# Architecture
Pipeline: `ingest` (git + GitHub -> JSONL cache) -> `build_graph` (entities, evidence, decisions -> Neo4j) -> `run_supersession` -> `serve` (FastAPI GraphRAG) -> React UI -> `run_eval`.

## Question path
1. Normalise language (Nemotron translation for Hindi/Hinglish).
2. Link entities: exact identifier match, then full-text over entity names.
3. Fetch governing decisions with the `DECISIONS_BY_ENTITY` template (hop 1). If nothing, vector search over Decision embeddings (hop 2).
4. If a matched decision is superseded or reversed, fetch and promote its replacement.
5. Select the latest ACTIVE/UNCERTAIN decision as governing; others are history.
6. Build evidence pack with stable refs (E1...). LLM must return claims with citations; claims without valid citations are dropped.
7. Compute confidence from five graph-derived factors. Below threshold -> refusal with last changers, closest discussions and top contributor.

## Why graph, not just vectors
"Which decision governs this config key, who made it, what replaced it?" is a traversal. The graph encodes GOVERNS, EVIDENCED_BY, MADE_BY, SUPERSEDES, REVERTS and MODIFIES edges so status and provenance are facts, not guesses.

## Safety properties
- No LLM-generated Cypher. Parameterised templates only.
- Quote verification at mining time; citation verification at answer time.
- Confidence is not the model's self-rating.

## Thread kinds

The `Thread.kind` field controls which mining path is used:

| kind | Source | Mining function | EVIDENCED_BY target |
|------|--------|-----------------|---------------------|
| `pr` | GitHub GraphQL | `mine_thread` | PullRequest node |
| `commit` | git log | `mine_thread` | Commit node |
| `document` | `scripts/ingest_docs.py` | `mine_document` | Document node (`path#Lstart`) |

Document threads are single-paragraph blocks extracted from `redis.conf` comment
sections or rationale-marker C comments in `src/replication.c`, `src/rdb.c`,
`src/aof.c`.  They use a dedicated single-pass prompt (`_DOC_SYSTEM` in
`decision_miner.py`) because source code comments are not PR discussions.

## Document source_kind property

`Document.source_kind` classifies content for retrieval filtering:

| value | What it covers | Mine? | Retrieve? |
|-------|---------------|-------|-----------|
| `source_comment` | Rationale-filtered C/conf blocks (242 total, 149 kept) | Yes | Yes |
| `source_comment_dropped` | Kept in cache but filtered out (93 blocks, too short or no verb) | No | No |
| *(absent)* | Legacy chunks from `doc_ingest.py` (2,236 records) | No | Fulltext only |

Legacy chunks cover `src/replication.c`, `src/rdb.c`, `src/aof.c` raw paragraphs,
`deps/` READMEs, `LICENSE.txt`, and various `.md` files.  They are NOT in any
vector index, and the current retrieval pipeline does not query `document_text`
directly — Documents only surface as evidence snippets attached to a Decision.

## DESCRIBES edges (Document → Entity)

Added by `load_documents` in `loader.py`:

```
(Document)-[:DESCRIBES]->(ConfigKey)   redis.conf block above a setting
(Document)-[:DESCRIBES]->(File)        C source block; path matches File.id
(Document)-[:DESCRIBES]->(Function)    best-effort: section name = Function.name
```

GOVERNS fallback for document-sourced decisions:
prefer ConfigKey/Function targets of DESCRIBES; fall back to File only when
neither exists.
