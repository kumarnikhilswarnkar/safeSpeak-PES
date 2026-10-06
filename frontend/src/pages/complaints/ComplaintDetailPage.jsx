import {
  AlarmClock,
  ArrowLeft,
  ArrowRight,
  ArrowUpCircle,
  Bot,
  CheckCircle2,
  Clock,
  FileText,
  GitBranch,
  History,
  PlayCircle,
  Route,
  ShieldAlert,
  TimerReset,
  UserCheck,
  UserCog,
  Users,
} from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'

import { getConcern, getRerouteTargets, reviewConcern, simulateBreach } from '../../api/concerns.js'
import { getAutomation, runAutomationNow } from '../../api/insights.js'
import { useAuth } from '../../auth/AuthContext.jsx'
import AiAnalysisCard from '../../components/AiAnalysisCard.jsx'
import AppShell from '../../components/AppShell.jsx'
import AuditTimeline from '../../components/AuditTimeline.jsx'
import { DecisionBadge, EscalationBadge, PriorityBadge, StatusBadge, TatBadge } from '../../components/Badges.jsx'
import { useToast } from '../../components/Toast.jsx'
import { Alert, Badge, Card, ErrorState, KeyValue, LoadingState, Modal, cx } from '../../components/ui.jsx'
import WorkflowStepper from '../../components/WorkflowStepper.jsx'
import useLoader from '../../hooks/useLoader.js'
import {
  CATEGORIES,
  OPEN_STATUSES,
  PRIORITIES,
  ROLE_SHORT,
  SCOPE_LABEL,
  formatDateTime,
  formatDuration,
  formatRemaining,
  personLabel,
} from '../../utils/format.js'

/** Re-render periodically so countdowns stay current. */
function useNow(intervalMs = 15_000) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(id)
  }, [intervalMs])
  return now
}

export default function ComplaintDetailPage() {
  const { code } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const { authRequest, user } = useAuth()
  const loader = useCallback(() => getConcern(authRequest, code), [authRequest, code])
  const { data: c, error, loading, setData, reload } = useLoader(loader)
  const now = useNow()

  // Keep an open case fresh, so an automatic escalation appears without a manual reload.
  useEffect(() => {
    if (!c || !OPEN_STATUSES.includes(c.status)) return undefined
    const id = setInterval(() => getConcern(authRequest, code).then(setData).catch(() => {}), 20_000)
    return () => clearInterval(id)
  }, [c, authRequest, code, setData])

  if (loading && !c) {
    return (
      <AppShell>
        <LoadingState label="Loading complaint…" />
      </AppShell>
    )
  }
  if (error) {
    return (
      <AppShell>
        {error.status === 404 ? (
          <Alert tone="amber" title="Complaint not found" icon={ShieldAlert}>
            It does not exist, or your account does not have access to it.
          </Alert>
        ) : (
          <ErrorState error={error} onRetry={reload} />
        )}
      </AppShell>
    )
  }

  const isOpen = OPEN_STATUSES.includes(c.status)
  const canAct = isOpen && user.permissions.includes('review_complaints') && c.assigned_to?.id === user.id
  const isOperator = user.permissions.includes('manage_rules_and_settings')

  return (
    <AppShell>
      <button type="button" onClick={() => navigate(-1)} className="mb-4 inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800">
        <ArrowLeft className="size-4" /> Back
      </button>

      {location.state?.justSubmitted && (
        <Alert tone="green" icon={CheckCircle2} title="Complaint submitted" className="mb-4">
          Keep your complaint ID <strong>{c.complaint_id}</strong> to track it.
        </Alert>
      )}

      <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <p className="eyebrow mb-1">Case file</p>
          <h1 className="font-mono text-2xl font-semibold tracking-tight text-slate-900">{c.complaint_id}</h1>
          <p className="mt-1 text-sm text-slate-500">
            Submitted by {c.complainant.name} ({ROLE_SHORT[c.complainant.role] ?? c.complainant.role}) ·{' '}
            {formatDateTime(c.created_at)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={c.status} />
          <PriorityBadge priority={c.priority} />
          <DecisionBadge source={c.decision_source} />
          <EscalationBadge complaint={c} />
          <TatBadge state={c.tat.state} />
        </div>
      </div>

      <WorkflowStepper complaint={c} />

      {c.breached_at_top && (
        <Alert tone="red" icon={ShieldAlert} title="Escalation chain exhausted — administrator attention needed" className="mt-4">
          The deadline passed at the highest configured level. The complaint stays with the highest authority and is
          flagged on the administrator dashboard; no further automatic escalation is possible.
        </Alert>
      )}

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <div className="min-w-0 space-y-6 xl:col-span-2">
          <Card title="Complaint" icon={FileText}>
            <p className="text-[15px] leading-relaxed whitespace-pre-wrap text-slate-800">{c.description}</p>
            {c.resolution_note && (
              <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm">
                <p className="font-medium text-emerald-900">Resolution · {formatDateTime(c.resolved_at)}</p>
                <p className="mt-0.5 text-emerald-800">{c.resolution_note}</p>
              </div>
            )}
          </Card>

          <AiAnalysisCard ai={c.ai} decisionSource={c.decision_source} />

          <DecisionComparison complaint={c} />

          {canAct && <ReviewPanel complaint={c} onUpdated={setData} />}

          <Card title="Audit trail" subtitle="Append-only record of every action, who did it and what changed" icon={History}>
            <AuditTimeline events={c.events} />
          </Card>
        </div>

        <div className="min-w-0 space-y-6">
          <AssignmentCard complaint={c} />
          <TatCard complaint={c} now={now} />
          <EscalationCard complaint={c} />
          {isOperator && <DemoPanel complaint={c} onUpdated={setData} />}
        </div>
      </div>
    </AppShell>
  )
}

// --- AI recommendation vs human decision -------------------------------------------------

function DecisionComparison({ complaint: c }) {
  const human = c.human_decision
  const pending = c.status === 'PENDING_REVIEW'
  const rows = [
    ['Category', c.ai.category, c.category],
    ['Priority', c.ai.priority, c.priority],
  ]
  return (
    <Card title="AI recommendation vs final decision" icon={UserCheck} subtitle="The AI output is never edited; the final values are what the workflow uses">
      <div className="overflow-hidden rounded-lg border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className="table-head">Field</th>
              <th className="table-head">
                <Bot className="mr-1 inline size-3.5" /> AI recommendation
              </th>
              <th className="table-head">
                <UserCheck className="mr-1 inline size-3.5" /> Final (in use)
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map(([label, ai, final]) => (
              <tr key={label}>
                <td className="table-cell text-slate-500">{label}</td>
                <td className="table-cell">{ai}</td>
                <td className="table-cell">
                  <span className={cx('font-medium', ai !== final ? 'text-amber-700' : 'text-slate-900')}>{final}</span>
                  {ai !== final && <Badge tone="amber" className="ml-2">changed by human</Badge>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4 text-sm">
        {human ? (
          <dl className="space-y-2">
            <KeyValue label="Decision">
              {human.action === 'accepted' ? 'Reviewer accepted the AI recommendation' : 'Reviewer overrode the AI recommendation'}
            </KeyValue>
            <KeyValue label="Reviewer">
              {personLabel(human.reviewer)} ({ROLE_SHORT[human.reviewer?.role] ?? '—'})
            </KeyValue>
            <KeyValue label="Decided at">{formatDateTime(human.at)}</KeyValue>
            <KeyValue label="Reviewer comment">{human.remarks ? `“${human.remarks}”` : <span className="text-slate-400">No comment</span>}</KeyValue>
          </dl>
        ) : pending ? (
          <Alert tone="brand" icon={UserCog}>
            Waiting for {personLabel(c.assigned_to)} to accept, override or reroute.
          </Alert>
        ) : (
          <p className="text-slate-500">
            No human review was needed: the AI recommendation was applied automatically. The assigned authority can still
            override it.
          </p>
        )}
      </div>
    </Card>
  )
}

// --- assignment and routing ------------------------------------------------------------

function AssignmentCard({ complaint: c }) {
  const r = c.routing
  const last = r?.last_decision
  return (
    <Card title="Assignment & routing" icon={Route}>
      <dl className="space-y-2.5">
        <KeyValue label="Assigned to">
          <span className="font-medium">{personLabel(c.assigned_to)}</span>
          <span className="block text-xs text-slate-500">{ROLE_SHORT[c.assigned_to?.role]}</span>
        </KeyValue>
        <KeyValue label="Department / office">{c.handling_department?.name ?? '—'}</KeyValue>
        <KeyValue label="Current level">L{c.escalation_level} of the chain</KeyValue>
      </dl>
      {last && (
        <div className="mt-4 rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
          <p className="mb-1 flex items-center gap-1.5 font-semibold text-slate-700">
            <GitBranch className="size-3.5" /> Routing reason
          </p>
          Category <strong>{last.category}</strong> uses the{' '}
          {last.chain === 'category' ? 'category-specific' : 'default'} escalation chain → level {last.level}:{' '}
          <strong>{last.rule_label}</strong> ({SCOPE_LABEL[last.target_scope] ?? last.target_scope}).
          {last.skipped_levels?.length > 0 && ` Levels ${last.skipped_levels.join(', ')} skipped: no active authority.`}
          {r.manually_rerouted && ' A reviewer has since rerouted it manually.'}
        </div>
      )}
      {r?.chain?.length > 0 && (
        <ol className="mt-4 space-y-1.5">
          {r.chain.map((step) => {
            const current = step.level === c.escalation_level
            const passed = step.level < c.escalation_level
            return (
              <li
                key={step.level}
                className={cx(
                  'flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-xs',
                  current ? 'bg-brand-50 font-medium text-brand-800 ring-1 ring-brand-100' : passed ? 'text-slate-400 line-through' : 'text-slate-600',
                )}
              >
                <span className={cx('grid size-5 shrink-0 place-items-center rounded-full text-[10px] font-semibold', current ? 'bg-brand-600 text-white' : 'bg-slate-200 text-slate-600')}>
                  {step.level}
                </span>
                {step.label}
              </li>
            )
          })}
        </ol>
      )}
    </Card>
  )
}

// --- TAT ------------------------------------------------------------------------------------

function TatCard({ complaint: c, now }) {
  const overdueMs = now - new Date(c.tat.deadline_at).getTime()
  const stopped = c.tat.state === 'STOPPED'
  const total = c.tat.hours * 3_600_000
  const used = Math.min(1, Math.max(0, (now - new Date(c.tat.started_at).getTime()) / total))
  return (
    <Card title="Turnaround time (TAT)" icon={Clock} actions={<TatBadge state={c.tat.state} />}>
      {!stopped && (
        <div className="mb-4">
          <p className={cx('text-xl font-semibold tabular-nums', overdueMs > 0 ? 'text-red-600' : 'text-slate-900')}>
            {overdueMs > 0 ? `Overdue by ${formatDuration(overdueMs)}` : formatRemaining(c.tat.deadline_at, now)}
          </p>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
            <div
              className={cx('h-full rounded-full', used >= 1 ? 'bg-red-500' : used > 0.75 ? 'bg-amber-500' : 'bg-emerald-500')}
              style={{ width: `${Math.round(used * 100)}%` }}
            />
          </div>
        </div>
      )}
      <dl className="space-y-2.5">
        <KeyValue label="Stage">{c.tat.stage === 'REVIEW' ? 'Human review' : 'Resolution'}</KeyValue>
        <KeyValue label="Allowance">{c.tat.hours} hours (rule #{c.tat.rule_id})</KeyValue>
        <KeyValue label="Stage started">{formatDateTime(c.tat.started_at)}</KeyValue>
        <KeyValue label="Original deadline">{formatDateTime(c.escalation.original_deadline_at)}</KeyValue>
        <KeyValue label="Current deadline">{formatDateTime(c.escalation.current_deadline_at)}</KeyValue>
      </dl>
    </Card>
  )
}

// --- escalation ------------------------------------------------------------------------------

function EscalationCard({ complaint: c }) {
  const history = c.escalation.history
  return (
    <Card title="Escalation" icon={ArrowUpCircle} actions={<EscalationBadge complaint={c} />}>
      {history.length === 0 ? (
        <p className="text-sm text-slate-500">
          Not escalated. If the deadline passes while the complaint is open, the automatic TAT monitor moves it to the next
          level of the chain.
        </p>
      ) : (
        <ol className="space-y-3">
          {history.map((h) => (
            <li key={h.at} className="rounded-lg border border-slate-200 p-3 text-sm">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-slate-900">
                  {h.result === 'exhausted' ? (
                    'Chain exhausted'
                  ) : (
                    <>
                      L{h.from_level} <ArrowRight className="inline size-3.5" /> L{h.to_level}
                    </>
                  )}
                </span>
                <Badge tone={h.automatic ? 'brand' : 'slate'} icon={h.automatic ? Bot : Users}>
                  {h.automatic ? 'Automatic' : 'Manual'}
                </Badge>
              </div>
              <p className="mt-1 text-xs text-slate-500">{formatDateTime(h.at)}</p>
              {h.result === 'escalated' && (
                <dl className="mt-2 space-y-1 text-xs">
                  <div className="flex justify-between gap-2">
                    <dt className="text-slate-500">From</dt>
                    <dd className="text-right">{h.from_assignee?.name ?? '—'}</dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-slate-500">To</dt>
                    <dd className="text-right font-medium">{h.to_assignee?.name ?? '—'}</dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-slate-500">Missed deadline</dt>
                    <dd className="text-right">{formatDateTime(h.previous_deadline_at)}</dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-slate-500">New deadline</dt>
                    <dd className="text-right">{formatDateTime(h.new_deadline_at)}</dd>
                  </div>
                </dl>
              )}
            </li>
          ))}
        </ol>
      )}
    </Card>
  )
}

// --- administrator demo tools -------------------------------------------------------------

function DemoPanel({ complaint, onUpdated }) {
  const { authRequest } = useAuth()
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const [monitor, setMonitor] = useState(null)
  const isOpen = OPEN_STATUSES.includes(complaint.status)

  useEffect(() => {
    getAutomation(authRequest).then(setMonitor).catch(() => {})
  }, [authRequest, complaint])

  async function breach() {
    setBusy(true)
    try {
      onUpdated(await simulateBreach(authRequest, complaint.complaint_id))
      toast(
        monitor?.running
          ? `Deadline moved into the past. The automatic monitor will escalate it within ${monitor.interval_seconds} s.`
          : 'Deadline moved into the past.',
        { title: 'TAT breach simulated', tone: 'info' },
      )
    } catch (err) {
      toast(err.status === 404 ? 'Demo mode is off on the server.' : err.message, { tone: 'error' })
    } finally {
      setBusy(false)
    }
  }

  async function runNow() {
    setBusy(true)
    try {
      const status = await runAutomationNow(authRequest)
      setMonitor(status)
      onUpdated(await getConcern(authRequest, complaint.complaint_id))
      const run = status.recent_runs[0]
      toast(`Checked now: ${run.escalated.length} escalated, ${run.exhausted.length} exhausted.`, { title: 'TAT check complete' })
    } catch (err) {
      toast(err.message, { tone: 'error' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card title="TAT breach demonstration" icon={TimerReset} subtitle="Administrator only · recorded in the audit trail">
      <p className="text-sm text-slate-600">
        Moves this complaint's deadline into the past (demo mode only). Escalation is then performed by the{' '}
        <strong>automatic TAT monitor</strong>
        {monitor?.running ? `, which checks every ${monitor.interval_seconds} s` : ''} — no button needed.
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        <button type="button" className="btn-secondary" onClick={breach} disabled={busy || !isOpen}>
          <AlarmClock className="size-4" /> Simulate TAT breach
        </button>
        <button type="button" className="btn-ghost" onClick={runNow} disabled={busy}>
          <PlayCircle className="size-4" /> Run check now
        </button>
      </div>
    </Card>
  )
}

// --- reviewer actions ------------------------------------------------------------------------

const ACTIONS = {
  accept: { label: 'Accept AI', icon: CheckCircle2, help: 'Confirm the AI category and priority as the final decision.' },
  override: { label: 'Override', icon: UserCog, help: 'Correct the category and/or priority. The complaint is re-routed for the corrected category.' },
  reroute: { label: 'Reroute', icon: Route, help: 'Hand the complaint to another authority with a fresh TAT allowance.' },
  resolve: { label: 'Resolve', icon: CheckCircle2, help: 'Close the complaint with a resolution note that the complainant will see.' },
}

function ReviewPanel({ complaint, onUpdated }) {
  const { authRequest } = useAuth()
  const toast = useToast()
  const pending = complaint.status === 'PENDING_REVIEW'
  const humanDecided = ['HUMAN_ACCEPTED', 'HUMAN_OVERRIDDEN'].includes(complaint.decision_source)
  const available = Object.keys(ACTIONS).filter((a) => !(a === 'accept' && humanDecided) && !(a === 'resolve' && pending))
  const [action, setAction] = useState(available[0])
  const [category, setCategory] = useState(complaint.category)
  const [priority, setPriority] = useState(complaint.priority)
  const [targets, setTargets] = useState(null)
  const [targetId, setTargetId] = useState('')
  const [remarks, setRemarks] = useState('')
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (action !== 'reroute' || targets) return
    getRerouteTargets(authRequest, complaint.complaint_id)
      .then(setTargets)
      .catch((err) => toast(err.message, { tone: 'error' }))
  }, [action, targets, authRequest, complaint.complaint_id, toast])

  const unchanged = action === 'override' && category === complaint.category && priority === complaint.priority
  const invalid = unchanged || (action === 'reroute' && !targetId) || (action === 'resolve' && !remarks.trim())
  const target = targets?.find((t) => String(t.id) === targetId)

  async function submit() {
    const body = { action, remarks: remarks.trim() || undefined }
    if (action === 'override') {
      if (category !== complaint.category) body.category = category
      if (priority !== complaint.priority) body.priority = priority
    }
    if (action === 'reroute') body.target_user_id = Number(targetId)
    setBusy(true)
    try {
      const updated = await reviewConcern(authRequest, complaint.complaint_id, body)
      onUpdated(updated)
      setConfirming(false)
      setRemarks('')
      setTargets(null)
      toast('Saved and added to the audit trail.', { title: `${ACTIONS[action].label} recorded` })
    } catch (err) {
      toast(err.message, { tone: 'error', title: 'Could not save' })
      setConfirming(false)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card
      title="Your review"
      icon={UserCheck}
      subtitle={pending ? 'Human review required: your decision starts the resolution clock' : 'This complaint is assigned to you'}
      className="border-brand-200 ring-2 ring-brand-50"
    >
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" role="radiogroup" aria-label="Review action">
        {available.map((a) => {
          const { label, icon: Icon } = ACTIONS[a]
          return (
            <button
              key={a}
              type="button"
              role="radio"
              aria-checked={action === a}
              onClick={() => setAction(a)}
              className={cx(
                'flex items-center justify-center gap-2 rounded-lg border px-3 py-2.5 text-sm font-medium transition',
                action === a ? 'border-brand-600 bg-brand-50 text-brand-800 ring-1 ring-brand-600' : 'border-slate-200 text-slate-600 hover:bg-slate-50',
              )}
            >
              <Icon className="size-4" /> {label}
            </button>
          )
        })}
      </div>
      <p className="mt-3 text-sm text-slate-500">{ACTIONS[action].help}</p>

      <div className="mt-4 space-y-4">
        {action === 'override' && (
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="label" htmlFor="category">
                Final category <span className="font-normal text-slate-400">(AI: {complaint.ai.category})</span>
              </label>
              <select id="category" className="input" value={category} onChange={(e) => setCategory(e.target.value)}>
                {CATEGORIES.map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="priority">
                Final priority <span className="font-normal text-slate-400">(AI: {complaint.ai.priority})</span>
              </label>
              <select id="priority" className="input" value={priority} onChange={(e) => setPriority(e.target.value)}>
                {PRIORITIES.map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </div>
          </div>
        )}
        {action === 'reroute' && (
          <div>
            <label className="label" htmlFor="target">
              Reroute to
            </label>
            <select id="target" className="input" value={targetId} onChange={(e) => setTargetId(e.target.value)} disabled={!targets}>
              <option value="">{targets ? 'Choose an authority…' : 'Loading…'}</option>
              {targets?.map((t) => (
                <option key={t.id} value={t.id}>
                  {personLabel(t)}
                  {t.department ? ` — ${t.department.code}` : ''}
                </option>
              ))}
            </select>
          </div>
        )}
        <div>
          <label className="label" htmlFor="remarks">
            {action === 'resolve' ? 'Resolution note (required)' : 'Reviewer comment (recorded in the audit trail)'}
          </label>
          <textarea id="remarks" rows={3} className="input" value={remarks} onChange={(e) => setRemarks(e.target.value)} maxLength={2000} />
        </div>
        <div className="flex justify-end">
          <button type="button" className="btn-primary" disabled={invalid || busy} onClick={() => setConfirming(true)}>
            Review and confirm
          </button>
        </div>
      </div>

      <Modal
        open={confirming}
        onClose={() => !busy && setConfirming(false)}
        title={`Confirm: ${ACTIONS[action].label}`}
        description={`${complaint.complaint_id} · this action is permanent and recorded with your name.`}
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setConfirming(false)} disabled={busy}>
              Cancel
            </button>
            <button type="button" className="btn-primary" onClick={submit} disabled={busy}>
              {busy ? 'Saving…' : 'Confirm'}
            </button>
          </>
        }
      >
        <dl className="space-y-2 text-sm">
          {action === 'accept' && (
            <KeyValue label="Final values">
              {complaint.category} · {complaint.priority}
            </KeyValue>
          )}
          {action === 'override' && (
            <>
              <KeyValue label="Category">
                {complaint.category} → <strong>{category}</strong>
              </KeyValue>
              <KeyValue label="Priority">
                {complaint.priority} → <strong>{priority}</strong>
              </KeyValue>
            </>
          )}
          {action === 'reroute' && <KeyValue label="New authority">{personLabel(target)}</KeyValue>}
          <KeyValue label="Comment">{remarks.trim() || <span className="text-slate-400">None</span>}</KeyValue>
        </dl>
      </Modal>
    </Card>
  )
}
