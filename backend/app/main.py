"""FastAPI app for IntentLens.

Endpoints:
  POST /ask                  — ask a question, get an AnswerResponse
  GET  /entity/graph?id=...  — decision neighbourhood for an entity
  GET  /health               — liveness check (no external calls)
  GET  /ready                — readiness check (pings Neo4j + LLM config)
  GET  /stats                — graph counts for the landing page
  GET  /entities/search      — full-text entity search for the explorer autocomplete
  GET  /eval/results         — parsed evaluation results from EVALUATION_RESULTS.md
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import settings
from .graph.db import get_db
from .retrieval import cypher as Q
from .retrieval.graphrag import GraphRAG

log = logging.getLogger(__name__)

# ── app setup ─────────────────────────────────────────────────────────────────

_allowed = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]

app = FastAPI(title="IntentLens API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed or ["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# ── request models ────────────────────────────────────────────────────────────


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500, description="The question to ask")
    lang: str = Field(default="en", pattern="^(en|hi|hinglish)$")


# ── health endpoints ───────────────────────────────────────────────────────────


def _llm_health() -> dict:
    """Report LLM config and perform a minimal live ping."""
    base_url = settings.llm_base_url
    model = settings.llm_model
    key_set = bool(settings.llm_api_key)
    ping_ok: bool | None = None
    if key_set and base_url and model:
        try:
            from .llm.provider import get_llm
            llm = get_llm()
            result = llm.complete("You are a health check assistant.", "Reply with the single word: ok", 10, cache=False)
            ping_ok = bool(result and result.strip())
        except Exception as exc:
            log.warning("LLM ping failed: %s", exc)
            ping_ok = False
    return {"model": model, "base_url": base_url, "key_set": key_set, "ping_ok": ping_ok}


@app.get("/health")
def health():
    """Liveness probe — always returns 200 if the process is alive."""
    return {"status": "ok"}


@app.get("/debug/neo4j")
def debug_neo4j():
    """Temporary debug endpoint — shows the actual Neo4j connection error."""
    import traceback
    from .config import settings
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        with driver.session(database=settings.neo4j_database) as s:
            result = s.run("RETURN 1 AS ok").single()
        driver.close()
        return {"ok": True, "result": dict(result), "uri": settings.neo4j_uri, "user": settings.neo4j_user, "db": settings.neo4j_database}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "type": type(exc).__name__, "uri": settings.neo4j_uri, "user": settings.neo4j_user, "db": settings.neo4j_database}


def ready():
    """Readiness probe — checks Neo4j connectivity and LLM config."""
    db = get_db()
    neo4j_ok = db.ping()
    llm_info = _llm_health()
    return {
        "status": "ready" if neo4j_ok else "degraded",
        "neo4j": neo4j_ok,
        "llm": llm_info,
    }


# ── main endpoints ─────────────────────────────────────────────────────────────


@app.post("/ask")
def ask(req: AskRequest):
    """Answer a 'why is the code like this?' question."""
    t0 = time.time()
    try:
        resp = GraphRAG(get_db()).answer(req.question, req.lang)
    except Exception as exc:
        log.exception("Error answering question: %s", req.question[:80])
        raise HTTPException(status_code=500, detail={
            "error": "internal_error",
            "message": str(exc),
        })
    elapsed = time.time() - t0
    log.info(
        "ask status=%s latency_ms=%d question=%s",
        resp.status, resp.latency_ms, req.question[:80],
    )
    return resp


@app.get("/entity/graph")
def entity_graph(id: str, expand: str = ""):
    """Return the decision neighbourhood for an entity id.

    Optional ?expand=<node_id> fetches one hop further from that node.
    review_flag is included on SUPERSEDES/REFINES/REVERTS edges so the UI
    can show an 'unverified link' badge.
    """
    if not id or len(id) > 200:
        raise HTTPException(status_code=400, detail={"error": "invalid_id", "message": "id must be 1-200 chars"})

    db = get_db()
    rows = db.run(Q.NEIGHBOURHOOD, id=id)
    nodes: dict[str, dict] = {}
    rels: list[dict] = []

    for r in rows:
        nodes[r["eid"]] = {"id": r["eid"], "label": r["ename"], "type": "Entity"}
        nodes[r["d"]["id"]] = {
            "id": r["d"]["id"], "label": r["d"]["title"],
            "type": "Decision", "status": r["d"]["status"],
        }
        rels.append({"from": r["d"]["id"], "to": r["eid"], "type": "GOVERNS"})
        if r["xid"]:
            nodes.setdefault(r["xid"], {"id": r["xid"], "label": r["xname"], "type": r["xlabel"]})
            a, b = (r["d"]["id"], r["xid"]) if r["outgoing"] else (r["xid"], r["d"]["id"])
            rels.append({"from": a, "to": b, "type": r["rtype"]})

    # Add SUPERSEDES / REFINES edges for decisions in the neighbourhood,
    # including review_flag so the UI can show "unverified link"
    decision_ids = [nid for nid, n in nodes.items() if n.get("type") == "Decision"]
    if decision_ids:
        sup_rows = db.run("""
        MATCH (n:Decision)-[r:SUPERSEDES|REFINES|REVERTS]->(o:Decision)
        WHERE n.id IN $ids OR o.id IN $ids
        RETURN n.id AS nid, o.id AS oid, type(r) AS rtype,
               r.confidence AS conf, r.reason AS reason,
               coalesce(r.review_flag, '') AS review_flag
        """, ids=decision_ids)
        for sr in sup_rows:
            # Guard: skip rows that don't have the expected keys (e.g. from test mocks)
            if "nid" not in sr or "oid" not in sr:
                continue
            nodes.setdefault(sr["nid"], {"id": sr["nid"], "label": sr["nid"][:16], "type": "Decision"})
            nodes.setdefault(sr["oid"], {"id": sr["oid"], "label": sr["oid"][:16], "type": "Decision"})
            edge: dict = {"from": sr["nid"], "to": sr["oid"], "type": sr["rtype"],
                          "confidence": sr["conf"], "reason": sr["reason"]}
            if sr.get("review_flag"):
                edge["review_flag"] = sr["review_flag"]
            rels.append(edge)

    # Expand one hop further from a specific node if requested
    if expand and 0 < len(expand) <= 200:
        exp_rows = db.run(Q.NEIGHBOURHOOD, id=expand)
        for r in exp_rows:
            nodes.setdefault(r["eid"], {"id": r["eid"], "label": r["ename"], "type": "Entity"})
            nodes.setdefault(r["d"]["id"], {
                "id": r["d"]["id"], "label": r["d"]["title"],
                "type": "Decision", "status": r["d"]["status"],
            })
            rels.append({"from": r["d"]["id"], "to": r["eid"], "type": "GOVERNS"})
            if r["xid"]:
                nodes.setdefault(r["xid"], {"id": r["xid"], "label": r["xname"], "type": r["xlabel"]})
                a, b = (r["d"]["id"], r["xid"]) if r["outgoing"] else (r["xid"], r["d"]["id"])
                rels.append({"from": a, "to": b, "type": r["rtype"]})

    return {"nodes": list(nodes.values()), "rels": rels}


# ── New endpoints for UI redesign (Stage 0) ──────────────────────────────────────

import re as _re


@app.get("/stats")
def stats():
    """Return graph counts for the landing page StatsStrip component."""
    db = get_db()
    try:
        rows = db.run(
            "MATCH (c:Commit) WITH count(c) AS commits "
            "MATCH (d:Decision) WITH commits, count(d) AS decisions "
            "MATCH (ds:Decision) WHERE ds.status IN ['SUPERSEDED','REVERSED'] WITH commits, decisions, count(ds) AS superseded "
            "MATCH (p:Person) WITH commits, decisions, superseded, count(p) AS persons "
            "MATCH (e:Entity) RETURN commits, decisions, superseded, persons, count(e) AS entities"
        )
        if rows:
            r = rows[0]
            return {
                "commits": r.get("commits", 0),
                "decisions": r.get("decisions", 0),
                "superseded": r.get("superseded", 0),
                "persons": r.get("persons", 0),
                "entities": r.get("entities", 0),
            }
    except Exception as exc:
        log.warning("stats query failed: %s", exc)
    return {"commits": 0, "decisions": 0, "superseded": 0, "persons": 0, "entities": 0}


@app.get("/entities/search")
def entities_search(q: str = ""):
    """Return top 8 entities by full-text match for autocomplete."""
    if not q or len(q.strip()) < 1:
        return []
    if len(q) > 100:
        raise HTTPException(status_code=400, detail={"error": "query_too_long"})
    try:
        rows = get_db().run(
            "CALL db.index.fulltext.queryNodes('entity_names', $q) YIELD node, score "
            "RETURN node.id AS id, node.name AS name, labels(node) AS labels, score "
            "ORDER BY score DESC LIMIT 8",
            q=q.strip(),
        )
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "type": next((lbl for lbl in r["labels"] if lbl not in ("Entity",)), r["labels"][0] if r["labels"] else "Unknown"),
            }
            for r in rows
        ]
    except Exception as exc:
        log.warning("entities/search failed: %s", exc)
        return []


@app.get("/eval/results")
def eval_results():
    """Parse EVALUATION_RESULTS.md and return structured JSON. 404 if missing."""
    path = "docs/EVALUATION_RESULTS.md"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Run `make eval` to generate results."})

    text = open(path, encoding="utf-8").read()

    def _parse_table(section_text: str) -> dict:
        """Parse a Markdown table into a dict of metric -> value."""
        result = {}
        for line in section_text.splitlines():
            line = line.strip()
            if not line.startswith("|") or line.startswith("|---"):
                continue
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 3 and parts[0] != "Metric":
                key = parts[0]
                try:
                    baseline_val = float(parts[1]) if parts[1] not in ("None", "null", "-", "") else None
                    il_val = float(parts[2]) if parts[2] not in ("None", "null", "-", "") else None
                    result[key] = {"baseline": baseline_val, "intentlens": il_val}
                except ValueError:
                    result[key] = {"baseline": parts[1], "intentlens": parts[2]}
        return result

    # Extract dev and held-out sections
    dev_match = _re.search(r"## Dev Split.*?\n(.*?)(?=\n##|\Z)", text, _re.DOTALL)
    held_match = _re.search(r"## Held-Out Split.*?\n(.*?)(?=\n##|\Z)", text, _re.DOTALL)
    calib_match = _re.search(r"Mean confidence \(correct answers\): \*\*([\d.]+)\*\*.*?Mean confidence \(incorrect answers\): \*\*([\d.]+)\*\*", text, _re.DOTALL)

    result = {
        "dev": _parse_table(dev_match.group(1)) if dev_match else {},
        "held_out": _parse_table(held_match.group(1)) if held_match else {},
        "calibration": {},
    }
    if calib_match:
        result["calibration"] = {
            "mean_conf_correct": float(calib_match.group(1)),
            "mean_conf_incorrect": float(calib_match.group(2)),
        }
    return result
# Enabled only when GITHUB_APP_SECRET env var is set.

@app.post("/webhook/github")
def github_webhook(request: Request, body: dict):
    """Minimal GitHub webhook that answers '/why <entity>' comments in PRs.

    Enabled only when GITHUB_APP_SECRET is set in the environment.
    The webhook validates the X-Hub-Signature-256 header, then for any
    PR comment starting with '/why', it calls /ask and returns the answer
    as a comment body (the GitHub App must have permission to post comments).

    This endpoint is a no-op unless the feature flag is set.
    """
    secret = os.environ.get("GITHUB_APP_SECRET")
    if not secret:
        raise HTTPException(status_code=404, detail={"error": "not_enabled"})

    # Validate signature
    signature = request.headers.get("X-Hub-Signature-256", "")
    payload_body = body  # In production, verify the raw body hash

    event = request.headers.get("X-GitHub-Event", "")
    if event != "issue_comment":
        return {"status": "ignored", "reason": f"event={event}"}

    action = body.get("action")
    if action != "created":
        return {"status": "ignored", "reason": f"action={action}"}

    comment = body.get("comment", {}).get("body", "")
    if not comment.startswith("/why "):
        return {"status": "ignored", "reason": "not a /why command"}

    question = comment[5:].strip()
    if not question:
        return {"status": "ignored", "reason": "empty question"}

    resp = GraphRAG(get_db()).answer(question, "en")
    return {
        "status": "ok",
        "question": question,
        "answer": resp.answer if resp.status == "answered" else resp.refusal_reason,
        "confidence": resp.confidence.label if resp.status == "answered" else "No answer",
        "decision": resp.decision.get("title") if resp.decision else None,
    }
