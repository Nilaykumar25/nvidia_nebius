import './About.css'

/* These limitations are copied verbatim in meaning from README.md.
   They have NOT been softened. */
const LIMITATIONS = [
  {
    id: 'identity',
    heading: 'Person identity is not merged',
    body: 'Commit authors are keyed by email and PR authors by GitHub login, so one human can appear as two Person nodes. There is no identity-mapping step yet. If antirez@gmail.com and antirez@users.noreply.github.com are the same person, the graph does not know that.',
  },
  {
    id: 'dates',
    heading: 'Mixed timezone formats can mis-order decisions',
    body: 'Dates are stored as ISO strings. Mixed timezone formats in old commits can produce incorrect ordering in edge cases, which affects the temporal supersession signal.',
  },
  {
    id: 'functions',
    heading: 'Function extraction is approximate outside C and Python',
    body: 'Function names are extracted from git hunk headers (the text after the second @@ in a diff). This is accurate for C and Python, approximate for other languages. Tree-sitter is the upgrade path but was not implemented in this version.',
  },
  {
    id: 'llm-endpoint',
    heading: 'LLM endpoint and model name may change',
    body: 'The LLM client targets any OpenAI-compatible endpoint. The base URL and model name are configured via LLM_BASE_URL and LLM_MODEL in the environment. Verify these against your Nebius dashboard before deployment.',
  },
  {
    id: 'nvl',
    heading: 'NVL graph library has breaking API changes between minor versions',
    body: 'The @neo4j-nvl/react package has breaking API changes between minor versions. The click callback changed from onClick to onNodeClick in 0.3.x. Always verify the installed version\'s API before deploying.',
  },
  {
    id: 'coverage',
    heading: 'Without GitHub token, only git commits are mined',
    body: 'PR discussions contain the richest engineering decisions. Without a GitHub token, ingestion runs on commit messages only. Commit-mined decisions have lower average agreement scores and fewer GOVERNS links because commit messages rarely name config keys explicitly.',
  },
  {
    id: 'governs',
    heading: '86% of decisions have no GOVERNS links in the current build',
    body: 'With only 200 commit-threads mined (no PRs), most decisions cannot be linked to specific entities because commit messages do not always name the entity. Loading GitHub PRs would dramatically improve GOVERNS coverage. Decisions without GOVERNS links are unreachable by entity search and only discoverable via vector fallback.',
  },
]

const TECH_STACK = [
  { name: 'Neo4j AuraDB',          role: 'Knowledge graph database', detail: 'Cypher 5, vector + full-text indexes' },
  { name: 'NVIDIA Nemotron 3 Ultra', role: 'LLM for mining + answering', detail: 'Served via Nebius Token Factory, OpenAI-compatible client' },
  { name: 'PyDriller',             role: 'Git history ingestion',     detail: 'pre-selects commits via git log' },
  { name: 'sentence-transformers', role: 'Embeddings',               detail: 'all-MiniLM-L6-v2, 384 dimensions' },
  { name: 'FastAPI',               role: 'Backend API',               detail: 'Pydantic v2, async endpoints' },
  { name: 'React 18 + Vite',       role: 'Frontend',                  detail: 'react-router-dom v6, code splitting' },
  { name: '@neo4j-nvl/react',      role: 'Graph visualisation',      detail: '0.3.9, InteractiveNvlWrapper' },
]

const TEAM = [
  {
    name: 'Nilay Kumar',
    roles: ['Backend & graph engineering', 'LLM integration & prompting'],
  },
  {
    name: 'Riddhima Chaturvedi',
    roles: ['Frontend & design', 'Evaluation & demo'],
  },
]

export default function About() {
  return (
    <main id="main" className="about-page">
      <div className="about-hero container">
        <h1 className="about-hero__title">About IntentLens</h1>
        <p className="about-hero__body">
          Codebases accumulate decisions without recording why. IntentLens makes those decisions visible by
          connecting every code entity to the conversation, commit, and person that shaped it.
        </p>
      </div>

      <div className="container">

        {/* Project summary */}
        <section className="about-section" aria-labelledby="project-heading">
          <h2 id="project-heading" className="about-section__title">Project summary</h2>
          <div className="about-prose">
            <p>
              IntentLens answers "why is the code like this?" for any Git repository. It ingests commit history,
              GitHub pull requests, issues, and in-repo design documents, builds a Neo4j knowledge graph
              (IntentGraph) connecting code entities to engineering decisions, and answers natural-language
              questions with a cited chain of evidence.
            </p>
            <p>
              Every answer carries evidence: no sentence is shown unless it cites at least one evidence ID
              that exists in the graph. Superseded decisions are never presented as current. If the graph has
              no answer, the system refuses rather than invents one.
            </p>
            <p>
              The system is demonstrated against the Redis/redis repository, subsystem: replication.c,
              rdb.c, aof.c, redis.conf.
            </p>
          </div>
        </section>

        {/* Hackathon submission details */}
        <section className="about-section" aria-labelledby="hackathon-heading">
          <h2 id="hackathon-heading" className="about-section__title">Hackathon submission details</h2>
          <div className="about-context-grid">
            {[
              { label: 'Event',      value: 'Nebius × NVIDIA Global AI Hackathon' },
              { label: 'Track',      value: 'Coding and Agentic Engineering' },
              { label: 'LLM',        value: 'NVIDIA Nemotron 3 Ultra' },
              { label: 'Inference',  value: 'Nebius Token Factory (OpenAI-compatible API)' },
              { label: 'Multilingual', value: 'Hindi/Hinglish query normalisation via Nemotron' },
            ].map(({ label, value }) => (
              <div key={label} className="about-context-item">
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </div>
        </section>

        {/* Tech stack */}
        <section className="about-section" aria-labelledby="tech-heading">
          <h2 id="tech-heading" className="about-section__title">Tech stack</h2>
          <div className="about-tech-grid">
            {TECH_STACK.map(({ name, role, detail }) => (
              <div key={name} className="about-tech-item">
                <strong className="about-tech-item__name">{name}</strong>
                <span className="about-tech-item__role">{role}</span>
                <span className="about-tech-item__detail">{detail}</span>
              </div>
            ))}
          </div>
        </section>

        {/* Known limitations — verbatim, unsoftened */}
        <section className="about-section" aria-labelledby="limits-heading">
          <h2 id="limits-heading" className="about-section__title">Known limitations</h2>
          <p className="about-limits-intro">
            These are stated plainly. A system that hides its limitations is more dangerous than one that names them.
          </p>
          <div className="about-limits">
            {LIMITATIONS.map(({ id, heading, body }) => (
              <div key={id} className="about-limit">
                <h3 className="about-limit__heading">{heading}</h3>
                <p className="about-limit__body">{body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Team */}
        <section className="about-section" aria-labelledby="team-heading">
          <h2 id="team-heading" className="about-section__title">Team</h2>
          <div className="about-team-grid">
            {TEAM.map(({ name, roles }) => (
              <div key={name} className="about-team-member">
                <span className="about-team-member__name">{name}</span>
                <ul className="about-team-member__roles">
                  {roles.map(r => (
                    <li key={r} className="about-team-member__role">{r}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>

      </div>
    </main>
  )
}
