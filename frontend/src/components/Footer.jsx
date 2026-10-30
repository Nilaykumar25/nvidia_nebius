import { Link } from 'react-router-dom'
import './Footer.css'

function FooterLogoMark() {
  return (
    <svg width="22" height="22" viewBox="0 0 28 28" fill="none" aria-hidden="true" focusable="false">
      <circle cx="8" cy="20" r="4" fill="var(--entity)" opacity="0.9" />
      <circle cx="14" cy="8" r="4" fill="var(--accent)" />
      <circle cx="22" cy="20" r="3" fill="var(--muted)" opacity="0.7" />
      <line x1="8" y1="20" x2="14" y2="8" stroke="var(--line)" strokeWidth="1.5" />
      <line x1="14" y1="8" x2="22" y2="20" stroke="var(--line)" strokeWidth="1.5" />
    </svg>
  )
}

export default function Footer() {
  return (
    <footer className="footer" role="contentinfo">
      <div className="container">
        <div className="footer__inner">

          <div className="footer__brand">
            <Link to="/" className="footer__logo" aria-label="IntentLens home">
              <FooterLogoMark />
              <span>IntentLens</span>
            </Link>
            <p className="footer__tagline">
              Connect code to the decisions that shaped it. Every answer shows its evidence trail.
            </p>
          </div>

          <nav className="footer__links" aria-label="Footer navigation">
            <div className="footer__col">
              <h3 className="footer__col-title">Product</h3>
              <Link to="/ask">Ask</Link>
              <Link to="/explore">Explore</Link>
            </div>

            <div className="footer__col">
              <h3 className="footer__col-title">Learn</h3>
              <Link to="/how">How it works</Link>
              <Link to="/results">Results</Link>
            </div>

            <div className="footer__col">
              <h3 className="footer__col-title">Project</h3>
              <Link to="/about">About</Link>
              <a
                href="https://github.com/nilay-intentlens/intentlens"
                target="_blank"
                rel="noreferrer noopener"
                aria-label="IntentLens on GitHub (opens in new tab)"
              >
                GitHub
              </a>
            </div>
          </nav>

        </div>

        <p className="footer__copy">
          © {new Date().getFullYear()} IntentLens. Built to surface decisions, not guess at them.
          &nbsp;·&nbsp; Powered by NVIDIA Nemotron 3 Ultra on Nebius Token Factory.
        </p>
      </div>
    </footer>
  )
}
