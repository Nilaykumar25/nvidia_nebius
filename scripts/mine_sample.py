"""Mine a sample of threads and print each extracted decision with verified quotes.

Usage:
    python -m scripts.mine_sample [thread_ids ...]

If no thread_ids are given, picks the 10 longest commit-threads automatically.
Thread IDs can be:
  - "pr:123"   (from threads.jsonl — requires GitHub token)
  - "commit:abc1234"  (from commits.jsonl — uses commit SHA prefix)

Output: one block per thread showing extracted decisions, verified quotes,
agreement scores, and which were dropped by verification.
"""
from __future__ import annotations

import json
import os
import sys

from backend.app.config import settings
from backend.app.extraction.decision_miner import (
    SYSTEM, SYSTEM_B, _norm, _parse, agreement_score, mine_thread, thread_text, verify_decision,
)
from backend.app.llm.provider import get_llm
from backend.app.models import Thread


def _read_jsonl(name: str) -> list[dict]:
    p = os.path.join(settings.cache_dir, name)
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()] if os.path.exists(p) else []


def _build_commit_thread(c: dict) -> Thread:
    """Build a Thread from a CommitRecord dict."""
    return Thread(
        id=f"commit:{c['sha']}",
        kind="commit",
        title=c["message"].split("\n")[0],
        body=c["message"],
        url=f"https://github.com/{settings.repo_owner}/{settings.repo_name}/commit/{c['sha']}",
        author=c["author"],
        created_at=c["date"],
        commit_shas=[c["sha"]],
        files=[f["path"] for f in c["files"]],
    )


def _auto_pick_threads(commits: list[dict], n: int = 10) -> list[Thread]:
    """Pick the N commit-threads with the longest messages."""
    # Sort by message length descending, take top N
    sorted_commits = sorted(commits, key=lambda c: len(c.get("message", "")), reverse=True)
    return [_build_commit_thread(c) for c in sorted_commits[:n]]


def _find_thread_by_id(tid: str, commits: list[dict], pr_threads: list[dict]) -> Thread | None:
    """Find a thread by its id string."""
    if tid.startswith("commit:"):
        sha = tid.split(":", 1)[1]
        for c in commits:
            if c["sha"].startswith(sha):
                return _build_commit_thread(c)
    elif tid.startswith("pr:"):
        for t in pr_threads:
            if t["id"] == tid:
                return Thread(**t)
    return None


def main() -> None:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    commits = _read_jsonl("commits.jsonl")
    pr_threads = _read_jsonl("threads.jsonl")

    # Determine threads to mine
    if len(sys.argv) > 1:
        ids = sys.argv[1:]
        threads = []
        for tid in ids:
            t = _find_thread_by_id(tid, commits, pr_threads)
            if t:
                threads.append(t)
            else:
                print(f"WARNING: thread {tid} not found in cache", file=sys.stderr)
    else:
        threads = _auto_pick_threads(commits, 10)

    if not threads:
        print("No threads to mine. Provide thread IDs or ensure commits.jsonl exists.", file=sys.stderr)
        sys.exit(1)

    print(f"Mining {len(threads)} thread(s) with LLM model {settings.llm_model!r}...\n")

    llm = get_llm()
    total_found = 0
    total_verified = 0
    total_dropped = 0
    total_json_first_try = 0
    total_json_repair = 0

    for t in threads:
        text = thread_text(t)
        print("=" * 70)
        print(f"Thread: {t.id}")
        print(f"  Author: {t.author}")
        print(f"  Date:   {t.created_at[:10]}")
        print(f"  Title:  {t.title[:80]}")
        print(f"  Text length: {len(text)} chars")
        print("-" * 70)

        if len(text) < 200:
            print("  [SKIP] Thread too short (<200 chars)\n")
            continue

        # Pass A (normal prompt)
        try:
            raw_a = llm.complete_json(SYSTEM, text, 8000)
            total_json_first_try += 1
        except Exception as exc:
            print(f"  [ERROR] Pass A JSON parse failed: {exc}")
            total_json_repair += 1
            continue

        # Pass B (conservative prompt)
        try:
            raw_b = llm.complete_json(SYSTEM_B, text, 8000)
        except Exception as exc:
            print(f"  [WARN] Pass B JSON parse failed: {exc}")
            raw_b = {"decisions": []}

        a = _parse(raw_a, t)
        b = _parse(raw_b, t)
        scores = agreement_score(a, b)

        found = len(a)
        verified_list = []
        dropped_list = []

        for i, d in enumerate(a):
            d.agreement = round(scores.get(i, 0.0), 3)
            v = verify_decision(d, text)
            if v:
                verified_list.append(v)
            else:
                dropped_list.append(d)

        total_found += found
        total_verified += len(verified_list)
        total_dropped += len(dropped_list)

        if not verified_list and not dropped_list:
            print("  No decisions extracted.\n")
            continue

        for d in verified_list:
            print(f"  ✓ DECISION: {d.title}")
            print(f"    Summary: {d.summary}")
            print(f"    Rationale: {d.rationale or '(inferred)'}")
            print(f"    Explicit: {d.explicit_rationale}")
            print(f"    Governs: {d.governs}")
            print(f"    Decided by: {d.decided_by}")
            print(f"    Agreement: {d.agreement:.3f}")
            for s in d.spans:
                print(f"    Quote [{s.source_id}]: \"{s.quote[:200]}\"")
            print()

        for d in dropped_list:
            print(f"  ✗ DROPPED (quote not verbatim): {d.title}")
            for s in d.spans:
                print(f"    Quote was: \"{s.quote[:200]}\"")
            print()

    # ── Summary ──────────────────────────────────────────────────────────────
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Threads mined:          {len(threads)}")
    print(f"  Decisions found:        {total_found}")
    print(f"  Decisions verified:     {total_verified}")
    print(f"  Decisions dropped:       {total_dropped}")
    print(f"  Drop rate:              {total_dropped}/{total_found} = "
          f"{(total_dropped/total_found*100):.0f}%" if total_found else "  Drop rate: N/A")
    print(f"  JSON first-try success: {total_json_first_try}/{len(threads)}")
    print(f"  JSON repair needed:      {total_json_repair}")


if __name__ == "__main__":
    main()
