/**
 * api.js — all backend calls
 *
 * In development:  Vite proxy strips /api prefix → http://127.0.0.1:8000
 * In production:   VITE_API_BASE_URL is the backend URL (no /api prefix)
 *                  e.g. https://intentlens-api.onrender.com
 */
const RENDER_URL = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL   // support both names

// In dev, use /api (proxied by vite). In prod, use the backend URL directly.
const BASE = RENDER_URL
  ? RENDER_URL.replace(/\/$/, '')   // strip trailing slash
  : '/api'

function url(path) {
  // path must start with /
  return `${BASE}${path}`
}

export async function ask(question, lang = 'en') {
  const r = await fetch(url('/ask'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, lang }),
  })
  if (!r.ok) throw new Error(`The server returned ${r.status}. Check that the backend is running and AuraDB is reachable.`)
  return r.json()
}

/** Alias — matches the task spec naming */
export const askQuestion = ask

export async function getStats() {
  try {
    const r = await fetch(url('/stats'))
    if (!r.ok) return null
    return r.json()
  } catch {
    return null
  }
}

export async function searchEntities(q) {
  if (!q) return []
  const r = await fetch(url(`/entities/search?q=${encodeURIComponent(q)}`))
  if (!r.ok) return []
  return r.json()
}

/**
 * getEntityGraph — fetch graph data for a single entity
 * GET /entity/graph?id=...&expand=<node_id>
 */
export async function getEntityGraph(id, expand = '') {
  const params = new URLSearchParams({ id })
  if (expand) params.set('expand', expand)
  const r = await fetch(url(`/entity/graph?${params.toString()}`))
  if (!r.ok) throw new Error(`Server error ${r.status}`)
  return r.json()
}

export async function getEvalResults() {
  const r = await fetch(url('/eval/results'))
  if (r.status === 404) return null
  if (!r.ok) throw new Error(`Server error ${r.status}`)
  return r.json()
}
