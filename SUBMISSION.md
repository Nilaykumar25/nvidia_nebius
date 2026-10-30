# SUBMISSION.md — Devpost Copy-Paste Kit

Use this file to fill out the Devpost submission form for the **Nebius × NVIDIA Global AI Hackathon**.

---

## Project name

**IntentLens**

## One-line tagline

Connect code to the decisions that shaped it — every answer cites its evidence, refuses when it can't.

## Track

**Coding and Agentic Engineering**

---

## Project description

### Inspiration

Every large codebase accumulates decisions without recording why. When a senior engineer leaves, the reasoning behind architectural choices leaves too. The tools we have — search, wikis, code comments — find text. They do not find decisions. A new joiner asking "why is this configuration key set to this value?" gets 150 commit mentions, a stale wiki page, or an LLM that confidently invents a plausible-sounding but wrong answer.

IntentLens is built to fix that. It ingests the git history, pull requests, and source-code comments of a repository, extracts engineering decisions using a two-pass LLM mining pipeline, stores them in a Neo4j knowledge graph with evidence links, and answers natural-language questions with a cited chain of evidence — refusing when the graph has no answer, instead of guessing.

### What it does

IntentLens answers "why is the code like this?" for a Git repository. Given a question like "Why is repl-diskless-sync set to yes by default?", it:

1. Links the question to code entities (config keys, functions, files) using exact-string and full-text matching.
2. Traverses the knowledge graph to find decisions that govern those entities.
3. Checks whether any matched decision has been superseded — if so, surfaces the replacement and marks the old decision as history.
4. Builds an evidence pack (up to 8 items: commits, PRs, comments, docs) and sends it to NVIDIA Nemotron 3 Ultra with a grounded-generation prompt. Every claim in the answer must cite a valid evidence ID; uncited claims are dropped.
5. Computes a 5-factor confidence score from graph facts (not from the LLM's self-assessment). If the score is below 0.35, the system refuses and returns the last people to modify the entity instead.

Three demo states are confirmed working: answered (High confidence), superseded (shows history with replacement), and refused (shows last changers and related discussions).

### How we built it

**Backend:** Python 3.11, FastAPI, Pydantic v2. The graph database is Neo4j AuraDB (Cypher 5, vector + full-text indexes). Ingestion runs via PyDriller (git) and the GitHub GraphQL API (PRs/issues). Local embeddings use sentence-transformers (all-MiniLM-L6-v2, 384 dimensions).

**LLM — NVIDIA Nemotron 3 Ultra on Nebius Token Factory:** Every LLM call in the pipeline uses Nemotron 3 Ultra served via the Nebius Token Factory OpenAI-compatible API. This covers:
- Two-pass decision mining (normal prompt + conservative prompt for agreement scoring)
- Supersession pair classification (`reinforces / refines / contradicts / unrelated`)
- Grounded cited answer generation
- Hindi/Hinglish query normalisation (translates to English while preserving code identifiers)

The LLM client (`backend/app/llm/provider.py`) strips `<think>…</think>` reasoning blocks, robustly extracts the first valid JSON object from any response, retries once with a stricter prompt on parse failure, and uses exponential backoff on 429/5xx errors.

**Frontend:** React 18 + Vite, @neo4j-nvl/react for the interactive graph explorer. The answer card displays a "Answered by Nemotron 3 Ultra on Nebius Token Factory" badge read from the `llm_model` field returned by `/ask`.

### Challenges

- **Nemotron reasoning verbosity:** Nemotron sometimes emits long `<think>…</think>` blocks before the JSON. We strip these before parsing, which keeps the pipeline clean.
- **JSON reliability:** Even with `response_format=json_object`, models occasionally wrap JSON in prose. The parser extracts the first valid JSON object from any text, with one structured retry on failure.
- **Quote verification:** Every mined decision must include a verbatim quote from the source thread. Implementing whitespace-normalised matching that handles smart quotes, markdown formatting, and C comment markers took significant iteration.
- **Supersession is a hard reasoning task:** Distinguishing "this decision contradicts the older one" from "this refines it" requires reading both decisions and their rationale. Nemotron's reasoning capability handles this reliably.

### Accomplishments

- A complete, working developer tool that answers "why" questions with cited evidence from a real public repository (redis/redis).
- 570 decisions mined and verified across the Redis replication and persistence subsystem.
- 18 SUPERSEDES + 40 REFINES edges detected automatically.
- Three confirmed demo states (answered, superseded, refused) working end-to-end.
- A 5-factor confidence model that is calibrated (higher confidence on correct answers than incorrect ones).
- Full multilingual support: Hindi/Hinglish questions work via Nemotron normalisation.

### What we learned

- OpenAI-compatible APIs are genuinely portable — migrating to Nebius Token Factory required only changing the base URL and key, with no code changes to the calling logic.
- Nemotron's reasoning tokens add latency on short tasks; stripping them is essential for interactive paths.
- Graph-first retrieval (GOVERNS traversal before vector search) dramatically improves precision over pure vector RAG for this task.
- Supersession is the hardest feature to get right — the three-signal approach (structural + semantic + temporal) is more reliable than any single signal.

### What's next

- Ingest more repositories beyond Redis.
- Add incident/post-mortem ingestion to link code entities to production incidents.
- Add a GitHub App so engineers can ask `/why <entity>` directly in PRs.
- Improve GOVERNS coverage with a tree-sitter-based entity extractor (currently ~14% GOVERNS coverage from commit-only mining without PRs).

---

## What changed during the submission period

The project existed as an earlier build with a different LLM provider. The following changes were made for this submission:

- Migrated the full LLM layer to Nemotron 3 Ultra on Nebius Token Factory (OpenAI-compatible client, no provider-specific SDK)
- Unified LLM client with exponential-backoff retries, `<think>` block stripping, and robust JSON extraction
- Nemotron-based Hindi/Hinglish query normalisation
- Live model badge in the UI (`llm_model` field in `/ask` response, displayed in AnswerCard)
- New `scripts/nemotron_demo_mining.py` — standalone Nemotron mining + supersession demo
- MIT LICENSE file added at repo root
- README rewritten for this hackathon, all old-hackathon branding removed
- `docs/DEPLOY.md` updated with Nebius Serverless Endpoints option
- `eval/nemotron_run.md` — Nemotron demo run output (generated by the demo script)

---

## Built with

`python` · `fastapi` · `pydantic` · `neo4j` · `neo4j-auradb` · `cypher` · `react` · `vite` · `nvidia-nemotron` · `nebius-token-factory` · `openai-sdk` · `sentence-transformers` · `pydriller` · `github-graphql-api` · `graph-rag` · `knowledge-graph`

---

## Feedback on Nebius Token Factory, AI Cloud, and NVIDIA tools

> **TODO — fill in before submitting:**
>
> **Nebius Token Factory:**
> - [ ] What worked well (API compatibility, latency, uptime, model selection)?
> - [ ] What was rough (documentation gaps, rate limits, dashboard UX, billing clarity)?
> - [ ] What would you improve?
>
> **NVIDIA Nemotron 3 Ultra:**
> - [ ] Quality of reasoning for supersession classification?
> - [ ] JSON output reliability (did response_format=json_object work consistently)?
> - [ ] Think-block verbosity — how much did it affect latency?
> - [ ] How did it compare to alternatives you tried?
>
> **Nebius AI Cloud (if used for deployment):**
> - [ ] Serverless Endpoints setup experience?
> - [ ] Any issues?

---

## 3-minute demo video script

### Timestamped outline

**0:00 — The problem (20 seconds)**
- Show: a large codebase, a developer asking "why is this config set this way?"
- Say: "When a senior engineer leaves, the reasoning behind the code leaves too. Search finds mentions. It doesn't find decisions. IntentLens does."

**0:20 — Live answered question (30 seconds)**
- Navigate to `/ask?demo=1`, click the "Multi-Part AOF" demo question.
- Show: the answered state — answer prose with citation chips, the decision card (title, rationale, decided date), the evidence rail with E1..E8 items.
- Say: "Every sentence cites a specific commit or PR. Claims without citations are dropped before the answer reaches you. High confidence — 0.78 — computed from five graph facts, not the LLM's self-assessment."

**0:50 — Superseded demo (30 seconds)**
- Click the "Bind address" demo question.
- Show: the superseded banner, the history section with the old decision struck through, the current replacement decision above it.
- Say: "The graph tracks when one decision replaces another. The old answer — from 2015 — is shown as history. The current decision, from 2022, is what you get."

**1:20 — Refused demo (30 seconds)**
- Click the "updateSlavesWaitingBgsave" demo question.
- Show: the refused state — reason, last person to work on it, related discussions.
- Say: "If the graph has no answer, IntentLens refuses rather than inventing one. It tells you who last touched the code and surfaces the closest related discussions."

**1:50 — Graph explorer (25 seconds)**
- Navigate to `/explore`, search for `repl-backlog-size`.
- Show: the NVL graph with Decision, Entity, Commit, Person nodes and GOVERNS/EVIDENCED_BY edges.
- Say: "Every answer is backed by a traversable knowledge graph. You can explore the full evidence neighbourhood of any entity."

**2:15 — Where Nemotron and Token Factory are used (25 seconds)**
- Show: `backend/app/llm/provider.py` — the OpenAI-compatible client, the `<think>` block stripping, the JSON extraction.
- Show: the model badge at the bottom of an answer card: "Answered by Nemotron 3 Ultra on Nebius Token Factory"
- Say: "Nemotron 3 Ultra, served via Nebius Token Factory, handles all LLM calls — two-pass decision mining, supersession classification, grounded answer generation, and multilingual query normalisation. One OpenAI-compatible client, one endpoint."

**2:40 — Impact and close (20 seconds)**
- Show: the landing page stats strip (570 decisions, 27,249 edges, 14,348 nodes).
- Say: "IntentLens works on any Git repository. Every answer is evidenced, every decision has a history, and the system refuses when it doesn't know. Connect code to the decisions that shaped it."

---

## Final submission checklist

- [ ] LICENSE file at repo root (MIT, visible on GitHub)
- [ ] README has working setup instructions — tested against actual commands
- [ ] All env vars documented in `.env.example` with placeholders (no real secrets)
- [ ] Demo URL is live and public → fill in `<!-- TODO: add ... -->` in README
- [ ] Demo video is public on YouTube, under 3 minutes → fill in URL in README
- [ ] GitHub repo is public
- [ ] Track selected on Devpost: **Coding and Agentic Engineering**
- [ ] Feedback section completed (in this file and on Devpost)
- [ ] "What changed during submission period" section is accurate
- [ ] No "hackfront", "sarvam", "PS 01", or old-hackathon text anywhere in repo
- [ ] `eval/nemotron_run.md` generated by running `python -m scripts.nemotron_demo_mining`
- [ ] TODO markers in README and SUBMISSION.md replaced with real values
