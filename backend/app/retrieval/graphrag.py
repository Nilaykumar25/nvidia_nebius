"""GraphRAG pipeline: link entities -> guarded Cypher -> evidence pack -> grounded answer -> verify -> confidence/refusal."""
from __future__ import annotations
import re, time
from ..config import settings
from ..graph.db import Neo4jDB
from ..llm.provider import LLM, embed, get_llm, translate_to_english
from ..models import AnswerResponse, Confidence, EvidenceItem, Factors
from ..reasoning import confidence as conf
from . import cypher as Q

STOP = set("""a an the is are was were why what when who how does do did of for in on at to from by with this that these those it its
be been being as and or not so then than into about default set value config option flag""".split())
LIVE = {"ACTIVE", "UNCERTAIN"}

GEN_SYSTEM = """You answer 'why is the code like this?' using ONLY the evidence pack provided.
Return JSON: {"claims":[{"text":"one sentence","evidence":["E1","E2"]}]}.
Rules: every claim must cite at least one evidence ref from the pack. Use 2 to 4 claims. Do not add facts that are not in the pack.
State the decision, then the reason, then any rejected alternative if present. Be concise and neutral."""


def keywords(q: str) -> list[str]:
    return [t for t in re.findall(r"[A-Za-z][A-Za-z0-9_\-]*", q.lower()) if t not in STOP and len(t) > 2]


def exact_candidates(q: str) -> list[str]:
    names = set(re.findall(r"[a-z][a-z0-9]*(?:[-_][a-z0-9]+)+", q.lower()))
    names |= set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*(?=\()", q))
    names |= set(re.findall(r"[\w./-]+\.(?:c|h|py|js|ts|go|rs|java|conf)", q.lower()))
    return [n.lower() for n in names]


def verify_claims(claims: list[dict], valid_refs: set[str]) -> list[dict]:
    """Drop any claim without at least one valid citation; strip invalid refs from the rest."""
    out = []
    for c in claims or []:
        refs = [r for r in c.get("evidence", []) if r in valid_refs]
        if c.get("text") and refs:
            out.append({"text": c["text"].strip(), "evidence": refs})
    return out


def select_governing(rows: list[dict]) -> tuple[dict | None, list[dict]]:
    """Latest live decision governs; everything else is history."""
    live = sorted([r for r in rows if r["decision"]["status"] in LIVE], key=lambda r: r["decision"]["decided_on"] or "", reverse=True)
    gov = live[0] if live else None
    history = [r for r in rows if r is not gov]
    return gov, history


class GraphRAG:
    def __init__(self, db: Neo4jDB, llm: LLM | None = None) -> None:
        self.db, self.llm = db, llm or get_llm()

    # ---- steps -------------------------------------------------------------
    def normalize(self, question: str, lang: str) -> str:
        if lang in ("hi", "hinglish"):
            return translate_to_english(self.llm, question)
        return question

    def link_entities(self, q: str) -> list[dict]:
        found: dict[str, dict] = {}
        names = exact_candidates(q)
        if names:
            for r in self.db.run(Q.ENTITY_EXACT, names=names):
                found[r["id"]] = r
        kws = keywords(q)
        if kws:
            try:
                for r in self.db.run(Q.ENTITY_FULLTEXT, q=" OR ".join(kws[:8]), k=5):
                    found.setdefault(r["id"], r)
            except Exception:
                pass
        return sorted(found.values(), key=lambda r: r["score"], reverse=True)[:3]

    def fetch(self, entity_ids: list[str]) -> list[dict]:
        return [r for r in self.db.run(Q.DECISIONS_BY_ENTITY, entity_ids=entity_ids)] if entity_ids else []

    def vector_fallback(self, emb: list[float]) -> tuple[list[dict], float]:
        hits = self.db.run(Q.DECISION_VECTOR, k=5, embedding=emb)
        if not hits or hits[0]["score"] < 0.80:
            return [], 0.0
        return self.db.run(Q.DECISIONS_BY_IDS, ids=[h["id"] for h in hits[:3]]), hits[0]["score"]

    def promote_replacements(self, rows: list[dict]) -> tuple[list[dict], list[str]]:
        """If a matched decision was superseded and its replacement is not in the set, fetch the replacement."""
        have = {r["decision"]["id"] for r in rows}
        notes, missing = [], []
        for r in rows:
            d = r["decision"]
            if d["status"] in ("SUPERSEDED", "REVERSED") and r["superseded_by"]:
                rep = r["superseded_by"][0]
                notes.append(f"The closest match, “{d['title']}” ({(d['decided_on'] or '')[:10]}), was {d['status'].lower()} "
                             f"on {(rep.get('decided_on') or '')[:10]} by “{rep['title']}”. Showing the current decision.")
                if rep["id"] not in have:
                    missing.append(rep["id"])
        if missing:
            rows = rows + self.db.run(Q.DECISIONS_BY_IDS, ids=missing)
        return rows, notes

    def evidence_pack(self, row: dict, limit: int = 8) -> list[EvidenceItem]:
        seen, items = set(), []
        for e in sorted((e for e in row["evidence"] if e.get("id")), key=lambda e: e.get("date") or ""):
            if e["id"] in seen:
                continue
            seen.add(e["id"])
            items.append(e)
        items = items[:limit]
        return [EvidenceItem(ref=f"E{i+1}", id=e["id"], kind=e["kind"], url=e.get("url") or "", date=e.get("date") or "",
                             author=e.get("author") or "", snippet=e.get("snippet") or "", quote=e.get("quote") or "")
                for i, e in enumerate(items)]

    def generate(self, question: str, decision: dict, evidence: list[EvidenceItem]) -> str:
        pack = "\n".join(f"[{e.ref}] {e.kind} {e.date[:10]} by {e.author}: {(e.quote or e.snippet)[:500]}" for e in evidence)
        user = (f"QUESTION: {question}\n\nDECISION: {decision['title']}\nSummary: {decision['summary']}\n"
                f"Rationale: {decision['rationale']}\nRejected alternatives: {decision.get('alternatives_rejected')}\n"
                f"Decided on: {decision['decided_on']}\n\nEVIDENCE PACK:\n{pack}")
        claims = verify_claims(self.llm.complete_json(GEN_SYSTEM, user, 900).get("claims", []), {e.ref for e in evidence})
        return " ".join(f"{c['text']} [{', '.join(c['evidence'])}]" for c in claims)

    # ---- main --------------------------------------------------------------
    def answer(self, question: str, lang: str = "en") -> AnswerResponse:
        t0 = time.time()
        q = self.normalize(question, lang)
        ents = self.link_entities(q)
        entity_ids = [e["id"] for e in ents]
        hops = 1
        rows = self.fetch(entity_ids)
        if not rows:
            rows, _ = self.vector_fallback(embed([q])[0])
            hops = 2
            if rows:
                entity_ids = sorted({i for r in rows for i in r["entity_ids"]})
        if not rows:
            return self.refuse(question, entity_ids, "No decision in the graph governs the entities named in this question.", t0)
        rows, notes = self.promote_replacements(rows)
        gov, history = select_governing(rows)
        if not gov:
            return self.refuse(question, entity_ids, "Every recorded decision for this entity was superseded or reversed, and no replacement was found.", t0, history=history)
        d = gov["decision"]
        evidence = self.evidence_pack(gov)
        answer = self.generate(question, d, evidence) if evidence else ""
        if not answer:
            return self.refuse(question, entity_ids, "The evidence could not support a cited answer.", t0, history=history)
        if gov["supersedes"]:
            notes.append("This decision replaced: " + "; ".join(f"“{o['title']}” ({(o['decided_on'] or '')[:10]})" for o in gov["supersedes"]) + ".")
        effective_entity_ids = gov["entity_ids"] or entity_ids
        decided_on = d.get("decided_on") or ""
        if effective_entity_ids and decided_on:
            drift = self.db.run(Q.DRIFT_COUNT, entity_ids=effective_entity_ids, after=decided_on)[0]["n"]
            currency_unknown = False
        elif effective_entity_ids and not decided_on:
            # Document-sourced decision with no date — can't measure drift
            drift = 0
            currency_unknown = True
        else:
            drift = 0
            currency_unknown = True
        n_sources = len({e.kind for e in evidence})
        f = Factors(
            directness=1.0 if d.get("explicit_rationale") else 0.5,
            corroboration=conf.corroboration_score(n_sources),
            agreement=float(d.get("agreement") or 0),
            currency=0.5 if currency_unknown else conf.currency_score(drift),
            distance=conf.distance_score(hops),
        )
        c = conf.build(f, drift, n_sources, currency_unknown=currency_unknown)
        if c.label == "No answer":
            return self.refuse(question, entity_ids, f"Confidence {c.score} is below the refusal threshold.", t0, history=history, c=c)
        return AnswerResponse(
            question=question, status="answered", answer=answer, decision=d,
            superseded_notice=" ".join(notes) or None,
            replaced_by=(gov["superseded_by"][0] if gov["superseded_by"] else None),
            evidence=evidence, person_to_ask=self.person(gov, gov["entity_ids"] or entity_ids),
            history=[r["decision"] for r in history], confidence=c,
            graph=self.graph_payload(rows, {e["id"]: e["name"] for e in ents}),
            latency_ms=int((time.time() - t0) * 1000),
            llm_model=self.llm.model,
        )

    def person(self, gov: dict, entity_ids: list[str]) -> dict | None:
        if gov["people"]:
            return {"id": gov["people"][0], "reason": "Made or approved this decision"}
        top = self.db.run(Q.TOP_CONTRIBUTOR, entity_ids=entity_ids)
        if top:
            t = top[0]
            return {"id": t["id"], "name": t["name"], "reason": f"Most commits to this entity ({t['commits']}); last active {(t['last_active'] or '')[:10]}"}
        return None

    def refuse(self, question: str, entity_ids: list[str], reason: str, t0: float, history: list[dict] | None = None, c: Confidence | None = None) -> AnswerResponse:
        changers = self.db.run(Q.LAST_CHANGERS, entity_ids=entity_ids) if entity_ids else []
        try:
            related = self.db.run(Q.RELATED_DISCUSSIONS, k=3, embedding=embed([question])[0])
        except Exception:
            related = []
        top = self.db.run(Q.TOP_CONTRIBUTOR, entity_ids=entity_ids) if entity_ids else []
        return AnswerResponse(
            question=question, status="refused", refusal_reason=reason, confidence=c or Confidence(score=0.0, label="No answer", reasons=[reason]),
            related=[{"type": "last_change", **x} for x in changers] + [{"type": "discussion", **x} for x in related],
            person_to_ask=({"id": top[0]["id"], "name": top[0]["name"], "reason": "Most commits to this entity"} if top else None),
            history=[r["decision"] for r in (history or [])], latency_ms=int((time.time() - t0) * 1000))

    @staticmethod
    def graph_payload(rows: list[dict], entity_names: dict[str, str]) -> dict:
        nodes: dict[str, dict] = {}
        rels: list[dict] = []
        for r in rows:
            d = r["decision"]
            nodes[d["id"]] = {"id": d["id"], "label": d["title"], "type": "Decision", "status": d["status"]}
            for eid in r["entity_ids"]:
                nodes.setdefault(eid, {"id": eid, "label": entity_names.get(eid, eid), "type": "Entity"})
                rels.append({"from": d["id"], "to": eid, "type": "GOVERNS"})
            for e in r["evidence"]:
                if e.get("id"):
                    nodes.setdefault(e["id"], {"id": e["id"], "label": f"{e['kind']} {(e.get('date') or '')[:10]}", "type": e["kind"]})
                    rels.append({"from": d["id"], "to": e["id"], "type": "EVIDENCED_BY"})
            for s in r["superseded_by"]:
                nodes.setdefault(s["id"], {"id": s["id"], "label": s["title"], "type": "Decision", "status": "ACTIVE"})
                rels.append({"from": s["id"], "to": d["id"], "type": "SUPERSEDES"})
        return {"nodes": list(nodes.values()), "rels": rels}
