import './How.css'

/* ── Shared section wrapper ───────────────────────────────── */
function Section({ id, title, children }) {
  return (
    <section id={id} className="how-section">
      <h2 className="how-section__title">{title}</h2>
      {children}
    </section>
  )
}

/* ──────────────────────────────────────────────────────────
   1. Pipeline SVG
   Five stages in a left-to-right chain with labelled arrows.
   Uses CSS variables for colours so it respects both themes.
   ────────────────────────────────────────────────────────── */
const PIPELINE_STEPS = [
  { id: 'ingest',     label: 'Ingest',              sub: 'git · GitHub · docs' },
  { id: 'graph',      label: 'Build graph',          sub: 'Neo4j AuraDB' },
  { id: 'mine',       label: 'Mine decisions',       sub: 'Nemotron + quote verifier' },
  { id: 'supersede',  label: 'Detect supersession',  sub: '3-signal engine' },
  { id: 'answer',     label: 'Answer',               sub: '5-factor confidence' },
]

function PipelineSVG() {
  const W = 860, H = 110
  const stepW = W / PIPELINE_STEPS.length
  const cy = 40
  const r = 20

  return (
    <svg
      className="how-svg"
      viewBox={`0 0 ${W} ${H}`}
      aria-label="Pipeline diagram: five stages from Ingest through to Answer"
      role="img"
    >
      <title>IntentLens pipeline: Ingest → Build graph → Mine decisions → Detect supersession → Answer</title>

      {/* Connectors */}
      {PIPELINE_STEPS.slice(0, -1).map((_, i) => {
        const x1 = stepW * i + stepW / 2 + r + 2
        const x2 = stepW * (i + 1) + stepW / 2 - r - 2
        const mx = (x1 + x2) / 2
        return (
          <g key={i}>
            <line x1={x1} y1={cy} x2={x2} y2={cy} stroke="var(--line)" strokeWidth="1.5" />
            <polygon
              points={`${x2},${cy} ${x2 - 6},${cy - 4} ${x2 - 6},${cy + 4}`}
              fill="var(--line)"
            />
          </g>
        )
      })}

      {/* Step circles */}
      {PIPELINE_STEPS.map((step, i) => {
        const cx = stepW * i + stepW / 2
        const isLast = i === PIPELINE_STEPS.length - 1
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
              fontSize="11" fontFamily="var(--font-ui)" fontWeight="600"
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
              fontSize="9" fontFamily="var(--font-ui)"
              fill="var(--muted)"
            >
              {step.sub}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

/* ──────────────────────────────────────────────────────────
   2. Graph schema SVG
   Shows the main node types and relationship arrows.
   ────────────────────────────────────────────────────────── */
function GraphSchemaSVG() {
  // Node positions
  const nodes = [
    { id: 'entity',   label: 'Entity',      sub: 'File · Function · ConfigKey',  x: 80,  y: 70,  color: 'var(--entity)', r: 30 },
    { id: 'decision', label: 'Decision',    sub: 'status · title · rationale',   x: 260, y: 70,  color: 'var(--accent)', r: 30 },
    { id: 'commit',   label: 'Commit',      sub: 'sha · date · author',           x: 440, y: 40,  color: 'var(--muted)',  r: 26 },
    { id: 'pr',       label: 'PullRequest', sub: 'number · title · body',        x: 440, y: 110, color: 'var(--muted)',  r: 26 },
    { id: 'person',   label: 'Person',      sub: 'email · login',                x: 620, y: 70,  color: 'var(--refused)', r: 26 },
    { id: 'doc',      label: 'Document',    sub: 'path · section · text',        x: 260, y: 175, color: 'var(--muted)',  r: 26 },
  ]

  const edges = [
    { from: 'entity',   to: 'decision', label: '←GOVERNS',       bend: -1 },
    { from: 'decision', to: 'commit',   label: 'EVIDENCED_BY→',  bend: 0 },
    { from: 'decision', to: 'pr',       label: 'EVIDENCED_BY→',  bend: 0 },
    { from: 'person',   to: 'commit',   label: 'AUTHORED→',      bend: 0 },
    { from: 'person',   to: 'decision', label: 'MADE_BY←',       bend: 0 },
    { from: 'commit',   to: 'entity',   label: 'MODIFIES→',      bend: 0 },
    { from: 'decision', to: 'doc',      label: 'EVIDENCED_BY→',  bend: 0 },
  ]

  const getNode = id => nodes.find(n => n.id === id)

  return (
    <svg
      className="how-svg how-svg--schema"
      viewBox="0 0 720 230"
      aria-label="Graph schema showing Entity, Decision, Commit, PullRequest, Person and Document nodes and their relationships"
      role="img"
    >
      <title>IntentGraph schema: Entity → Decision → Evidence (Commit / PullRequest / Document) → Person</title>

      {/* Edges */}
      {edges.map((e, i) => {
        const n1 = getNode(e.from)
        const n2 = getNode(e.to)
        if (!n1 || !n2) return null
        const mx = (n1.x + n2.x) / 2
        const my = (n1.y + n2.y) / 2 + e.bend * 20
        const fontSize = 8
        return (
          <g key={i}>
            <line
              x1={n1.x} y1={n1.y} x2={n2.x} y2={n2.y}
              stroke="var(--line)" strokeWidth="1" strokeDasharray="3 2"
            />
            <text
              x={mx} y={my}
              textAnchor="middle" dominantBaseline="middle"
              fontSize={fontSize} fontFamily="var(--font-mono)"
              fill="var(--muted)"
            >
              {e.label}
            </text>
          </g>
        )
      })}

      {/* Nodes */}
      {nodes.map(n => (
        <g key={n.id}>
          <circle cx={n.x} cy={n.y} r={n.r} fill={n.color} opacity="0.15" stroke={n.color} strokeWidth="1.5" />
          <text
            x={n.x} y={n.y - 2}
            textAnchor="middle" dominantBaseline="middle"
            fontSize="10" fontFamily="var(--font-ui)" fontWeight="600"
            fill={n.color}
          >
            {n.label}
          </text>
          <text
            x={n.x} y={n.y + 11}
            textAnchor="middle"
            fontSize="8" fontFamily="var(--font-ui)"
            fill="var(--muted)"
          >
            {n.sub}
          </text>
        </g>
      ))}
    </svg>
  )
}

/* ──────────────────────────────────────────────────────────
   3. Supersession algorithm SVG
   Shows the three signals and a worked example.
   ────────────────────────────────────────────────────────── */
function SupersessionSVG() {
  return (
    <svg
      className="how-svg how-svg--supersession"
      viewBox="0 0 700 160"
      aria-label="Supersession detection: three signals — structural revert detection, semantic pair classification, and temporal status resolution"
      role="img"
    >
      <title>Three-signal supersession: Structural → Semantic → Temporal</title>

      {/* Three boxes */}
      {[
        { x: 20,  label: '① Structural', sub: 'Parses "This reverts commit SHA"\nLinks REVERTS edges', color: 'var(--reversed)' },
        { x: 253, label: '② Semantic',   sub: 'LLM classifies pairs:\nreinforces / refines / contradicts', color: 'var(--superseded)' },
        { x: 486, label: '③ Temporal',   sub: 'compute_statuses() resolves:\nACTIVE / SUPERSEDED / REVERSED', color: 'var(--active)' },
      ].map((box) => (
        <g key={box.x}>
          <rect
            x={box.x} y={10} width={194} height={80}
            fill="var(--surface-2)" stroke={box.color} strokeWidth="1.5" rx="6"
          />
          <text
            x={box.x + 97} y={38}
            textAnchor="middle"
            fontSize="11" fontFamily="var(--font-ui)" fontWeight="600"
            fill={box.color}
          >
            {box.label}
          </text>
          {box.sub.split('\n').map((line, i) => (
            <text
              key={i}
              x={box.x + 97} y={56 + i * 14}
              textAnchor="middle"
              fontSize="9" fontFamily="var(--font-ui)"
              fill="var(--muted)"
            >
              {line}
            </text>
          ))}
        </g>
      ))}

      {/* Arrows between boxes */}
      {[214, 447].map(x => (
        <g key={x}>
          <line x1={x} y1={50} x2={x + 35} y2={50} stroke="var(--line)" strokeWidth="1.5" />
          <polygon points={`${x + 35},50 ${x + 29},46 ${x + 29},54`} fill="var(--line)" />
        </g>
      ))}

      {/* Worked example */}
      <text x={20} y={120} fontSize="10" fontFamily="var(--font-ui)" fontWeight="600" fill="var(--muted)">
        Worked example:
      </text>
      <rect x={20} y={128} width={660} height={24} fill="var(--surface-2)" rx="4" />
      {[
        { x: 30,  label: '"Avoid simultaneous RDB+AOF"',  color: 'var(--superseded)', strike: true },
        { x: 270, label: 'SUPERSEDED BY',                  color: 'var(--muted)', strike: false },
        { x: 370, label: '"Delay BGSAVE only when AOF rewrites"', color: 'var(--active)', strike: false },
        { x: 630, label: '0.90 conf', color: 'var(--muted)', strike: false },
      ].map((item, i) => (
        <text
          key={i}
          x={item.x} y={143}
          fontSize="9" fontFamily="var(--font-ui)"
          fill={item.color}
          textDecoration={item.strike ? 'line-through' : 'none'}
        >
          {item.label}
        </text>
      ))}
    </svg>
  )
}

/* ──────────────────────────────────────────────────────────
   4. Confidence formula SVG
   Horizontal bar chart of the five weights.
   ────────────────────────────────────────────────────────── */
const CONFIDENCE_FACTORS = [
  { name: 'Directness',    weight: 0.30, desc: '1.0 if rationale is explicitly stated; 0.5 if inferred' },
  { name: 'Corroboration', weight: 0.25, desc: '0.4 one source · 0.7 two sources · 1.0 three or more' },
  { name: 'Agreement',     weight: 0.20, desc: 'Cosine similarity between two independent mining passes' },
  { name: 'Currency',      weight: 0.15, desc: '1 − min(1, drift_commits / 5) — code still matches decision' },
  { name: 'Distance',      weight: 0.10, desc: '1 − (hops − 1) / MAX_GRAPH_HOPS' },
]

function ConfidenceSVG() {
  const barW = 300
  return (
    <svg
      className="how-svg how-svg--confidence"
      viewBox="0 0 680 170"
      aria-label="Confidence score formula: five weighted factors"
      role="img"
    >
      <title>Confidence = 0.30×Directness + 0.25×Corroboration + 0.20×Agreement + 0.15×Currency + 0.10×Distance</title>
      {CONFIDENCE_FACTORS.map((f, i) => {
        const y = 18 + i * 30
        const fillW = barW * f.weight / 0.30  // scale so max weight fills bar
        return (
          <g key={f.name}>
            <text x={0} y={y + 10} fontSize="10" fontFamily="var(--font-ui)" fontWeight="500" fill="var(--ink)">{f.name}</text>
            <rect x={120} y={y} width={barW} height={16} rx="3" fill="var(--surface-2)" />
            <rect x={120} y={y} width={fillW} height={16} rx="3" fill="var(--accent)" opacity="0.7" />
            <text x={120 + fillW + 6} y={y + 11} fontSize="10" fontFamily="var(--font-mono)" fill="var(--accent)">{Math.round(f.weight * 100)}%</text>
            <text x={460} y={y + 11} fontSize="8.5" fontFamily="var(--font-ui)" fill="var(--muted)">{f.desc}</text>
          </g>
        )
      })}
      <text x={0} y={170} fontSize="9" fontFamily="var(--font-mono)" fill="var(--muted)">
        High ≥ 0.75 · Medium ≥ 0.55 · Low ≥ REFUSAL_THRESHOLD (0.35) · No answer below
      </text>
    </svg>
  )
}

/* ── Step-by-step explanation ─────────────────────────────── */
const QUESTION_STEPS = [
  {
    n: '1',
    title: 'Normalise language',
    body: 'Hindi or Hinglish questions are translated to English by Nemotron 3 Ultra (via Nebius Token Factory) before any further processing. Code identifiers, config keys, and function names are preserved unchanged.',
  },
  {
    n: '2',
    title: 'Link entities',
    body: 'Entity names in the question are extracted using exact-string matching (hyphenated identifiers, function names, file extensions) and then a full-text index query against all Entity nodes.',
  },
  {
    n: '3',
    title: 'Traverse the graph',
    body: 'Governing decisions are fetched via GOVERNS edges (hop 1). If nothing is found, a vector search over decision embeddings provides a fallback (hop 2). Only decisions within MAX_GRAPH_HOPS are considered.',
  },
  {
    n: '4',
    title: 'Check supersession',
    body: 'Every matched decision is checked for SUPERSEDED or REVERSED status. If superseded, the replacement is fetched and promoted. Stale decisions appear only in the history section.',
  },
  {
    n: '5',
    title: 'Build an evidence pack',
    body: 'Up to eight evidence items (commits, PRs, issues, comments, documents) are assembled with stable refs E1…E8. Each item carries the verbatim quote used in mining.',
  },
  {
    n: '6',
    title: 'Generate and verify',
    body: 'The LLM produces JSON claims, each citing evidence refs. Any claim without a valid citation is dropped. The remaining claims form the answer string.',
  },
  {
    n: '7',
    title: 'Compute confidence',
    body: 'A five-factor score is computed from graph facts — not from the LLM\'s self-assessment. If the score falls below REFUSAL_THRESHOLD, the system refuses and returns last changers instead.',
  },
]

export default function How() {
  return (
    <main id="main" className="how-page">
      <div className="how-hero container">
        <h1 className="how-hero__title">How IntentLens works</h1>
        <p className="how-hero__body">
          Every answer traces back through a knowledge graph of commits, decisions, and people.
          This page explains the five-stage pipeline, the graph schema, and how confidence is scored.
        </p>
        {/* Jump links */}
        <nav className="how-toc" aria-label="Page contents">
          <a href="#pipeline">Pipeline</a>
          <a href="#schema">Graph schema</a>
          <a href="#question-path">Question path</a>
          <a href="#supersession">Supersession</a>
          <a href="#confidence">Confidence</a>
        </nav>
      </div>

      <div className="container">

        {/* 1. Pipeline */}
        <Section id="pipeline" title="Five-stage pipeline">
          <div className="how-svg-wrap">
            <PipelineSVG />
          </div>
          <ol className="how-pipeline-list">
            {[
              { label: 'Ingest', body: 'Git history (via PyDriller) and GitHub PRs/issues (GraphQL API) are cached as JSONL. Design docs and redis.conf comment blocks are extracted as Document nodes. All stages are resumable.' },
              { label: 'Build graph', body: 'Idempotent MERGE batches push Commits, Persons, Files, Functions, ConfigKeys, PullRequests, Issues, Comments, and Documents into Neo4j AuraDB. REFERENCES edges link commits to the issues they mention.' },
              { label: 'Mine decisions', body: 'Each PR thread and substantial commit message is sent to Nemotron 3 Ultra (via Nebius Token Factory) twice — a normal prompt and a conservative prompt. Extracted decisions must have at least one verbatim quote verifiable in the source. Agreement is scored as embedding cosine similarity between the two passes.' },
              { label: 'Detect supersession', body: 'Three signals: structural (commit revert detection), semantic (LLM pair classification of consecutive decisions per entity), and high-similarity cross-entity pairs. Status resolution applies precedence: SUPERSEDED/REVERSED > UNCERTAIN > ACTIVE.' },
              { label: 'Answer with confidence', body: 'Entity linking, graph traversal, evidence assembly, grounded generation with citation verification, and a five-factor confidence score. The system refuses — and says so — when the graph has no answer.' },
            ].map(({ label, body }, i) => (
              <li key={i} className="how-pipeline-item">
                <span className="how-pipeline-item__n">{i + 1}</span>
                <div>
                  <strong className="how-pipeline-item__label">{label}</strong>
                  <p className="how-pipeline-item__body">{body}</p>
                </div>
              </li>
            ))}
          </ol>
        </Section>

        {/* 2. Graph schema */}
        <Section id="schema" title="Graph schema">
          <div className="how-svg-wrap">
            <GraphSchemaSVG />
          </div>
          <div className="how-schema-table">
            <table>
              <thead>
                <tr><th>Node</th><th>Key properties</th><th>Role</th></tr>
              </thead>
              <tbody>
                {[
                  ['Entity (File / Function / ConfigKey)', 'id, name, path', 'The code artefact a decision governs'],
                  ['Decision', 'id, title, summary, rationale, status, agreement', 'The mined engineering decision'],
                  ['Commit', 'id (sha), message, date, author', 'Git commit — primary evidence'],
                  ['PullRequest / Issue', 'id, number, title, body', 'GitHub discussion — additional evidence'],
                  ['Comment', 'id, author, body, embedding', 'Individual comment — used in vector search'],
                  ['Document', 'id, path, section, text', 'Design doc or config comment block'],
                  ['Person', 'id (email/login), name', 'Author, committer, or decision-maker'],
                ].map(([node, props, role]) => (
                  <tr key={node}>
                    <td><code>{node}</code></td>
                    <td><code>{props}</code></td>
                    <td>{role}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="how-schema-rels">
            <h3 className="how-schema-rels__title">Key relationships</h3>
            <div className="how-schema-rels__grid">
              {[
                ['GOVERNS',      'Decision → Entity',      'The decision applies to this code entity'],
                ['EVIDENCED_BY', 'Decision → Commit/PR…',  'Evidence used to extract the decision'],
                ['MODIFIES',     'Commit → Entity',         'Commit changed this entity (with CHANGE type)'],
                ['SUPERSEDES',   'Decision → Decision',     'Newer decision overrides older one'],
                ['REFINES',      'Decision → Decision',     'Newer decision extends or adjusts without overriding'],
                ['REVERTS',      'Decision → Decision',     'Structural revert — evidence from commit message'],
                ['AUTHORED',     'Person → Commit/PR',      'Authorship edge'],
                ['MADE_BY',      'Decision → Person',       'Person approved or proposed the decision'],
                ['REFERENCES',   'Commit → Issue',          'Commit message references #123'],
              ].map(([rel, path, desc]) => (
                <div key={rel} className="how-schema-rels__item">
                  <code className="how-schema-rels__rel">{rel}</code>
                  <span className="how-schema-rels__path">{path}</span>
                  <span className="how-schema-rels__desc">{desc}</span>
                </div>
              ))}
            </div>
          </div>
        </Section>

        {/* 3. Question path */}
        <Section id="question-path" title="What happens when you ask a question">
          <ol className="how-steps">
            {QUESTION_STEPS.map(step => (
              <li key={step.n} className="how-step">
                <span className="how-step__n" aria-hidden="true">{step.n}</span>
                <div>
                  <h3 className="how-step__title">{step.title}</h3>
                  <p className="how-step__body">{step.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </Section>

        {/* 4. Supersession */}
        <Section id="supersession" title="Supersession detection">
          <p className="how-body">
            When a decision is superseded — replaced by a newer choice that contradicts it — IntentLens must not return the stale decision as the current answer. Three signals are used in combination:
          </p>
          <div className="how-svg-wrap">
            <SupersessionSVG />
          </div>
          <div className="how-supersession-detail">
            <div className="how-supersession-signal">
              <h4>Structural (commit reverts)</h4>
              <p>Commit messages matching <code>"This reverts commit SHA"</code> create REVERTS edges between the decisions evidenced by each commit. Confidence is set to 0.95 automatically.</p>
            </div>
            <div className="how-supersession-signal">
              <h4>Semantic (LLM pair classification)</h4>
              <p>For every entity with two or more governing decisions, consecutive pairs (by date) are sent to the LLM with the prompt: "Classify NEWER relative to OLDER — reinforces / refines / contradicts / unrelated." Any pair with cosine similarity above 0.50 is also a candidate, even if they govern different entities. LLM calls are capped at 200 per run.</p>
            </div>
            <div className="how-supersession-signal">
              <h4>Temporal resolution</h4>
              <p><code>compute_statuses()</code> applies precedence rules: SUPERSEDED/REVERSED beats UNCERTAIN beats ACTIVE. A link with confidence below MIN_CONF (0.6) yields UNCERTAIN rather than SUPERSEDED, and the answer notes "possibly superseded" rather than hiding the decision.</p>
            </div>
          </div>
        </Section>

        {/* 5. Confidence */}
        <Section id="confidence" title="Confidence scoring">
          <p className="how-body">
            Confidence is computed from five graph facts. The LLM never contributes to this score — it is not asked to rate its own answer.
          </p>
          <p className="how-body">
            <strong>Formula:</strong> score = Σ weight<sub>i</sub> × factor<sub>i</sub>
          </p>
          <div className="how-svg-wrap">
            <ConfidenceSVG />
          </div>
          {CONFIDENCE_FACTORS.map(f => (
            <div key={f.name} className="how-factor">
              <span className="how-factor__name">{f.name}</span>
              <span className="how-factor__weight">{Math.round(f.weight * 100)}%</span>
              <span className="how-factor__desc">{f.desc}</span>
            </div>
          ))}
          <p className="how-body how-body--note">
            If the score falls below <code>REFUSAL_THRESHOLD</code> (default 0.35) or no decision is found within <code>MAX_GRAPH_HOPS</code> (default 3), the system refuses. The refusal response includes last commit authors and closest related discussions from vector search.
          </p>
        </Section>

      </div>
    </main>
  )
}
