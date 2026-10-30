import React, { useCallback, useRef, useState } from 'react'
import Badge from './Badge.jsx'
import './AnswerCard.css'

const fmt = (d) => (d ? String(d).slice(0, 10) : '—')

const EVIDENCE_ICONS = {
  Commit:      '⬡',  // using geometric shapes, not emoji, for cleanliness
  PullRequest: '⬡',
  Issue:       '○',
  Comment:     '◇',
  Document:    '□',
}

const FACTOR_LABELS = {
  directness:    'Directness',
  corroboration: 'Corroboration',
  agreement:     'Agreement',
  currency:      'Currency',
  distance:      'Distance',
}

const FACTOR_WEIGHTS = {
  directness:    0.30,
  corroboration: 0.25,
  agreement:     0.20,
  currency:      0.15,
  distance:      0.10,
}

/* ── Citation chip — clicking scrolls to and highlights evidence ──── */
function CitationChip({ refId, url, onCite }) {
  return (
    <button
      className="cite-chip"
      onClick={() => onCite(refId)}
      aria-label={`Jump to evidence ${refId}`}
      type="button"
    >
      {refId}
    </button>
  )
}

/* ── Answer prose with inline citation chips ─────────────────────── */
function AnswerProse({ text, evidence, onCite }) {
  const parts = text.split(/(\[E\d+(?:,\s*E\d+)*\])/g)
  return (
    <p className="ac-answer">
      {parts.map((part, i) => {
        const match = part.match(/^\[(E\d+(?:,\s*E\d+)*)\]$/)
        if (!match) return <span key={i}>{part}</span>
        return match[1].split(/,\s*/).map((ref) => (
          <CitationChip key={`${i}-${ref}`} refId={ref} onCite={onCite} />
        ))
      })}
    </p>
  )
}

/* ── Confidence meter with five factor bars ─────────────────────── */
function ConfidenceMeter({ confidence }) {
  const { score, label, factors, reasons } = confidence
  const pct = Math.round(score * 100)

  const labelVariant = {
    High: 'active',
    Medium: 'superseded',
    Low: 'refused',
    'No answer': 'refused',
  }[label] || 'default'

  return (
    <div className="ac-confidence" data-testid="confidence-meter">
      <div className="ac-confidence__header">
        <span className="ac-confidence__title">Confidence</span>
        <Badge variant={labelVariant}>{label} — {pct}%</Badge>
      </div>

      {/* Overall bar */}
      <div
        className="ac-confidence__bar-wrap"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Overall confidence: ${pct}%`}
      >
        <div className="ac-confidence__bar" style={{ width: `${pct}%` }} />
      </div>

      {/* Five factor breakdown */}
      {factors && (
        <div className="ac-confidence__factors">
          {Object.entries(FACTOR_WEIGHTS).map(([key, weight]) => {
            const value = factors[key] ?? 0
            const contrib = Math.round(value * weight * 100)
            const barPct = Math.round(value * 100)
            return (
              <div key={key} className="ac-factor">
                <div className="ac-factor__meta">
                  <span className="ac-factor__name">{FACTOR_LABELS[key]}</span>
                  <span className="ac-factor__weight">{Math.round(weight * 100)}%</span>
                  <span className="ac-factor__contrib">{contrib}pts</span>
                </div>
                <div
                  className="ac-factor__bar-wrap"
                  role="progressbar"
                  aria-valuenow={barPct}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label={`${FACTOR_LABELS[key]}: ${barPct}%`}
                >
                  <div className="ac-factor__bar" style={{ width: `${barPct}%` }} />
                </div>
              </div>
            )
          })}
        </div>
      )}

      {reasons && reasons.length > 0 && (
        <ul className="ac-confidence__reasons">
          {reasons.map((r) => <li key={r}>{r}</li>)}
        </ul>
      )}
    </div>
  )
}

/* ── Evidence rail ───────────────────────────────────────────────── */
function EvidenceRail({ evidence, highlightedRef }) {
  return (
    <ol className="ac-rail" aria-label="Evidence chain">
      {evidence.map((e) => (
        <li
          key={e.id}
          id={`evidence-${e.ref}`}
          className={`ac-rail__item${highlightedRef === e.ref ? ' ac-rail__item--highlighted' : ''}`}
          data-ref={e.ref}
          aria-label={`${e.ref}: ${e.kind} by ${e.author || 'unknown'} on ${fmt(e.date)}`}
        >
          <span className="ac-rail__ref" aria-hidden="true">{e.ref}</span>
          <div className="ac-rail__body">
            <div className="ac-rail__meta">
              <span className="ac-rail__kind">{e.kind}</span>
              <span className="ac-rail__mono">
                {e.id.length > 16 ? e.id.slice(0, 12) + '…' : e.id}
              </span>
              {e.author && <span className="ac-rail__author">{e.author}</span>}
              <span className="ac-rail__date">{fmt(e.date)}</span>
              {e.url && (
                <a
                  href={e.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="ac-rail__link"
                  aria-label={`Open ${e.kind} in new tab`}
                >
                  ↗
                </a>
              )}
            </div>
            {(e.quote || e.snippet) && (
              <p className="ac-rail__quote">{e.quote || e.snippet}</p>
            )}
          </div>
        </li>
      ))}
    </ol>
  )
}

/* ── Decision card ───────────────────────────────────────────────── */
function DecisionCard({ decision }) {
  const statusVariant = {
    ACTIVE: 'active',
    SUPERSEDED: 'superseded',
    REVERSED: 'reversed',
    UNCERTAIN: 'uncertain',
  }[decision.status] || 'default'

  return (
    <div className="ac-decision" data-testid="decision-card">
      <div className="ac-decision__header">
        <h3 className="ac-decision__title">{decision.title}</h3>
        <Badge variant={statusVariant}>{decision.status.toLowerCase()}</Badge>
      </div>
      {decision.summary && (
        <p className="ac-decision__summary">{decision.summary}</p>
      )}
      <dl className="ac-decision__meta">
        {decision.decided_on && (
          <div>
            <dt>Decided</dt>
            <dd>{fmt(decision.decided_on)}</dd>
          </div>
        )}
        {decision.alternatives_rejected && decision.alternatives_rejected.length > 0 && (
          <div>
            <dt>Considered and rejected</dt>
            <dd>{decision.alternatives_rejected.join(', ')}</dd>
          </div>
        )}
        {decision.explicit_rationale === false && (
          <div>
            <dt>Rationale</dt>
            <dd className="ac-decision__inferred">Inferred — not explicitly stated in the source.</dd>
          </div>
        )}
      </dl>
    </div>
  )
}

/* ── Person to ask ───────────────────────────────────────────────── */
function PersonCard({ person }) {
  return (
    <div className="ac-person" data-testid="person-card">
      <span className="ac-person__icon" aria-hidden="true">◎</span>
      <div>
        <div className="ac-person__name">{person.name || person.id}</div>
        <div className="ac-person__reason">{person.reason}</div>
      </div>
    </div>
  )
}

/* ── History list ────────────────────────────────────────────────── */
function HistoryList({ history }) {
  if (!history || history.length === 0) return null
  return (
    <div className="ac-history" data-testid="history-list">
      <h4 className="ac-history__title">Earlier decisions</h4>
      <ul>
        {history.map((h) => {
          const isSuperseded = h.status === 'SUPERSEDED' || h.status === 'REVERSED'
          const statusVariant = {
            ACTIVE: 'active', SUPERSEDED: 'superseded',
            REVERSED: 'reversed', UNCERTAIN: 'uncertain',
          }[h.status] || 'default'
          return (
            <li key={h.id} className={`ac-history__item${isSuperseded ? ' ac-history__item--struck' : ''}`}>
              {isSuperseded ? (
                <s className="ac-history__struck">{h.title}</s>
              ) : (
                <span className="ac-history__title-text">{h.title}</span>
              )}
              <Badge variant={statusVariant} size="sm">{h.status.toLowerCase()}</Badge>
              <span className="ac-history__date">{fmt(h.decided_on)}</span>
              {!isSuperseded && (
                <span className="ac-history__refined-label">
                  Earlier decision, refined by the one above
                </span>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

/* ── Copy / share bar ────────────────────────────────────────────── */
function ActionBar({ answer, question }) {
  const copy = () => {
    const text = `Q: ${question}\n\nA: ${answer.replace(/\[E\d+(?:,\s*E\d+)*\]/g, '')}`
    navigator.clipboard?.writeText(text)
  }

  const share = () => {
    const params = new URLSearchParams({ q: question })
    navigator.clipboard?.writeText(
      `${window.location.origin}/ask?${params.toString()}`
    )
  }

  return (
    <div className="ac-actions">
      <button className="ac-action-btn" onClick={copy} type="button" aria-label="Copy answer to clipboard">
        Copy answer
      </button>
      <button className="ac-action-btn" onClick={share} type="button" aria-label="Copy shareable link">
        Share link
      </button>
    </div>
  )
}

/* ── Superseded banner ───────────────────────────────────────────── */
function SupersededBanner({ notice, replacedBy }) {
  return (
    <div className="ac-banner" role="status" aria-live="polite" data-testid="superseded-banner">
      <span className="ac-banner__icon" aria-hidden="true">⚠</span>
      <div>
        <p className="ac-banner__text">{notice}</p>
        {replacedBy && (
          <p className="ac-banner__replacement">
            Current decision: <strong>{replacedBy.title}</strong>
            {replacedBy.decided_on && ` (${fmt(replacedBy.decided_on)})`}
          </p>
        )}
      </div>
    </div>
  )
}

/* ── Answered state ──────────────────────────────────────────────── */
function AnsweredView({ res }) {
  const railRef = useRef(null)
  const [highlightedRef, setHighlightedRef] = React.useState(null)

  const handleCite = useCallback((ref) => {
    // Scroll to and highlight the evidence item
    const el = document.getElementById(`evidence-${ref}`)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
    setHighlightedRef(ref)
    setTimeout(() => setHighlightedRef(null), 2500)
  }, [])

  return (
    <article className="ac-answered" data-testid="answered-view">
      {res.superseded_notice && (
        <SupersededBanner notice={res.superseded_notice} replacedBy={res.replaced_by} />
      )}

      <AnswerProse text={res.answer} evidence={res.evidence} onCite={handleCite} />
      <ActionBar answer={res.answer} question={res.question} />

      {res.decision && <DecisionCard decision={res.decision} />}
      {res.person_to_ask && <PersonCard person={res.person_to_ask} />}

      {res.evidence.length > 0 && (
        <section aria-label="Evidence chain" ref={railRef}>
          <h4 className="ac-section-title">Evidence chain</h4>
          <EvidenceRail evidence={res.evidence} highlightedRef={highlightedRef} />
        </section>
      )}

      <HistoryList history={res.history} />
      <ConfidenceMeter confidence={res.confidence} />
    </article>
  )
}

/* ── Refused state ───────────────────────────────────────────────── */
function RefusedView({ res }) {
  return (
    <article className="ac-refused" data-testid="refused-view">
      <div className="ac-refused__header">
        <span className="ac-refused__icon" aria-hidden="true">◉</span>
        <h2 className="ac-refused__heading">No recorded rationale found</h2>
      </div>
      <p className="ac-refused__reason">{res.refusal_reason}</p>
      <p className="ac-refused__note">
        The graph does not contain a decision that explains this. IntentLens will not guess.
      </p>

      {res.person_to_ask && (
        <div className="ac-refused__person">
          <span className="ac-refused__person-label">Last person to work on it</span>
          <PersonCard person={res.person_to_ask} />
        </div>
      )}

      {res.related && res.related.length > 0 && (
        <section aria-label="Closest related history">
          <h4 className="ac-section-title">Closest related history</h4>
          <ul className="ac-refused__related">
            {res.related.map((r) => (
              <li key={r.id} className="ac-refused__related-item">
                <div className="ac-refused__related-meta">
                  <span className="ac-refused__related-type">
                    {r.type === 'last_change' ? 'Last change' : 'Discussion'}
                  </span>
                  <span className="ac-refused__related-date">{fmt(r.date)}</span>
                  {r.author && <span className="ac-refused__related-author">{r.author}</span>}
                  {r.url && (
                    <a href={r.url} target="_blank" rel="noreferrer noopener" className="ac-rail__link">↗</a>
                  )}
                </div>
                <p className="ac-refused__related-text">{r.message || r.snippet}</p>
              </li>
            ))}
          </ul>
        </section>
      )}
    </article>
  )
}

/* ── Model badge ─────────────────────────────────────────────────── */
function ModelBadge({ model }) {
  if (!model) return null
  const label = (model.toLowerCase().includes('nemotron'))
    ? 'Nemotron 3 Ultra on Nebius Token Factory'
    : model
  return (
    <div className="ac-model-badge" title={`Full model: ${model}`} aria-label={`Answered by ${label}`}>
      <span className="ac-model-badge__dot" aria-hidden="true" />
      Answered by {label}
    </div>
  )
}

/* ── Main export ─────────────────────────────────────────────────── */
export default function AnswerCard({ res }) {
  if (res.status === 'refused') return <RefusedView res={res} />
  return (
    <>
      <AnsweredView res={res} />
      <ModelBadge model={res.llm_model} />
    </>
  )
}

