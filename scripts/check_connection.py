"""Smoke-test all external dependencies.

Prints:
  - Neo4j server version and current index/constraint states
  - LLM provider config and result of one tiny live call
  - Overall PASS / FAIL

Usage:
    python -m scripts.check_connection
"""
from __future__ import annotations

import sys


# ── Neo4j ─────────────────────────────────────────────────────────────────────

def check_neo4j() -> bool:
    from backend.app.config import settings
    from backend.app.graph.db import get_db
    from neo4j.exceptions import AuthError, ServiceUnavailable

    print(f"  URI  : {settings.neo4j_uri}")
    print(f"  User : {settings.neo4j_user}")
    print(f"  DB   : {settings.neo4j_database}")

    try:
        db = get_db()
        ver = db.version()
        print(f"  Version : {ver}")
    except AuthError as exc:
        print(f"  [FAIL] {exc}", file=sys.stderr)
        return False
    except ServiceUnavailable as exc:
        print(f"  [FAIL] {exc}", file=sys.stderr)
        return False
    except Exception as exc:
        print(f"  [FAIL] Unexpected error: {exc}", file=sys.stderr)
        return False

    # Index / constraint states
    rows = db.run(
        "SHOW INDEXES YIELD name, type, state, labelsOrTypes, properties "
        "RETURN name, type, state, labelsOrTypes, properties "
        "ORDER BY type, name"
    )
    if rows:
        print(f"\n  Indexes ({len(rows)} total):")
        for r in rows:
            status = "ONLINE" if r["state"] == "ONLINE" else f"** {r['state']} **"
            print(f"    {status:10s}  {r['type']:12s}  {r['name']}")
    else:
        print("  No indexes found (schema not yet applied — run `make schema` first).")

    not_online = [r for r in rows if r["state"] != "ONLINE"]
    if not_online:
        print(f"\n  Warning: {len(not_online)} index(es) are not yet ONLINE.")

    return True


# ── LLM ───────────────────────────────────────────────────────────────────────

def check_llm() -> bool:
    from backend.app.config import settings
    from backend.app.llm.provider import LLM

    base_url = settings.llm_base_url
    model = settings.llm_model
    key = settings.llm_api_key

    print(f"  Base URL : {base_url or '(not set)'}")
    print(f"  Model    : {model or '(not set)'}")

    if not key:
        print("  [SKIP] LLM_API_KEY not set in .env — cannot make live call.")
        return False
    if not base_url or not model:
        print("  [SKIP] LLM_BASE_URL or LLM_MODEL not set — cannot make live call.")
        return False

    print("  Key      : set (not echoed)")
    try:
        llm = LLM()
        response = llm.complete(
            "You are a test harness. Be extremely concise.",
            "Reply with exactly the single word: OK",
            max_tokens=10,
            cache=False,
        )
        trimmed = response.strip()
        ok = "ok" in trimmed.lower()
        print(f"  Response : {trimmed!r}  →  {'OK' if ok else 'unexpected (non-fatal)'}")
        return True
    except Exception as exc:
        print(f"  [FAIL] LLM call failed: {exc}", file=sys.stderr)
        return False


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 54)
    print("  IntentLens — connection check")
    print("=" * 54)

    print("\n── Neo4j ──────────────────────────────────────────────")
    neo4j_ok = check_neo4j()

    print("\n── LLM ────────────────────────────────────────────────")
    llm_ok = check_llm()

    print("\n" + "=" * 54)
    if neo4j_ok and llm_ok:
        print("  [PASS] All checks passed.")
    elif neo4j_ok and not llm_ok:
        # LLM key missing is a warning, not a blocker for schema work
        print("  [WARN] Neo4j OK. LLM key missing or call failed — set key before mining.")
    else:
        print("  [FAIL] Neo4j check failed. Fix credentials before continuing.")
        sys.exit(1)


if __name__ == "__main__":
    main()
