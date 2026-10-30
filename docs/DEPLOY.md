# Deployment Guide — Render (backend) + Vercel (frontend)

IntentLens backend is a Python/FastAPI app. Frontend is a React SPA.
Backend → Render free tier. Frontend → Vercel hobby plan.

```
Browser
  │
  ▼
Vercel  (React SPA, static)
  │  VITE_API_BASE_URL → Render URL
  ▼
Render  (FastAPI, Python)
  │
  ├──► Neo4j AuraDB       (cloud graph DB)
  └──► NVIDIA API          (Nemotron 3 Ultra LLM)
       integrate.api.nvidia.com/v1
```

---

## Prerequisites

| What | Where |
|---|---|
| Neo4j AuraDB instance | [console.neo4j.io](https://console.neo4j.io) — free tier is enough |
| NVIDIA API key | [build.nvidia.com](https://build.nvidia.com) → get API key |
| GitHub PAT | [github.com/settings/tokens](https://github.com/settings/tokens) → Classic, `public_repo` scope |
| Render account | [render.com](https://render.com) — free |
| Vercel account | [vercel.com](https://vercel.com) — free |

---

## Step 1 — Deploy backend on Render

### 1a. Create the web service

1. Go to **dashboard.render.com** → New → Web Service
2. Connect GitHub → select the `intentlens` repository
3. Render detects `render.yaml` automatically → click **Apply**

### 1b. Set secrets in Render dashboard

Go to your service → **Environment** → add these (all marked `sync: false` in `render.yaml` so Render never auto-fills them):

| Key | Value |
|-----|-------|
| `NEO4J_URI` | `neo4j+s://<your-instance-id>.databases.neo4j.io` |
| `NEO4J_USER` | `<your-instance-id>` (e.g. `228d5e41`) |
| `NEO4J_PASSWORD` | your AuraDB password |
| `NEO4J_DATABASE` | `<your-instance-id>` (same as user on AuraDB free) |
| `LLM_API_KEY` | your `nvapi-...` key from build.nvidia.com |
| `GITHUB_TOKEN` | `ghp_...` (only needed if re-running ingest) |

Non-secret values are already set in `render.yaml` with `value:`:

| Key | Value already in render.yaml |
|-----|-------------------------------|
| `LLM_BASE_URL` | `https://integrate.api.nvidia.com/v1` |
| `LLM_MODEL` | `nvidia/nemotron-3-ultra-550b-a55b` |
| `LLM_TIMEOUT_SECONDS` | `60` |
| `LLM_MAX_RETRIES` | `3` |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` |

### 1c. Deploy

Click **Save Changes** → Render builds (~3 min). Copy your service URL:
```
https://intentlens-api.onrender.com
```

Test it:
```bash
curl https://intentlens-api.onrender.com/health
# → {"status":"ok"}

curl https://intentlens-api.onrender.com/ready
# → {"status":"ready","neo4j":true,"llm":{"model":"nvidia/nemotron-3-ultra-550b-a55b","ping_ok":true}}
```

---

## Step 2 — Deploy frontend on Vercel

### 2a. Import project

1. Go to **vercel.com/new** → Import Git Repository → select the `intentlens` repo
2. Set **Root Directory** to `frontend`
3. Framework: **Vite** (auto-detected from `vercel.json`)

### 2b. Set environment variable

In Vercel → Project → **Environment Variables**:

| Key | Value |
|-----|-------|
| `VITE_API_BASE_URL` | `https://intentlens-api.onrender.com` ← your Render URL from Step 1c |

> This is the only env var the frontend needs. It is injected at build time.
> `vercel.json` handles SPA routing (all paths → `index.html`).

### 2c. Deploy

Click **Deploy** → frontend live at e.g.:
```
https://intentlens.vercel.app
```

---

## Step 3 — Wire CORS together

Back in **Render** → your service → Environment → update `ALLOWED_ORIGINS`:
```
ALLOWED_ORIGINS=https://intentlens.vercel.app,http://localhost:5173
```
Save → Render redeploys automatically.

---

## Step 4 — Verify end-to-end

Open your Vercel URL and go to `/ask?demo=1`. Check all three states:

| Demo button | Expected result |
|-------------|-----------------|
| Multi-Part AOF | ANSWERED — High confidence, evidence rail, model badge shows Nemotron |
| Bind address | ANSWERED with superseded banner + history |
| updateSlavesWaitingBgsave | REFUSED — last changers shown |

Check `/explore` — search `repl-backlog-size` and the graph loads.

Check the footer: shows "Powered by NVIDIA Nemotron 3 Ultra on Nebius Token Factory".

---

## Environment variable reference

| Variable | Required | Where to set | Notes |
|---|---|---|---|
| `NEO4J_URI` | ✅ | Render (secret) | `neo4j+s://...` |
| `NEO4J_USER` | ✅ | Render (secret) | Instance ID |
| `NEO4J_PASSWORD` | ✅ | Render (secret) | AuraDB password |
| `NEO4J_DATABASE` | ✅ | Render (secret) | Instance ID |
| `LLM_BASE_URL` | ✅ | `render.yaml` value | `https://integrate.api.nvidia.com/v1` |
| `LLM_API_KEY` | ✅ | Render (secret) | `nvapi-...` |
| `LLM_MODEL` | ✅ | `render.yaml` value | `nvidia/nemotron-3-ultra-550b-a55b` |
| `LLM_TIMEOUT_SECONDS` | optional | `render.yaml` value | default 60 |
| `LLM_MAX_RETRIES` | optional | `render.yaml` value | default 3 |
| `GITHUB_TOKEN` | ingest only | Render (secret) | `ghp_...` |
| `ALLOWED_ORIGINS` | ✅ | `render.yaml` (update after Vercel) | Your Vercel URL |
| `VITE_API_BASE_URL` | ✅ | Vercel env vars | Your Render URL |

---

## Troubleshooting

**CORS error in browser console**
`ALLOWED_ORIGINS` in Render doesn't include your Vercel URL. Update it and save — Render redeploys.

**`/ready` returns `neo4j: false`**
AuraDB free tier pauses after 72 hours idle. Resume it at [console.neo4j.io](https://console.neo4j.io) — takes ~30s.

**`/ready` returns `ping_ok: false`**
`LLM_API_KEY` is wrong or expired. Regenerate at [build.nvidia.com](https://build.nvidia.com).

**Stats strip shows zeros on landing**
Neo4j connection failed or graph is empty. Check `/ready`.

**Render free tier sleeping**
First request after 15 min idle takes ~30s. Warmup before demo:
```bash
curl https://intentlens-api.onrender.com/health
```

**`VITE_API_BASE_URL` not working**
It must be set *before* the Vercel build runs (not at runtime). Set it in Vercel → Settings → Environment Variables → then trigger a redeploy.

---

## Optional: Nebius Serverless Endpoints

If you want the full stack on Nebius infrastructure, deploy the backend container to Nebius Serverless Endpoints instead of Render:

```bash
docker build -t intentlens-api .
# Push to Nebius Container Registry, then create a Serverless Endpoint
# pointing to the image with the same env vars listed above
```

Set `VITE_API_BASE_URL` in Vercel to your Nebius endpoint URL instead of the Render URL.
