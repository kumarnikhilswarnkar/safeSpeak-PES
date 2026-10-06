import { Activity, PlayCircle } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import { getAutomation, runAutomationNow } from '../api/insights.js'
import { useAuth } from '../auth/AuthContext.jsx'
import { formatDateTime, timeAgo } from '../utils/format.js'
import { useToast } from './Toast.jsx'
import { Badge, Card, Spinner } from './ui.jsx'

function useTick(ms = 1000) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), ms)
    return () => clearInterval(id)
  }, [ms])
  return now
}

/** Live status of the automatic TAT monitor (polled every 10 s). */
export default function AutomationPanel({ overview, canRun, onRan, className, showRuns = false }) {
  const { authRequest } = useAuth()
  const toast = useToast()
  const [status, setStatus] = useState(null)
  const [busy, setBusy] = useState(false)
  const now = useTick()

  const load = useCallback(() => getAutomation(authRequest).then(setStatus).catch(() => {}), [authRequest])
  useEffect(() => {
    load()
    const id = setInterval(load, 10_000)
    return () => clearInterval(id)
  }, [load])

  async function runNow() {
    setBusy(true)
    try {
      const s = await runAutomationNow(authRequest)
      setStatus(s)
      const r = s.recent_runs[0]
      toast(`${r.processed} overdue complaint(s) processed: ${r.escalated.length} escalated, ${r.exhausted.length} exhausted.`, {
        title: 'TAT check complete',
      })
      onRan?.()
    } catch (err) {
      toast(err.message, { tone: 'error' })
    } finally {
      setBusy(false)
    }
  }

  const nextIn = status?.next_run_at ? Math.max(0, Math.round((new Date(status.next_run_at) - now) / 1000)) : null

  return (
    <Card
      title="Automatic TAT monitor"
      subtitle="Background job inside the API: finds overdue complaints and escalates them"
      icon={Activity}
      className={className}
      actions={
        status &&
        (status.running ? (
          <Badge tone="green">
            <span className="size-1.5 animate-pulse rounded-full bg-emerald-500" /> Running
          </Badge>
        ) : (
          <Badge tone="red">{status.enabled ? 'Stopped' : 'Disabled'}</Badge>
        ))
      }
    >
      {!status ? (
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <Spinner /> Loading status…
        </div>
      ) : (
        <>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
            <div>
              <dt className="text-xs text-slate-500">Check interval</dt>
              <dd className="font-medium">every {status.interval_seconds} s</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Next check</dt>
              <dd className="font-medium tabular-nums">{nextIn != null ? `in ${nextIn} s` : '—'}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Last automatic check</dt>
              <dd className="font-medium">{status.last_automatic_run_at ? timeAgo(status.last_automatic_run_at, now) : 'not yet'}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Checks since start</dt>
              <dd className="font-medium tabular-nums">{status.total_runs}</dd>
            </div>
            {overview && (
              <>
                <div>
                  <dt className="text-xs text-slate-500">Overdue right now</dt>
                  <dd className="font-medium tabular-nums">{overview.totals.overdue}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">Escalated automatically (all time)</dt>
                  <dd className="font-medium tabular-nums">{overview.escalations.automatic}</dd>
                </div>
              </>
            )}
          </dl>
          {status.started_at && (
            <p className="mt-3 text-xs text-slate-500">Monitor started {formatDateTime(status.started_at)}. Duplicate escalation is prevented by a lock and a new deadline after each escalation.</p>
          )}
          {canRun && (
            <button type="button" className="btn-secondary mt-4 w-full" onClick={runNow} disabled={busy}>
              {busy ? <Spinner /> : <PlayCircle className="size-4" />} Run check now
            </button>
          )}
          {showRuns && (
            <div className="mt-5 border-t border-slate-100 pt-4">
              <p className="eyebrow mb-2">Recent checks</p>
              {status.recent_runs.length === 0 ? (
                <p className="text-sm text-slate-500">No checks yet.</p>
              ) : (
                <ul className="divide-y divide-slate-100 text-sm">
                  {status.recent_runs.map((r) => (
                    <li key={r.started_at} className="flex flex-wrap items-center gap-2 py-2">
                      <Badge tone={r.trigger === 'automatic' ? 'brand' : 'slate'}>{r.trigger}</Badge>
                      <span className="text-slate-600">{formatDateTime(r.finished_at)}</span>
                      <span className="ml-auto text-slate-700 tabular-nums">
                        {r.error ? (
                          <span className="text-red-600">error: {r.error}</span>
                        ) : (
                          `${r.processed} overdue · ${r.escalated.length} escalated · ${r.exhausted.length} exhausted`
                        )}
                      </span>
                      {r.escalated.length > 0 && <span className="w-full font-mono text-xs text-slate-500">{r.escalated.join(', ')}</span>}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </>
      )}
    </Card>
  )
}
