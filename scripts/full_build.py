"""
full_build.py  —  End-to-end data build pipeline.

Stages:
  1. Validate credentials / services
  2. Fetch PR threads (MAX_PRS=300 + dossier PRs by number)
  3. Ingest commits (resumable)
  4. Extract document blocks (ingest_docs.py)
  5. Load graph: commits, entities, threads, documents
  6. Mine decisions: PR threads, commit-threads, Document threads
  7. Post-load: git blame dates, ConfigKey seeding, DESCRIBES links,
                GOVERNS re-resolution, File->Function promotion,
                near-duplicate dedup, null-date cleanup
  8. run_supersession
  9. Write eval/supersession_found.md
 10. Print final summary table and verify 5 example questions via POST /ask

All steps are resumable (MERGE + skip-if-cached). Rate-limit back-off is
handled by the existing github_ingest / llm provider layers.
"""
from __future__ import annotations

import datetime
import json
import os
import random
import re
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from backend.app.config import settings
from backend.app.extraction.decision_miner import mine_thread, mine_document
from backend.app.extraction.entities import (
    entity_ids_for_commit, find_refs, parse_config_keys,
)
from backend.app.graph import loader
from backend.app.graph.db import get_db
from backend.app.llm.provider import cosine, embed, get_llm
from backend.app.models import Thread
from backend.app.reasoning.supersession import run_supersession

REPO   = ROOT / "data" / "repo"
CACHE  = ROOT / "data" / "cache"
EVAL   = ROOT / "eval"

DOSSIER_PRS = [
    7092, 8303, 8474, 9166, 9644, 9788, 9968,
    10092, 10504, 10690, 10866, 11676, 11713, 11905,
]

# ── helpers ───────────────────────────────────────────────────────────────────

def read_jsonl(name: str) -> list[dict]:
    p = CACHE / name
    if not p.exists():
        return []
    rows = []
    with p.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


def run_py(*args, timeout=600) -> subprocess.CompletedProcess:
    """Run a Python module or script in the venv, streaming output."""
    cmd = [sys.executable] + list(args)
    print(f"\n>>> {' '.join(args)}")
    result = subprocess.run(cmd, cwd=str(ROOT), timeout=timeout)
    if result.returncode != 0:
        print(f"  [WARNING] exited {result.returncode}")
    return result


def _run_git(*args, cwd=REPO) -> str:
    try:
        r = subprocess.run(
            ["git"] + list(args), cwd=str(cwd),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=15,
        )
        return r.stdout
    except subprocess.TimeoutExpired:
        return ""


def _parse_blame(out: str) -> dict:
    sha_counts: dict[str, int] = defaultdict(int)
    sha_meta: dict[str, dict] = {}
    cur = None
    for line in out.splitlines():
        if re.match(r"^[0-9a-f]{40} ", line):
            cur = line.split()[0]
            sha_counts[cur] += 1
        elif line.startswith("author ") and cur:
            sha_meta.setdefault(cur, {})["author"] = line[7:].strip()
        elif line.startswith("author-time ") and cur:
            ts = int(line.split()[1])
            sha_meta.setdefault(cur, {})["date"] = (
                datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
            )
        elif line.startswith("summary ") and cur:
            sha_meta.setdefault(cur, {})["subject"] = line[8:].strip()
    return {"counts": dict(sha_counts), "meta": sha_meta}


_REFORMAT = {"whitespace", "indentation", "style", "formatting",
             "clang-format", "copyright", "license"}
_PR_RE = re.compile(r"\(#(\d+)\)")


def blame_doc(doc: dict) -> dict:
    start = doc.get("start_line") or 1
    end   = doc.get("end_line")   or start
    relpath = doc.get("path", "")
    if not relpath or not (REPO / relpath).exists():
        return {"date_source": "unknown"}
    out = _run_git("blame", "-w", "--line-porcelain",
                   f"-L{start},{end}", relpath)
    if not out.strip():
        return {"date_source": "unknown"}
    parsed = _parse_blame(out)
    if not parsed["counts"]:
        return {"date_source": "unknown"}
    best = max(parsed["counts"], key=parsed["counts"].get)
    meta = parsed["meta"].get(best, {})
    subject = meta.get("subject", "")
    date    = meta.get("date")
    if any(kw in subject.lower() for kw in _REFORMAT) or not date:
        return {"date_source": "unknown"}
    pr_m = _PR_RE.search(subject)
    return {
        "sha":         best,
        "date":        date,
        "author":      meta.get("author", ""),
        "subject":     subject,
        "pr_number":   int(pr_m.group(1)) if pr_m else None,
        "date_source": "blame_comment_introduced",
    }


def _find_enclosing_fn(relpath: str, line: int) -> str | None:
    path = REPO / relpath
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    func_re = re.compile(
        r"^(?:(?:static|inline|void|int|long|unsigned|char|"
        r"[A-Za-z_]\w*)\s+\*?\s*)*([A-Za-z_][A-Za-z0-9_]*)\s*\("
    )
    skip = {"if","while","for","switch","return","sizeof","assert",
            "else","do","NULL","void","int","char","long","unsigned",
            "static","inline","struct","typedef"}
    # first try 2 lines AFTER the comment end (the function it documents)
    for i in range(line, min(line + 3, len(lines))):
        m = func_re.match(lines[i])
        if m and m.group(1) not in skip:
            return m.group(1)
    # then scan backwards for enclosing function
    for i in range(min(line - 1, len(lines) - 1), -1, -1):
        m = func_re.match(lines[i])
        if m and m.group(1) not in skip:
            return m.group(1)
    return None


# ── Stage 1: credential check ─────────────────────────────────────────────────

def stage1_check():
    print("\n=== STAGE 1: credential / service check ===")
    db = get_db()
    if not db.ping():
        print("NEO4J UNREACHABLE — aborting"); sys.exit(1)
    if not settings.github_token:
        print("GITHUB_TOKEN missing — aborting"); sys.exit(1)
    if not settings.llm_api_key:
        print("LLM_API_KEY missing — aborting"); sys.exit(1)
    print("  Neo4j OK  |  GITHUB_TOKEN set  |  LLM_API_KEY set")


# ── Stage 2: fetch PR threads ─────────────────────────────────────────────────

def stage2_fetch_prs():
    print("\n=== STAGE 2: fetch PR threads ===")
    existing = read_jsonl("threads.jsonl")
    seen_nums = {t["number"] for t in existing if t.get("number")}
    print(f"  Already cached: {len(existing)} threads, {len(seen_nums)} unique PRs")

    # Dossier PRs by number (skip already cached)
    missing_dossier = [n for n in DOSSIER_PRS if n not in seen_nums]
    if missing_dossier:
        nums_str = ",".join(str(n) for n in missing_dossier)
        run_py("-m", "backend.app.ingestion.github_ingest",
               "--pr-numbers", nums_str, timeout=300)
    else:
        print(f"  All {len(DOSSIER_PRS)} dossier PRs already cached")

    # Paginated fetch up to MAX_PRS=300
    existing_after = read_jsonl("threads.jsonl")
    current_count = len(existing_after)
    max_prs = 300
    if current_count < max_prs:
        remaining = max_prs - current_count
        # Temporarily override max_prs in settings via env
        env = {**os.environ, "MAX_PRS": str(remaining)}
        cmd = [sys.executable, "-m", "backend.app.ingestion.github_ingest"]
        print(f"  Fetching up to {remaining} more PRs via paginated ingest...")
        result = subprocess.run(cmd, cwd=str(ROOT), env=env, timeout=600)
        if result.returncode != 0:
            print(f"  [WARNING] github_ingest exited {result.returncode}")
    else:
        print(f"  Already have {current_count} threads (>= {max_prs})")


# ── Stage 3: ingest commits ───────────────────────────────────────────────────

def stage3_commits():
    print("\n=== STAGE 3: ingest commits ===")
    from backend.app.ingestion.git_ingest import ingest_commits
    n = ingest_commits()
    existing = read_jsonl("commits.jsonl")
    print(f"  New commits written: {n}  |  Total cached: {len(existing)}")


# ── Stage 4: extract document blocks ─────────────────────────────────────────

def stage4_docs():
    print("\n=== STAGE 4: extract document blocks ===")
    run_py("scripts/ingest_docs.py", timeout=60)


# ── Stage 5: load graph (commits, entities, threads, documents) ───────────────

def stage5_load(db):
    print("\n=== STAGE 5: load graph ===")
    commits    = read_jsonl("commits.jsonl")
    pr_threads = read_jsonl("threads.jsonl")
    docs_all   = read_jsonl("documents.jsonl")

    conf_text = (REPO / "redis.conf").read_text(encoding="utf-8", errors="replace")
    known = set(parse_config_keys(conf_text).keys())

    print(f"  commits={len(commits)}  threads={len(pr_threads)}  docs={len(docs_all)}")

    loader.load_commits(db, commits)
    ents = []
    for c in commits:
        e = entity_ids_for_commit(
            c["files"],
            {p for p in settings.paths if p.endswith(".conf")},
            known or None,
        )
        ents.append({"sha": c["sha"], **e})
    loader.load_entities(db, ents)
    loader.load_threads(db, pr_threads)

    commit_refs = [
        {"source_id": c["sha"], "ref_number": n}
        for c in commits for n in find_refs(c["message"])
    ]
    pr_refs = [
        {"source_id": t["id"], "ref_number": n}
        for t in pr_threads
        for n in find_refs(t.get("body", "") + " " + t.get("title", ""))
    ]
    all_refs = commit_refs + pr_refs
    if all_refs:
        loader.add_references(db, all_refs)
        print(f"  references: {len(all_refs)}")

    # Seed all ConfigKey nodes from redis.conf
    ck_rows = [{"key": k, "value": v} for k, v in parse_config_keys(conf_text).items()]
    db.run_batches("""
    UNWIND $rows AS r
    MERGE (k:ConfigKey {id:'config:'+r.key})
      ON CREATE SET k:Entity, k.name=r.key, k.default_value=r.value, k.path='redis.conf'
      ON MATCH  SET k.default_value=coalesce(k.default_value, r.value), k:Entity
    """, ck_rows)
    print(f"  ConfigKey nodes seeded: {len(ck_rows)}")

    loader.load_documents(db, docs_all)
    print(f"  documents loaded: {len(docs_all)}")

    # Ensure DESCRIBES links for all redis.conf docs (ConfigKey may be new)
    db.run("""
    MATCH (doc:Document)
    WHERE doc.source = 'redis.conf' AND doc.section IS NOT NULL AND doc.section <> ''
    MATCH (k:ConfigKey {id:'config:'+doc.section})
    MERGE (doc)-[:DESCRIBES]->(k)
    """)


# ── Stage 6: mine decisions ───────────────────────────────────────────────────

def stage6_mine(db):
    print("\n=== STAGE 6: mine decisions ===")
    commits    = read_jsonl("commits.jsonl")
    pr_threads = read_jsonl("threads.jsonl")
    docs_all   = read_jsonl("documents.jsonl")

    kept_docs = [d for d in docs_all if d.get("source_kind") == "source_comment"]
    doc_threads = [
        Thread(
            id=d["id"], kind="document",
            title=d.get("section") or d.get("path", ""),
            body=d.get("text", ""),
            url=d.get("url", ""),
            author="", created_at="",
        )
        for d in kept_docs
    ]

    in_pr = {s for t in pr_threads for s in t.get("commit_shas", [])}
    commit_threads = [
        Thread(
            id=f"commit:{c['sha']}", kind="commit",
            title=c["message"].split("\n")[0],
            body=c["message"],
            url=f"https://github.com/{settings.repo_owner}/{settings.repo_name}/commit/{c['sha']}",
            author=c["author"], created_at=c["date"],
            commit_shas=[c["sha"]],
            files=[f["path"] for f in c["files"]],
        ).model_dump()
        for c in commits
        if c["sha"] not in in_pr and len(c["message"]) > 300
    ]

    work_pr     = [Thread(**t) for t in pr_threads]
    work_commit = [Thread(**t) for t in commit_threads]
    work_doc    = doc_threads

    print(f"  PR threads:      {len(work_pr)}")
    print(f"  Commit threads:  {len(work_commit)}")
    print(f"  Document threads:{len(work_doc)}")

    # Check which decisions already exist (idempotent re-run)
    existing_ids = {r["id"] for r in db.run("MATCH (d:Decision) RETURN d.id AS id")}
    print(f"  Existing decisions in graph: {len(existing_ids)}")

    from tqdm import tqdm
    llm = get_llm()

    decisions_pr_commit = []
    decisions_doc       = []
    doc_decision_counts: dict[str, int] = {}

    all_work = work_pr + work_commit + work_doc
    for t in tqdm(all_work, desc="mining"):
        try:
            mined = mine_document(llm, t) if t.kind == "document" else mine_thread(llm, t)
        except Exception as ex:
            print(f"  skip {t.id}: {ex}")
            continue
        if t.kind == "document":
            decisions_doc.extend(mined)
            doc_decision_counts[t.id] = doc_decision_counts.get(t.id, 0) + len(mined)
        else:
            decisions_pr_commit.extend(mined)

    if decisions_pr_commit:
        for d in decisions_pr_commit:
            if d.thread_id.startswith("commit:"):
                d.thread_id = d.thread_id.split(":", 1)[1]
        loader.load_decisions(db, decisions_pr_commit)
        print(f"  decisions loaded (PR/commit): {len(decisions_pr_commit)}")

    if decisions_doc:
        stats = loader.load_decisions_from_documents(db, decisions_doc)
        print(f"  decisions loaded (documents): {stats['loaded']}")
        print(f"    zero GOVERNS: {stats['zero_governs']}")
        print(f"    file-only:    {stats['file_only_governs']}")

    return decisions_doc


# ── Stage 7: post-load enrichment ────────────────────────────────────────────

def stage7_enrich(db, doc_decisions_loaded: bool = True):
    print("\n=== STAGE 7: post-load enrichment ===")
    docs_all  = read_jsonl("documents.jsonl")
    kept_docs = [d for d in docs_all if d.get("source_kind") == "source_comment"]

    # 7a: git blame all kept docs
    print(f"  Running git blame on {len(kept_docs)} docs...")
    blame_cache: dict[str, dict] = {}
    for doc in kept_docs:
        blame_cache[doc["id"]] = blame_doc(doc)
    got_date = sum(1 for v in blame_cache.values() if v.get("date_source") == "blame_comment_introduced")
    got_pr   = sum(1 for v in blame_cache.values() if v.get("pr_number"))
    print(f"    got date: {got_date}/{len(kept_docs)}  got PR: {got_pr}")

    # Update Document nodes with blame metadata
    blame_doc_rows = [
        {
            "doc_id":       doc_id,
            "intro_sha":    b.get("sha") or "",
            "intro_date":   b.get("date") or "",
            "intro_author": b.get("author") or "",
            "date_source":  b.get("date_source", "unknown"),
        }
        for doc_id, b in blame_cache.items()
    ]
    db.run_batches("""
    UNWIND $rows AS r
    MATCH (d:Document {id:r.doc_id})
    SET d.intro_sha    = CASE WHEN r.intro_sha   <> '' THEN r.intro_sha   ELSE null END,
        d.intro_date   = CASE WHEN r.intro_date  <> '' THEN r.intro_date  ELSE null END,
        d.intro_author = CASE WHEN r.intro_author <> '' THEN r.intro_author ELSE null END,
        d.date_source  = r.date_source
    """, blame_doc_rows)

    # Update all doc-sourced decisions with blame date + MADE_BY + EVIDENCED_BY Commit
    dec_rows = db.run("""
    MATCH (d:Decision)-[:EVIDENCED_BY]->(doc:Document)
    WHERE doc.source IS NOT NULL AND doc.source <> ''
    RETURN d.id AS did, doc.id AS doc_id
    """)

    decision_blame_rows = []
    for r in dec_rows:
        b = blame_cache.get(r["doc_id"], {})
        if b.get("date_source") == "blame_comment_introduced":
            decision_blame_rows.append({
                "did":     r["did"],
                "date":    b["date"],
                "author":  b.get("author") or "",
                "sha":     b.get("sha") or "",
                "subject": b.get("subject") or "",
                "pr_num":  b.get("pr_number"),
            })

    if decision_blame_rows:
        db.run_batches("""
        UNWIND $rows AS r
        MATCH (d:Decision {id:r.did})
        SET d.decided_on = r.date, d.date_source = 'blame_comment_introduced'
        """, decision_blame_rows)

        db.run_batches("""
        UNWIND $rows AS r
        MATCH (d:Decision {id:r.did})
        MERGE (p:Person {id:r.author}) SET p.name = r.author
        MERGE (d)-[:MADE_BY]->(p)
        """, [r for r in decision_blame_rows if r["author"]])

        db.run_batches("""
        UNWIND $rows AS r
        MATCH (d:Decision {id:r.did})
        MERGE (c:Commit {id:r.sha})
          ON CREATE SET c.date=r.date, c.author=r.author,
                        c.message=r.subject, c.text=r.subject,
                        c.url='https://github.com/redis/redis/commit/'+r.sha
        MERGE (d)-[:EVIDENCED_BY]->(c)
        """, [r for r in decision_blame_rows if r["sha"]])

        db.run_batches("""
        UNWIND $rows AS r
        MATCH (c:Commit {id:r.sha})
        MERGE (pr:PullRequest {id:'pr:'+toString(r.pr_num)})
          ON CREATE SET pr.number=r.pr_num,
                        pr.url='https://github.com/redis/redis/pull/'+toString(r.pr_num)
        MERGE (c)-[:PART_OF]->(pr)
        """, [r for r in decision_blame_rows if r["pr_num"]])

    # Null-out empty decided_on strings
    db.run("""
    MATCH (d:Decision)
    WHERE d.decided_on = ''
    SET d.decided_on = null
    """)

    # 7b: Re-run GOVERNS resolution for doc decisions
    db.run("""
    MATCH (d:Decision)-[:EVIDENCED_BY]->(doc:Document)
    WHERE doc.source IS NOT NULL AND doc.source <> ''
      AND NOT (d)-[:GOVERNS]->(:Entity)
    MATCH (doc)-[:DESCRIBES]->(t)
    WHERE t:ConfigKey OR t:Function
    MERGE (d)-[:GOVERNS]->(t)
    """)

    # 7c: Promote File-only to Function
    file_only_rows = db.run("""
    MATCH (d:Decision)-[:GOVERNS]->(f:File)
    WHERE NOT (d)-[:GOVERNS]->(:Function) AND NOT (d)-[:GOVERNS]->(:ConfigKey)
    MATCH (d)-[:EVIDENCED_BY]->(doc:Document)
    WHERE doc.source IS NOT NULL AND doc.source <> ''
    RETURN d.id AS did, f.id AS fpath, doc.start_line AS sl, doc.end_line AS el
    """)
    promoted = 0
    for r in file_only_rows:
        fn_name = _find_enclosing_fn(r["fpath"] or "", r["sl"] or 1)
        if not fn_name:
            continue
        fn_id = f"fn:{r['fpath']}::{fn_name}"
        db.run("""
        MATCH (d:Decision {id:$did})-[rel:GOVERNS]->(f:File {id:$fpath})
        MERGE (fn:Function {id:$fn_id})
          ON CREATE SET fn:Entity, fn.name=$fn_name, fn.path=$fpath
        MERGE (d)-[:GOVERNS]->(fn)
        DELETE rel
        """, did=r["did"], fpath=r["fpath"], fn_id=fn_id, fn_name=fn_name)
        promoted += 1
    print(f"    File->Function promoted: {promoted}")

    # 7d: Near-duplicate dedup (cosine > 0.9), cap 3/doc
    doc_decisions = db.run("""
    MATCH (d:Decision)-[:EVIDENCED_BY]->(doc:Document)
    WHERE doc.source IS NOT NULL AND doc.source <> ''
    RETURN doc.id AS doc_id, d.id AS did, d.summary AS summary,
           d.agreement AS agr
    ORDER BY doc.id, d.agreement DESC
    """)
    by_doc: dict[str, list] = defaultdict(list)
    for r in doc_decisions:
        by_doc[r["doc_id"]].append(r)

    to_delete: list[str] = []
    for doc_id, decs in by_doc.items():
        if len(decs) <= 1:
            continue
        summaries = [d["summary"] or "" for d in decs]
        embs = embed(summaries)
        kept: list[int] = []
        for i in range(len(decs)):
            if any(cosine(embs[i], embs[j]) > 0.9 for j in kept):
                to_delete.append(decs[i]["did"])
            else:
                kept.append(i)
        for idx in kept[3:]:
            to_delete.append(decs[idx]["did"])

    if to_delete:
        db.run_batches("""
        UNWIND $rows AS r
        MATCH (d:Decision {id:r.did}) DETACH DELETE d
        """, [{"did": did} for did in to_delete])
        print(f"    Duplicate decisions deleted: {len(to_delete)}")

    # Final zero-GOVERNS count
    zero = db.run("""
    MATCH (d:Decision)-[:EVIDENCED_BY]->(doc:Document)
    WHERE doc.source IS NOT NULL AND doc.source <> ''
      AND NOT (d)-[:GOVERNS]->(:Entity)
    RETURN count(d) AS n
    """)[0]["n"]
    print(f"    Zero-GOVERNS after enrichment: {zero}")
    print(f"  Stage 7 done. Blame-dated decisions: {len(decision_blame_rows)}")


# ── Stage 8: supersession ────────────────────────────────────────────────────

def stage8_supersession(db):
    print("\n=== STAGE 8: run supersession ===")
    llm = get_llm()
    result = run_supersession(db, llm)
    print(f"  decisions={result['decisions']}  links={result['links']}"
          f"  llm_calls={result['llm_calls']}  non_active={result['non_active']}")
    return result


# ── Stage 9: write supersession_found.md ────────────────────────────────────

def stage9_write_supersession(db):
    print("\n=== STAGE 9: write eval/supersession_found.md ===")
    EVAL.mkdir(exist_ok=True)
    rows = db.run("""
    MATCH (newer:Decision)-[r:SUPERSEDES|REFINES|REVERTS]->(older:Decision)
    RETURN type(r) AS edge_type, r.confidence AS confidence, r.reason AS reason,
           newer.id AS newer_id, newer.title AS newer_title,
           newer.decided_on AS newer_date, newer.status AS newer_status,
           older.id AS older_id, older.title AS older_title,
           older.decided_on AS older_date, older.status AS older_status
    ORDER BY edge_type, r.confidence DESC
    """)

    lines = [
        "# Supersession Edges Found",
        "",
        f"Total edges: {len(rows)}",
        "",
        "| Type | Conf | Newer (date) | Older (date) | Reason |",
        "|------|------|--------------|--------------|--------|",
    ]
    for r in rows:
        n_date = (r["newer_date"] or "?")[:10]
        o_date = (r["older_date"] or "?")[:10]
        reason = (r["reason"] or "")[:80].replace("|", "/")
        lines.append(
            f"| {r['edge_type']} | {r['confidence']:.2f} | "
            f"{r['newer_title'][:40]} ({n_date}) | "
            f"{r['older_title'][:40]} ({o_date}) | {reason} |"
        )

    lines += ["", "## Detail"]
    for i, r in enumerate(rows, 1):
        lines += [
            f"",
            f"### [{i}] {r['edge_type']}  confidence={r['confidence']:.3f}",
            f"**Newer** `{r['newer_id'][:8]}`  {r['newer_date'] or '?'}  "
            f"[{r['newer_status']}]  {r['newer_title']}",
            f"**Older** `{r['older_id'][:8]}`  {r['older_date'] or '?'}  "
            f"[{r['older_status']}]  {r['older_title']}",
            f"Reason: {r['reason'] or '(none)'}",
        ]

    out = EVAL / "supersession_found.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Written: {out}")
    return rows


# ── Stage 10: summary table + 5 question verification ─────────────────────────

def stage10_summary(db, sup_rows):
    print("\n=== STAGE 10: summary table + question verification ===")

    # Node counts
    node_counts = db.run("""
    CALL apoc.meta.stats() YIELD labels
    RETURN labels
    """)
    # Fallback if apoc not available
    labels_to_count = [
        "Commit","PullRequest","Issue","Comment","Document",
        "Decision","Person","File","Function","ConfigKey",
    ]
    counts = {}
    for lbl in labels_to_count:
        r = db.run(f"MATCH (n:{lbl}) RETURN count(n) AS n")
        counts[lbl] = r[0]["n"] if r else 0

    # Relationship counts
    rel_types = [
        "EVIDENCED_BY","GOVERNS","MODIFIES","PART_OF","AUTHORED",
        "SUPERSEDES","REFINES","REVERTS","DESCRIBES","COMMENTED_ON",
        "MADE_BY","REFERENCES","CLOSES",
    ]
    rel_counts = {}
    for rt in rel_types:
        r = db.run(f"MATCH ()-[r:{rt}]->() RETURN count(r) AS n")
        rel_counts[rt] = r[0]["n"] if r else 0

    # Decisions by status
    status_rows = db.run("""
    MATCH (d:Decision)
    RETURN d.status AS status, count(d) AS n
    ORDER BY n DESC
    """)

    # Decisions by source kind
    source_rows = db.run("""
    MATCH (d:Decision)
    RETURN coalesce(d.source_kind,'pr_or_commit') AS source_kind, count(d) AS n
    ORDER BY n DESC
    """)

    # Supersession edge counts
    sup_counts = {}
    for rt in ["SUPERSEDES","REFINES","REVERTS"]:
        r = db.run(f"MATCH ()-[r:{rt}]->() RETURN count(r) AS n")
        sup_counts[rt] = r[0]["n"] if r else 0

    # Print summary
    print("\n" + "="*70)
    print("FINAL BUILD SUMMARY")
    print("="*70)
    print("\nNode counts:")
    for lbl, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {lbl:<15} {n:>7}")
    print("\nRelationship counts:")
    for rt, n in sorted(rel_counts.items(), key=lambda x: -x[1]):
        print(f"  {rt:<20} {n:>7}")
    print("\nDecisions by status:")
    for r in status_rows:
        print(f"  {r['status']:<15} {r['n']:>5}")
    print("\nDecisions by source kind:")
    for r in source_rows:
        print(f"  {r['source_kind']:<20} {r['n']:>5}")
    print("\nSupersession / refinement edges:")
    for rt, n in sup_counts.items():
        print(f"  {rt:<12} {n:>5}")

    # ── 5 example questions ────────────────────────────────────────────────────
    questions = [
        {
            "q": "Why was repl-diskless-sync changed to yes by default?",
            "entity": "repl-diskless-sync",
        },
        {
            "q": "Why does Redis use a shared replication buffer?",
            "entity": "repl-backlog-size",
        },
        {
            "q": "Why are TTLs replicated as absolute millisecond timestamps?",
            "entity": "src/replication.c",
        },
        {
            "q": "What is the rationale for the Multi-Part AOF mechanism?",
            "entity": "appenddirname",
        },
        {
            "q": "Why does the WAIT command track per-client write offsets?",
            "entity": "WAIT",
        },
    ]

    print("\n" + "="*70)
    print("5 EXAMPLE QUESTIONS AND API RESULTS")
    print("="*70)

    # Start the API server (if not running), then hit it
    import httpx
    api_url = "http://127.0.0.1:8000"

    # Try to reach the API; start it if needed
    api_ok = False
    for attempt in range(3):
        try:
            r = httpx.get(f"{api_url}/health", timeout=5)
            if r.status_code == 200:
                api_ok = True
                break
        except Exception:
            pass
        if attempt < 2:
            time.sleep(2)

    if not api_ok:
        print("  API not reachable at http://127.0.0.1:8000 — skipping live test")
        print("  Start with: .venv/Scripts/python.exe -m uvicorn backend.app.main:app")
        for q_item in questions:
            print(f"\n  Q: {q_item['q']}")
            print(f"     entity hint: {q_item['entity']}")
            print(f"     result: (API not running — cannot verify)")
    else:
        for q_item in questions:
            try:
                resp = httpx.post(
                    f"{api_url}/ask",
                    json={"question": q_item["q"]},
                    timeout=60,
                )
                body = resp.json()
                status = body.get("status", "?")
                conf   = body.get("confidence", {}).get("label", "?")
                sup    = body.get("superseded_notice") or ""
                answer_preview = (body.get("answer") or "")[:120]
                print(f"\n  Q: {q_item['q']}")
                print(f"     entity: {q_item['entity']}")
                print(f"     status={status}  confidence={conf}")
                if sup:
                    print(f"     SUPERSEDED: {sup[:120]}")
                if answer_preview:
                    print(f"     answer: {answer_preview}")
            except Exception as ex:
                print(f"\n  Q: {q_item['q']}")
                print(f"     ERROR: {ex}")

    # Write markdown summary
    out_path = EVAL / "build_summary.md"
    md = ["# Final Build Summary", "", f"Generated: {datetime.datetime.utcnow().isoformat()}", ""]
    md += ["## Node Counts", "", "| Label | Count |", "|-------|-------|"]
    for lbl, n in sorted(counts.items(), key=lambda x: -x[1]):
        md.append(f"| {lbl} | {n} |")
    md += ["", "## Relationship Counts", "", "| Type | Count |", "|------|-------|"]
    for rt, n in sorted(rel_counts.items(), key=lambda x: -x[1]):
        md.append(f"| {rt} | {n} |")
    md += ["", "## Decisions by Status", "", "| Status | Count |", "|--------|-------|"]
    for r in status_rows:
        md.append(f"| {r['status']} | {r['n']} |")
    md += ["", "## Decisions by Source Kind", "", "| Source | Count |", "|--------|-------|"]
    for r in source_rows:
        md.append(f"| {r['source_kind']} | {r['n']} |")
    md += ["", "## Supersession Edges", "", "| Type | Count |", "|------|-------|"]
    for rt, n in sup_counts.items():
        md.append(f"| {rt} | {n} |")
    md += ["", "## 5 Example Questions", ""]
    for q_item in questions:
        md.append(f"- **{q_item['q']}** (entity: `{q_item['entity']}`)")
    out_path.write_text("\n".join(md), encoding="utf-8")
    print(f"\n  Summary written to: {out_path}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-stage", type=int, default=1,
                    help="Resume from this stage (1-10)")
    ap.add_argument("--end-stage", type=int, default=10,
                    help="Stop after this stage")
    args = ap.parse_args()

    s = args.start_stage
    e = args.end_stage

    if s <= 1 <= e: stage1_check()

    db = get_db()

    if s <= 2 <= e: stage2_fetch_prs()
    if s <= 3 <= e: stage3_commits()
    if s <= 4 <= e: stage4_docs()
    if s <= 5 <= e: stage5_load(db)

    doc_decisions_loaded = False
    if s <= 6 <= e:
        stage6_mine(db)
        doc_decisions_loaded = True

    if s <= 7 <= e: stage7_enrich(db, doc_decisions_loaded)
    if s <= 8 <= e: sup_result = stage8_supersession(db)
    else: sup_result = {}

    sup_rows = []
    if s <= 9 <= e: sup_rows = stage9_write_supersession(db)
    if s <= 10 <= e: stage10_summary(db, sup_rows)

    print("\n\nBUILD COMPLETE.")


if __name__ == "__main__":
    main()
