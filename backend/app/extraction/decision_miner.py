"""Stage 3: LLM decision mining with deterministic quote verification and two-pass agreement."""
from __future__ import annotations
import re
from ..llm.provider import LLM, cosine, embed
from ..models import ExtractedDecision, Span, Thread

SYSTEM = """You extract ENGINEERING DECISIONS from a software project's discussion history.
A decision is a deliberate choice that governs code behaviour: a default value, an algorithm, a design trade-off,
a compatibility rule, a deprecation, a bug-fix strategy, a configuration choice.
Rules:
- Only extract decisions that are actually present. If the thread has none, return {"decisions": []}.
- Never invent rationale. If the reason is not stated, set "explicit_rationale": false and keep "rationale" brief or empty.
- Every decision MUST include at least one "spans" item whose "quote" is copied VERBATIM (<=300 chars) from the thread,
  with "source_id" equal to the id shown in brackets before that text.
- "governs": names of config keys, functions or files the decision concerns, exactly as written in the thread.
- "decided_by": GitHub logins or names who made or approved the decision.
Return JSON: {"decisions":[{"title","summary","rationale","alternatives_rejected":[],"decided_by":[],
"decided_on":"ISO date or null","explicit_rationale":true|false,"governs":[],"spans":[{"source_id","quote"}]}}\

Few-shot example 1 — thread WITH an explicit decision:

Thread text:
[pr:42] (2020-01-15) PR by antirez: Add replication backlog
We decided to add a replication backlog of 1mb by default. The reason is that without a backlog,
when a slave disconnects briefly, it needs a full resync which is very expensive. The backlog
buffers recent replication data so the slave can do a partial resync instead.
We considered 256kb but that's too small for most workloads. We also considered 10mb but that
would waste memory on small instances.

Output:
{"decisions":[{"title":"Add 1mb default replication backlog","summary":"Set repl-backlog-size to 1mb by default to enable partial resync after brief disconnections.","rationale":"Without a backlog, a brief slave disconnection requires a full resync which is expensive. 1mb buffers enough for partial resync.","alternatives_rejected":["256kb (too small for most workloads)","10mb (wastes memory on small instances)"],"decided_by":["antirez"],"decided_on":"2020-01-15","explicit_rationale":true,"governs":["repl-backlog-size"],"spans":[{"source_id":"pr:42","quote":"We decided to add a replication backlog of 1mb by default. The reason is that without a backlog, when a slave disconnects briefly, it needs a full resync which is very expensive."}]}]}}\

Few-shot example 2 — thread with NO decision:

Thread text:
[pr:43] (2020-02-01) PR by joe: Fix typo in README
Fixed a typo in the installation instructions.

Output:
{"decisions":[]}}"""

SYSTEM_B = SYSTEM + "\nBe conservative: prefer fewer, higher-quality decisions."


def thread_text(t: Thread, limit: int = 24000) -> str:
    parts = [f"[{t.id}] ({t.created_at}) {t.kind.upper()} by {t.author}: {t.title}\n{t.body}"]
    for c in t.comments:
        parts.append(f"[{c.id}] ({c.created_at}) {c.author}: {c.body}")
    return "\n\n".join(parts)[:limit]


def _norm(s: str) -> str:
    """Normalise text for verbatim comparison: collapse whitespace, lowercase,
    strip markdown formatting, convert smart quotes to ASCII."""
    s = s or ""
    # Unicode normalisation: NFKD decomposes ligatures and smart quotes
    import unicodedata
    s = unicodedata.normalize("NFKD", s)
    # Smart quotes → ASCII
    s = s.replace("\u2018", "'").replace("\u2019", "'")
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = s.replace("\u2013", "-").replace("\u2014", "-")  # en/em dash
    s = s.replace("\u00a0", " ")  # non-breaking space
    # Strip markdown emphasis markers
    s = re.sub(r"\*{1,2}(.*?)\*{1,2}", r"\1", s)  # *bold* / **bold**
    s = re.sub(r"_{1,2}(.*?)_{1,2}", r"\1", s)  # _italic_ / __bold__
    s = re.sub(r"`{1,2}(.*?)`{1,2}", r"\1", s)  # `code` / ``code``
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def verify_decision(d: ExtractedDecision, source: str) -> ExtractedDecision | None:
    """Keep only spans whose quote exists verbatim (whitespace-normalised) in the source; drop the decision if none.

    Also strips enclosing brackets from source_ids (the model sometimes returns
    [commit:sha] instead of commit:sha).
    """
    src = _norm(source)
    good = []
    for s in d.spans:
        if not s.quote:
            continue
        # Normalise source_id: strip brackets the model sometimes adds
        source_id = s.source_id.strip("[]")
        if _norm(s.quote) in src:
            good.append(Span(source_id=source_id, quote=s.quote))
    if not good:
        return None
    d.spans = good
    return d


def _parse(raw: dict, t: Thread) -> list[ExtractedDecision]:
    out = []
    for item in raw.get("decisions", []):
        try:
            item["spans"] = [Span(**s) for s in item.get("spans", [])]
            d = ExtractedDecision(**item)
            d.thread_id = t.id
            # For document threads: keep decided_on as None (will be filled by git blame).
            # For PR/commit threads: fall back to merged_at or created_at.
            if t.kind != "document":
                d.decided_on = d.decided_on or (t.merged_at or t.created_at) or None
            else:
                d.decided_on = None   # always null — blame sets it later
            out.append(d)
        except Exception:
            continue
    return out


def agreement_score(a: list[ExtractedDecision], b: list[ExtractedDecision]) -> dict[int, float]:
    """For each decision in `a`, best cosine similarity of its summary against decisions in `b` (0 if none)."""
    if not a:
        return {}
    if not b:
        return {i: 0.0 for i in range(len(a))}
    ea, eb = embed([x.summary for x in a]), embed([x.summary for x in b])
    return {i: max(0.0, max(cosine(va, vb) for vb in eb)) for i, va in enumerate(ea)}


def mine_thread(llm: LLM, t: Thread) -> list[ExtractedDecision]:
    text = thread_text(t)
    if len(text) < 200:
        return []
    a = _parse(llm.complete_json(SYSTEM, text, 8000), t)
    b = _parse(llm.complete_json(SYSTEM_B, text, 8000), t)
    scores = agreement_score(a, b)
    verified = []
    for i, d in enumerate(a):
        d.agreement = round(scores.get(i, 0.0), 3)
        v = verify_decision(d, text)
        if v:
            verified.append(v)
    return verified


# ── Document-specific mining ──────────────────────────────────────────────────
# Source code comments and redis.conf comment blocks need a different prompt:
# they are not PR discussions — they are recorded design rationale in inline
# comments.  Key differences:
#   • decided_by is always []  (comments have no attributed author)
#   • decided_on is always null
#   • source_id in spans = the Document node id  (path#Lstart)
#   • we only ask for one LLM pass (no SYSTEM_B agreement loop) to save cost

_DOC_SYSTEM = (
    "You extract ENGINEERING DECISIONS from source code comments and configuration"
    " documentation.\n"
    "A decision is a deliberate design choice captured in a comment: a default value"
    " rationale, an algorithm choice, a trade-off, a compatibility rule, a known"
    " limitation, a design constraint, or a configuration guideline.\n\n"
    "Rules:\n"
    "- Extract only what is explicitly stated. Never invent rationale.\n"
    "- Every decision MUST include at least one 'spans' item whose 'quote' is copied"
    " VERBATIM (<=300 chars) from the text, with 'source_id' equal to the document id"
    " shown in brackets at the start of the text.\n"
    "- 'governs': the specific config key, function name, or file the decision concerns.\n"
    "- 'decided_by': always [].\n"
    "- 'decided_on': always null.\n"
    "- If the comment only describes WHAT the code does with no stated reason,"
    ' return {"decisions": []}.\n\n'
    'Return JSON: {"decisions":[{"title","summary","rationale",'
    '"alternatives_rejected":[],"decided_by":[],"decided_on":null,'
    '"explicit_rationale":true|false,"governs":[],'
    '"spans":[{"source_id","quote"}]}]}\n\n'
    "Example — comment WITH a stated reason:\n"
    "[redis.conf#L142] (tcp-backlog) CONFIG DOCUMENT:\n"
    "In high requests-per-second environments you need a high backlog in order\n"
    "to avoid slow clients connection issues. The Linux kernel will silently\n"
    "truncate it to the value of /proc/sys/net/core/somaxconn.\n"
    "tcp-backlog 511\n\n"
    'Output: {"decisions":[{"title":"tcp-backlog default 511",'
    '"summary":"tcp-backlog 511 avoids slow client connections in high-RPS environments.",'
    '"rationale":"High RPS requires a high backlog to avoid slow client connection issues.",'
    '"alternatives_rejected":[],"decided_by":[],"decided_on":null,'
    '"explicit_rationale":true,"governs":["tcp-backlog"],'
    '"spans":[{"source_id":"redis.conf#L142",'
    '"quote":"you need a high backlog in order to avoid slow clients connection issues"}]}]}\n\n'
    "Example — comment with NO stated reason:\n"
    "[src/rdb.c#L100] (rdbSave) CODE COMMENT:\n"
    "Save the DB on disk.\n\n"
    'Output: {"decisions":[]}'
)


_DOC_SYSTEM_B = (
    "You are a strict engineering-decision auditor reviewing source code comments"
    " and configuration documentation from the Redis project.\n"
    "Extract only the most important ENGINEERING DECISIONS — deliberate design choices"
    " with an explicit stated reason. Skip anything that merely describes what code does.\n\n"
    "Rules:\n"
    "- Only extract if a clear reason/trade-off/constraint is stated.\n"
    "- Every decision needs at least one verbatim quote (<=300 chars) from the text,"
    " with source_id = the document id shown in brackets.\n"
    "- 'governs': the config key, function, or file this decision constrains.\n"
    "- 'decided_by': always [].\n"
    "- 'decided_on': always null.\n"
    "- When in doubt, return {\"decisions\": []}.\n\n"
    'Return JSON: {"decisions":[{"title","summary","rationale",'
    '"alternatives_rejected":[],"decided_by":[],"decided_on":null,'
    '"explicit_rationale":true|false,"governs":[],'
    '"spans":[{"source_id","quote"}]}]}\n\n'
    "Example — comment with explicit trade-off:\n"
    "[src/aof.c#L864] (aofInstallPreloadFile) CODE COMMENT:\n"
    "Prefer a hard link to avoid copying, and fall back to a full copy.\n\n"
    'Output: {"decisions":[{"title":"Prefer hard link over copy for AOF file install",'
    '"summary":"AOF file installation uses hard links to avoid the I/O cost of copying.",'
    '"rationale":"Hard links avoid copying.",'
    '"alternatives_rejected":["full copy"],"decided_by":[],"decided_on":null,'
    '"explicit_rationale":true,"governs":["aofInstallPreloadFile"],'
    '"spans":[{"source_id":"src/aof.c#L864",'
    '"quote":"Prefer a hard link to avoid copying, and fall back to a full copy"}]}]}\n\n'
    "Example — no explicit reason:\n"
    "[src/rdb.c#L100] (rdbSave) CODE COMMENT:\n"
    "Save the DB on disk.\n\n"
    'Output: {"decisions":[]}'
)

# Rationale markers: a quote containing none of these should flip explicit_rationale=False
_RATIONALE_MARKER_RE = re.compile(
    r"\b(because|in order to|to avoid|otherwise|so that|to prevent|"
    r"instead of|trade[-\s]off|this causes|without this|if we did not)\b",
    re.IGNORECASE,
)


def _strip_c_markers(text: str) -> str:
    """Strip C comment markers and leading * from text for quote verification."""
    import re as _re
    # Strip /* ... */ markers
    text = _re.sub(r"^/\*+\s*|\s*\*+/$", "", text.strip())
    text = _re.sub(r"^\s*\*+\s?", "", text, flags=_re.MULTILINE)
    # Strip // markers
    text = _re.sub(r"^\s*//+\s?", "", text, flags=_re.MULTILINE)
    # Strip # markers (redis.conf)
    text = _re.sub(r"^\s*#+\s?", "", text, flags=_re.MULTILINE)
    return text.strip()


def _doc_text(t: Thread) -> str:
    """Format a document Thread for the DOC_SYSTEM prompt."""
    kind_label = "CONFIG DOCUMENT" if "redis.conf" in t.id else "CODE COMMENT"
    return f"[{t.id}] ({t.title}) {kind_label}:\n{t.body}"


def _doc_verify_source(t: Thread) -> str:
    """Return the combined source text used for quote verification.

    Combines _doc_text() (what the LLM sees) with the comment-stripped body
    so that quotes work whether the model copied from the stripped or raw form.
    """
    doc_text_str = _doc_text(t)
    stripped = _strip_c_markers(t.body)
    return doc_text_str + "\n" + stripped


def _fix_explicit_rationale(d: ExtractedDecision) -> ExtractedDecision:
    """Set explicit_rationale=False when none of the verified quotes
    contain a rationale marker — the model may have over-claimed."""
    quotes_text = " ".join(s.quote for s in d.spans)
    if not _RATIONALE_MARKER_RE.search(quotes_text):
        d.explicit_rationale = False
    return d


def mine_document(llm: LLM, t: Thread) -> list[ExtractedDecision]:
    """Mine a single Document thread using the document-specific prompt.

    Uses the same two-pass agreement scheme as mine_thread:
      pass A  — normal _DOC_SYSTEM prompt
      pass B  — conservative _DOC_SYSTEM_B prompt
    Agreement is computed with agreement_score (cosine of summaries), exactly
    as for PR/commit threads.  No hard-coded values.

    After verification, explicit_rationale is set to False for any decision
    whose verified quotes contain no rationale marker.
    """
    text = _doc_text(t)
    verify_src = _doc_verify_source(t)   # wider source for quote matching
    if len(text.split()) < 12:
        return []

    a = _parse(llm.complete_json(_DOC_SYSTEM,   text, 4000), t)
    b = _parse(llm.complete_json(_DOC_SYSTEM_B, text, 4000), t)
    scores = agreement_score(a, b)
    verified = []
    for i, d in enumerate(a):
        d.agreement = round(scores.get(i, 0.0), 3)
        v = verify_decision(d, verify_src)
        if v:
            verified.append(_fix_explicit_rationale(v))
    return verified
