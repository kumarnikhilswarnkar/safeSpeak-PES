import { CheckCircle2, RefreshCw, XCircle } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import { apiRequest } from '../api/client.js'
import CenteredPage from '../components/CenteredPage.jsx'
import { Alert, Spinner } from '../components/ui.jsx'

function Row({ label, ok, value }) {
  return (
    <div className="flex items-center justify-between py-2.5 text-sm">
      <dt className="text-slate-500">{label}</dt>
      <dd className="flex items-center gap-1.5 font-medium text-slate-900">
        {ok === true && <CheckCircle2 className="size-4 text-emerald-600" />}
        {ok === false && <XCircle className="size-4 text-red-600" />}
        {value}
      </dd>
    </div>
  )
}

export default function SystemStatusPage() {
  const [health, setHealth] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  const check = useCallback(async (signal) => {
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
    check(controller.signal)
    return () => controller.abort()
  }, [check])

  return (
    <CenteredPage>
      <h1 className="text-xl font-semibold text-slate-900">System status</h1>
      {loading && !health && (
        <p className="mt-4 flex items-center gap-2 text-sm text-slate-500">
          <Spinner /> Checking the server…
        </p>
      )}
      {!loading && !health && (
        <Alert tone="red" className="mt-4">
          {error ?? 'The API did not respond'}. Start the backend and try again.
        </Alert>
      )}
      {health && (
        <dl className="mt-4 divide-y divide-slate-100">
          <Row label="API" ok value="Reachable" />
          <Row label="Database" ok={health.database === 'ok'} value={health.database === 'ok' ? 'Connected' : 'Unavailable'} />
          <Row label="AI triage model" ok={health.triage_model !== 'unavailable'} value={health.triage_model} />
          <Row label="Environment" value={health.environment} />
          <Row label="Demo mode" value={health.demo_mode ? 'On' : 'Off'} />
          <Row label="API version" value={health.version} />
        </dl>
      )}
      <button type="button" className="btn-secondary mt-6 w-full" onClick={() => check()} disabled={loading}>
        <RefreshCw className="size-4" /> Check again
      </button>
    </CenteredPage>
  )
}
