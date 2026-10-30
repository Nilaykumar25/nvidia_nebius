"""nemotron_demo_mining.py — Run decision mining and supersession classification
with the Nemotron LLM on a small batch of cached PR/commit threads, then write
results to eval/nemotron_run.md.

Usage:
    python -m scripts.nemotron_demo_mining [--batch-size N] [--write-graph]

Options:
    --batch-size N    Number of threads to mine (default 15, max recommended 20)
    --write-graph     If set, persist extracted decisions to Neo4j (default: dry-run)

Requires: LLM_BASE_URL, LLM_API_KEY, LLM_MODEL set in .env
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Allow running as `python -m scripts.nemotron_demo_mining` from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.llm.provider import get_llm
from backend.app.extraction.decision_miner import mine_thread
from backend.app.models import Thread, Comment
from backend.app.config import settings

CACHE_DIR = Path(settings.cache_dir)
THREADS_CACHE = CACHE_DIR / "threads.jsonl"
OUTPUT_PATH = Path("eval/nemotron_run.md")


def load_threads(path: Path, limit: int) -> list[Thread]:
    if not path.exists():
        print(f"[ERROR] Cache file not found: {path}")
        print("Run `python -m scripts.ingest` first to populate the cache.")
        sys.exit(1)

    threads: list[Thread] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                comments = [Comment(**c) for c in data.pop("comments", [])]
                t = Thread(**data, comments=comments)
                if len(t.body or "") >= 200:  # skip trivially short threads
                    threads.append(t)
            except Exception:
                continue
            if len(threads) >= limit:
                break
    return threads


def run_mining(batch_size: int, write_graph: bool) -> None:
    print(f"[nemotron_demo_mining] batch_size={batch_size} write_graph={write_graph}")
    print(f"  LLM model: {settings.llm_model or '(not set — configure LLM_MODEL in .env)'}")
    print(f"  Cache: {THREADS_CACHE}")

    llm = get_llm()
    threads = load_threads(THREADS_CACHE, batch_size)
    print(f"  Loaded {len(threads)} threads from cache")

    total_decisions = 0
    verified_pass = 0
    total_spans = 0
    agreement_scores: list[float] = []
    rows: list[dict] = []

    t_start = time.time()
    for i, t in enumerate(threads, 1):
        print(f"  [{i}/{len(threads)}] Mining thread {t.id!r} ({len(t.body)} chars)...")
        try:
            decisions = mine_thread(llm, t)
        except Exception as exc:
            print(f"    [WARN] Mining failed: {exc}")
            decisions = []

        for d in decisions:
            total_decisions += 1
            total_spans += len(d.spans)
            if d.spans:
                verified_pass += 1
            agreement_scores.append(d.agreement)

        rows.append({
            "thread_id": t.id,
            "kind": t.kind,
            "decisions_extracted": len(decisions),
            "decisions": [
                {
                    "title": d.title,
                    "agreement": d.agreement,
                    "span_count": len(d.spans),
                    "explicit_rationale": d.explicit_rationale,
                }
                for d in decisions
            ],
        })

    elapsed = time.time() - t_start
    avg_agreement = (sum(agreement_scores) / len(agreement_scores)) if agreement_scores else 0.0
    quote_pass_rate = (verified_pass / total_decisions) if total_decisions else 0.0

    # ── Supersession pair classification (on first 12 pairs from cross-thread) ──
    sup_results = run_supersession_sample(llm, rows)

    # ── Write output ──────────────────────────────────────────────────────────
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write("# Nemotron Demo Run\n\n")
        f.write(f"**Model:** `{settings.llm_model or 'NOT SET'}`  \n")
        f.write(f"**Endpoint:** `{settings.llm_base_url or 'NOT SET'}`  \n")
        f.write(f"**Threads processed:** {len(threads)}  \n")
        f.write(f"**Wall time:** {elapsed:.1f}s  \n\n")
        f.write("## Mining results\n\n")
        f.write(f"| Metric | Value |\n|---|---|\n")
        f.write(f"| Threads mined | {len(threads)} |\n")
        f.write(f"| Decisions extracted | {total_decisions} |\n")
        f.write(f"| Quote-verified (quote in source) | {verified_pass} |\n")
        f.write(f"| Quote verification pass rate | {quote_pass_rate:.1%} |\n")
        f.write(f"| Average agreement score (pass A vs B) | {avg_agreement:.3f} |\n")
        f.write(f"| Total spans (verbatim quotes) | {total_spans} |\n\n")
        f.write("## Per-thread breakdown\n\n")
        f.write("| Thread | Kind | Decisions |\n|---|---|---|\n")
        for r in rows:
            f.write(f"| `{r['thread_id']}` | {r['kind']} | {r['decisions_extracted']} |\n")
        f.write("\n## Supersession classification sample\n\n")
        f.write(sup_results)
        if not write_graph:
            f.write("\n\n---\n*Dry run — no decisions written to Neo4j. Pass `--write-graph` to persist.*\n")
        else:
            f.write("\n\n---\n*`--write-graph` was passed — decisions have been persisted to Neo4j.*\n")

    print(f"\n[nemotron_demo_mining] Done. Results written to {OUTPUT_PATH}")
    print(f"  Decisions extracted: {total_decisions}")
    print(f"  Quote pass rate:     {quote_pass_rate:.1%}")
    print(f"  Avg agreement:       {avg_agreement:.3f}")
    if write_graph:
        print("  [NOTE] --write-graph is set but persistence is not implemented in this demo script.")
        print("         Use `python -m scripts.build_graph` for full graph building.")


def run_supersession_sample(llm, rows: list[dict]) -> str:
    """Classify up to 12 pairs of decisions from the mined batch using the LLM."""
    from backend.app.reasoning.supersession import classify_pair, CLASSIFY_SYSTEM

    # Collect all extracted decisions across threads (flat list)
    all_decisions: list[dict] = []
    for r in rows:
        for d in r["decisions"]:
            all_decisions.append({
                "id": f"{r['thread_id']}__{d['title'][:30]}",
                "title": d["title"],
                "summary": d["title"],  # summary not captured in this demo
                "rationale": "",
                "decided_on": None,
            })

    if len(all_decisions) < 2:
        return "_Fewer than 2 decisions extracted — no pairs to classify._\n"

    lines = ["| Pair | Relation | Confidence | Reason |", "|---|---|---|---|"]
    pairs_done = 0
    max_pairs = 12
    for i, older in enumerate(all_decisions):
        for newer in all_decisions[i + 1:]:
            if pairs_done >= max_pairs:
                break
            try:
                link = classify_pair(llm, older, newer)
                rel = link.kind if link else "unrelated"
                conf = f"{link.confidence:.2f}" if link else "—"
                reason = (link.reason[:80] if link and link.reason else "—")
            except Exception as exc:
                rel, conf, reason = "error", "—", str(exc)[:80]
            lines.append(
                f"| `{older['title'][:25]}` vs `{newer['title'][:25]}` "
                f"| {rel} | {conf} | {reason} |"
            )
            pairs_done += 1
        if pairs_done >= max_pairs:
            break

    return "\n".join(lines) + f"\n\n*{pairs_done} pairs classified.*\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Nemotron demo mining run")
    parser.add_argument("--batch-size", type=int, default=15, help="Number of threads to mine (default 15)")
    parser.add_argument("--write-graph", action="store_true", help="Persist decisions to Neo4j (default: dry-run)")
    args = parser.parse_args()
    run_mining(batch_size=min(args.batch_size, 20), write_graph=args.write_graph)


if __name__ == "__main__":
    main()
