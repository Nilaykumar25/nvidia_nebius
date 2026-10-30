# Demo Script for IntentLens

## Pre-demo checklist (5 min before)

1. **Start backend**: `.venv\Scripts\uvicorn backend.app.main:app --port 8001`
2. **Start frontend**: `cd frontend && npm run dev`
3. **Warm caches**: `.venv\Scripts\python -m scripts.warm_demo`
4. **Open browser**: http://localhost:5173
5. **Verify all 3 examples work** — they should load in < 2s

## Demo flow

### 1. Normal answer (30s)
Click: **"Why does always-show-logo exist in redis.conf?"**

Show:
- The answer text with [E1] citation links
- Decision card: title, date, status (ACTIVE), person to ask
- Evidence chain rail with commit links
- Confidence meter showing "High" with reasons
- Graph view on the right showing the decision neighbourhood

### 2. Superseded-aware answer (30s)
Click: **"Why does replicationCron avoid simultaneous BGSAVE and BGREWRITEAOF?"**

Show:
- The **amber banner** explaining the old decision was superseded
- The current decision is shown, not the stale one
- The timeline shows the older decision with SUPERSEDED status (struck through)
- The graph shows the SUPERSEDES edge

### 3. Refusal (30s)
Click: **"Why did the Redis team choose to use sds instead of C strings?"**

Show:
- The **distinct refusal card** (grey left border)
- The reason: "No decision in the graph governs the entities named in this question."
- The message: "IntentLens will not guess."
- Person to ask: antirez (most commits to the touched entities)
- Related last changes as context

## Failure modes and mitigations

| # | Failure | Mitigation |
|---|---------|------------|
| 1 | AuraDB serverless sleeps after idle | Pre-warm with `warm_demo.py`; the `db.run()` auto-reconnects on stale connections |
| 2 | LLM rate-limited (429) | Provider retries with exponential backoff; cache means repeated demo questions don't hit the API |
| 3 | LLM returns empty or malformed response | Provider strips `<think>` blocks; robust JSON extraction retries once with stricter prompt; cache has known-good responses |
| 4 | Network latency spike | Demo uses cached responses (sub-1s); p95 is 2s |
| 5 | Browser CORS error | CORS allows localhost:5173; set `ALLOWED_ORIGINS` in .env if using a different port |
| 6 | Graph is empty | Run `make schema && make ingest && make build --limit 200 && make supersede` before demo |
| 7 | Frontend NVL rendering fails | Graph view shows "No graph to show" gracefully; build is verified with `npm run build` |
| 8 | Wrong answer returned | The demo questions are carefully chosen to match entities with GOVERNS links in the graph |
| 9 | AuraDB connection drops mid-demo | `db.run()` catches the exception and reconnects with a fresh driver |
| 10 | LLM takes >12s | Cache is warm from `warm_demo.py`; first cold call is ~3-5s, cached calls are <0.5s |

## Fallback video

If the live demo fails, record a 3-minute screen capture using the same flow above with `warm_demo.py` having already been run. The recorded version shows the exact same answers because the LLM cache makes responses deterministic.
