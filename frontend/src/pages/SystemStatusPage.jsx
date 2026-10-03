import { useCallback, useEffect, useState } from 'react'

import { apiRequest } from '../api/client.js'
import Wordmark from '../components/Wordmark.jsx'

const DISPLAY_TIMEZONE = 'Asia/Kolkata'

function formatServerTime(isoValue) {
  return new Intl.DateTimeFormat('en-IN', {
    dateStyle: 'medium',
    timeStyle: 'medium',
    timeZone: DISPLAY_TIMEZONE,
  }).format(new Date(isoValue))
}

function StatusRow({ label, value, tone }) {
  return (
    <div className="status-row">
      <dt>{label}</dt>
      <dd>
        {tone ? <span className={`pill pill--${tone}`}>{value}</span> : value}
      </dd>
    </div>
  )
}

export default function SystemStatusPage() {
  const [health, setHealth] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  const checkHealth = useCallback(async (signal) => {
    setLoading(true)
    setError(null)
    try {
      setHealth(await apiRequest('/health', { signal }))
    } catch (err) {
      if (err.name === 'AbortError') return
      // A 503 still carries a health body describing what is down.
      setHealth(err.body && typeof err.body === 'object' ? err.body : null)
      setError(err.message)
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    checkHealth(controller.signal)
    return () => controller.abort()
  }, [checkHealth])

  const apiReachable = health !== null

  return (
    <div className="page-center">
      <main className="card status-card" aria-busy={loading}>
        <header className="status-card__header">
          <Wordmark size="lg" />
          <p className="muted">Human-in-the-Loop Campus Concern Triage and Prioritization</p>
        </header>

        <h1 className="status-card__title">System status</h1>

        {loading && !health && <p className="muted">Checking the server…</p>}

        {!loading && !apiReachable && (
          <p className="alert alert--danger" role="alert">
            {error ?? 'The API did not respond'}. Start the backend and try again.
          </p>
        )}

        {apiReachable && (
          <dl className="status-list">
            <StatusRow label="API" value="Reachable" tone="success" />
            <StatusRow
              label="Database"
              value={health.database === 'ok' ? 'Connected' : 'Unavailable'}
              tone={health.database === 'ok' ? 'success' : 'danger'}
            />
            <StatusRow label="Environment" value={health.environment} />
            <StatusRow label="API version" value={health.version} />
            <StatusRow label="Server time (IST)" value={formatServerTime(health.server_time_utc)} />
          </dl>
        )}

        <button type="button" className="btn btn--primary" onClick={() => checkHealth()} disabled={loading}>
          {loading ? 'Checking…' : 'Check again'}
        </button>
      </main>
    </div>
  )
}
