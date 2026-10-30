import { Link } from 'react-router-dom'
import EvidenceThread from '../components/EvidenceThread.jsx'
import Button from '../components/Button.jsx'
import Badge from '../components/Badge.jsx'
import StatsStrip from '../components/StatsStrip.jsx'
import './Landing.css'

/* ── Section 1: Hero ──────────────────────────────────────
   Asymmetric: copy left, animated evidence trail right.
   The SVG is the ONE memorable element — copy stays quiet.
   -------------------------------------------------------- */
function Hero() {
  return (
    <section className="hero" aria-labelledby="hero-heading">
      <div className="container hero__inner">
        <div className="hero__copy">
          <p className="hero__eyebrow">Nebius × NVIDIA Global AI Hackathon · Coding and Agentic Engineering</p>
          <h1 id="hero-heading" className="hero__heading">
            Connect code to the decisions that shaped it.
          </h1>
          <p className="hero__body">
            IntentLens answers "why is the code like this?" with a cited chain of evidence.
            Every answer traces back through a decision, a discussion, a person, and a date.
            It refuses rather than guesses when the graph has no answer.
          </p>
          <div className="hero__actions">
            <Button as={Link} to="/ask" variant="primary" size="lg">
              Ask the codebase
            </Button>
            <Button as={Link} to="/how" variant="ghost" size="lg">
              See how it works
            </Button>
          </div>
        </div>

        <figure className="hero__figure" aria-label="Sample evidence trail illustration">
          <div className="hero__sample-label" aria-hidden="true">Sample answer</div>
          <EvidenceThread size="lg" animated={true} decorative={false} />
          <figcaption className="hero__sample-caption">
            A question about <code>replication.c</code> traces to a decision, the PR discussion,
            the engineer who approved it, and the date it merged.
          </figcaption>
        </figure>
      </div>
    </section>
  )
}

/* ── Section 2: The problem ───────────────────────────────
   Four failure modes. Not numbered (they are not a sequence).
   -------------------------------------------------------- */
const FAILURE_MODES = [
  {
    problem: 'Search finds mentions, not decisions.',
    response: 'IntentLens mines the decision behind a change and cites the exact quote from the discussion.',
  },
  {
    problem: 'Docs drift. The code changes, the docs stay wrong.',
    response: 'The graph is built from commits and PRs, so it reflects what actually happened, not what was planned.',
  },
  {
    problem: 'A reversed decision looks as authoritative as a current one.',
    response: 'Every answer checks supersession status. A reversed decision is shown as history, never as the current answer.',
  },
  {
    problem: 'Incidents are not linked to the code that caused them.',
    response: 'IntentLens stores Incident nodes and connects them to the affected entities — planned for ingestion from post-mortems.',
  },
]

function Problem() {
  return (
    <section className="problem" aria-labelledby="problem-heading">
      <div className="container">
        <h2 id="problem-heading" className="section-heading">
          When the senior engineer leaves, the reasoning leaves too.
        </h2>
        <p className="section-subheading">
          The tools we have today — search, wikis, comments — find text. They do not find decisions.
        </p>
        <div className="problem__grid">
          {FAILURE_MODES.map(({ problem, response }) => (
            <div key={problem} className="problem__item">
              <p className="problem__symptom">{problem}</p>
              <p className="problem__answer">{response}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ── Section 3: Three signature capabilities ─────────────
   Small illustrative UI fragments instead of stock icons.
   -------------------------------------------------------- */
function CapabilityEvidenceFragment() {
  return (
    <div className="cap-fragment cap-fragment--evidence" aria-label="Evidence chain illustration">
      <div className="cap-fragment__answer">
        Redis uses a 1 MB backlog to allow partial resyncs after brief disconnections.
        <span className="cap-fragment__cite">E1</span>
      </div>
      <div className="cap-fragment__evidence-item">
        <span className="cap-fragment__kind">Commit</span>
        <span className="cap-fragment__mono">07888202</span>
        <span className="cap-fragment__snippet">Add replication backlog of 1mb by default</span>
      </div>
    </div>
  )
}

function CapabilitySupersessionFragment() {
  return (
    <div className="cap-fragment cap-fragment--supersession" aria-label="Supersession banner illustration">
      <div className="cap-fragment__banner">
        This decision was superseded on 2016-07-22.
        <span className="cap-fragment__link">See replacement</span>
      </div>
      <div className="cap-fragment__old">
        <s>Avoid simultaneous RDB and AOF child process</s>
        <Badge variant="superseded" size="sm">Superseded</Badge>
      </div>
      <div className="cap-fragment__new">
        Delay BGSAVE only when AOF rewriting is active
        <Badge variant="active" size="sm">Active</Badge>
      </div>
    </div>
  )
}

function CapabilityRefusalFragment() {
  return (
    <div className="cap-fragment cap-fragment--refusal" aria-label="Refusal state illustration">
      <div className="cap-fragment__refusal-heading">No recorded rationale found</div>
      <p className="cap-fragment__refusal-body">
        The graph does not contain a decision that explains this, so IntentLens will not guess.
      </p>
      <div className="cap-fragment__person">
        Last person to work on it: <span className="cap-fragment__mono">antirez</span>
      </div>
    </div>
  )
}

const CAPABILITIES = [
  {
    title: 'Evidence on every answer',
    body: 'Every sentence cites an evidence ID. Claims without a valid citation are dropped before the answer reaches you.',
    fragment: <CapabilityEvidenceFragment />,
  },
  {
    title: 'Supersession awareness',
    body: 'The graph tracks when one decision replaces another. You always see the current decision, with history below.',
    fragment: <CapabilitySupersessionFragment />,
  },
  {
    title: 'Honest refusal',
    body: 'If no decision governs the entity or confidence is below threshold, the system refuses and tells you who to ask instead.',
    fragment: <CapabilityRefusalFragment />,
  },
]

function Capabilities() {
  return (
    <section className="capabilities" aria-labelledby="cap-heading">
      <div className="container">
        <h2 id="cap-heading" className="section-heading">Three things it does that search cannot.</h2>
        <div className="capabilities__grid">
          {CAPABILITIES.map(({ title, body, fragment }) => (
            <div key={title} className="capability">
              <div className="capability__fragment">{fragment}</div>
              <h3 className="capability__title">{title}</h3>
              <p className="capability__body">{body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ── Section 4: Pipeline SVG ─────────────────────────────
   Inline SVG, no external images.
   -------------------------------------------------------- */
function PipelineDiagram() {
  const steps = [
    { id: 'ingest',     label: 'Ingest',           sub: 'git + GitHub + docs' },
    { id: 'graph',      label: 'Build graph',       sub: 'Neo4j AuraDB' },
    { id: 'mine',       label: 'Mine decisions',    sub: 'LLM + quote verify' },
    { id: 'supersede',  label: 'Detect supersession', sub: '3-signal engine' },
    { id: 'answer',     label: 'Answer with confidence', sub: '5-factor score' },
  ]

  const W = 900, H = 120
  const stepW = W / steps.length
  const cy = H / 2
  const r = 22

  return (
    <section className="pipeline" aria-labelledby="pipeline-heading">
      <div className="container">
        <h2 id="pipeline-heading" className="section-heading">How it works in five steps.</h2>
        <div className="pipeline__svg-wrap">
          <svg
            viewBox={`0 0 ${W} ${H}`}
            width="100%"
            aria-label="Pipeline: Ingest, Build graph, Mine decisions, Detect supersession, Answer with confidence"
            role="img"
            className="pipeline__svg"
          >
            <title>IntentLens pipeline diagram</title>

            {/* Connecting lines */}
            {steps.slice(0, -1).map((_, i) => {
              const x1 = stepW * i + stepW / 2 + r
              const x2 = stepW * (i + 1) + stepW / 2 - r
              return (
                <line
                  key={i}
                  x1={x1} y1={cy} x2={x2} y2={cy}
                  stroke="var(--line)" strokeWidth="1.5" strokeDasharray="4 3"
                />
              )
            })}

            {/* Step nodes */}
            {steps.map((step, i) => {
              const cx = stepW * i + stepW / 2
              const isLast = i === steps.length - 1
              return (
                <g key={step.id}>
                  <circle
                    cx={cx} cy={cy} r={r}
                    fill={isLast ? 'var(--accent-soft)' : 'var(--surface-2)'}
                    stroke={isLast ? 'var(--accent)' : 'var(--line)'}
                    strokeWidth="1.5"
                  />
                  <text
                    x={cx} y={cy + 1}
                    textAnchor="middle" dominantBaseline="middle"
                    fontSize="11" fontFamily="var(--font-ui)" fontWeight="500"
                    fill={isLast ? 'var(--accent)' : 'var(--ink)'}
                  >
                    {i + 1}
                  </text>
                  <text
                    x={cx} y={cy + r + 16}
                    textAnchor="middle"
                    fontSize="11" fontFamily="var(--font-ui)" fontWeight="500"
                    fill="var(--ink)"
                  >
                    {step.label}
                  </text>
                  <text
                    x={cx} y={cy + r + 30}
                    textAnchor="middle"
                    fontSize="9.5" fontFamily="var(--font-ui)"
                    fill="var(--muted)"
                  >
                    {step.sub}
                  </text>
                </g>
              )
            })}
          </svg>
        </div>
      </div>
    </section>
  )
}

/* ── Section 5: Live stats ───────────────────────────────
   Real numbers from GET /stats. Graceful empty state.
   -------------------------------------------------------- */
function LiveStats() {
  return (
    <section className="live-stats" aria-labelledby="stats-heading">
      <div className="container">
        <h2 id="stats-heading" className="section-heading section-heading--center">
          What is in the graph right now.
        </h2>
        <p className="section-subheading section-subheading--center">
          These are live counts from the loaded graph — not marketing estimates.
        </p>
        <StatsStrip />
      </div>
    </section>
  )
}

/* ── Section 6: Built on ─────────────────────────────────
   Text only. No external image hosts.
   -------------------------------------------------------- */
const BUILT_ON = [
  { name: 'Neo4j AuraDB', role: 'Knowledge graph' },
  { name: 'GraphRAG', role: 'Graph-first retrieval' },
  { name: 'NVIDIA Nemotron 3 Ultra', role: 'LLM via Nebius Token Factory' },
  { name: 'FastAPI', role: 'Backend API' },
  { name: 'React 18', role: 'Frontend' },
]

function BuiltOn() {
  return (
    <section className="built-on" aria-labelledby="builton-heading">
      <div className="container">
        <p id="builton-heading" className="built-on__title">Built with</p>
        <ul className="built-on__list" role="list">
          {BUILT_ON.map(({ name, role }) => (
            <li key={name} className="built-on__item">
              <span className="built-on__name">{name}</span>
              <span className="built-on__role">{role}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}

/* ── Section 7: Powered by NVIDIA Nemotron ───────────────
   Factual and modest. No invented claims.
   -------------------------------------------------------- */
function NvidiaSection() {
  return (
    <section className="india-section" aria-labelledby="nvidia-heading">
      <div className="container">
        <div className="india-section__inner">
          <div className="india-section__copy">
            <h2 id="nvidia-heading" className="india-section__heading">
              Powered by NVIDIA Nemotron 3 Ultra on Nebius Token Factory.
            </h2>
            <p>
              Every LLM call in IntentLens — two-pass decision mining, supersession pair
              classification, grounded answer generation, and multilingual query
              normalisation — runs through Nemotron 3 Ultra served via Nebius Token Factory.
            </p>
            <p>
              Nemotron's strong reasoning capability is critical for the supersession
              classification task: judging whether one engineering decision truly overrides
              another requires reading both decisions and their rationale, then making a
              precise semantic distinction between "refines", "contradicts", and "unrelated".
            </p>
            <p>
              Questions can be asked in Hinglish or Hindi — Nemotron translates them to
              English while preserving code identifiers and config keys exactly as written,
              so the entity-linking step still works correctly.
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}

/* ── Section 8: Final CTA ────────────────────────────────── */
function FinalCta() {
  return (
    <section className="final-cta" aria-labelledby="cta-heading">
      <div className="container">
        <div className="final-cta__inner">
          <h2 id="cta-heading" className="final-cta__heading">
            Ask your first question.
          </h2>
          <p className="final-cta__body">
            Load the redis/redis subsystem, ask why a configuration key exists,
            and trace the answer back to the commit that introduced it.
          </p>
          <div className="final-cta__actions">
            <Button as={Link} to="/ask" variant="primary" size="lg">
              Ask the codebase
            </Button>
            <Button as={Link} to="/about" variant="secondary" size="lg">
              Read about the project
            </Button>
          </div>
        </div>
      </div>
    </section>
  )
}

/* ── Page ─────────────────────────────────────────────── */
export default function Landing() {
  return (
    <main id="main">
      <Hero />
      <Problem />
      <Capabilities />
      <PipelineDiagram />
      <LiveStats />
      <BuiltOn />
      <NvidiaSection />
      <FinalCta />
    </main>
  )
}
