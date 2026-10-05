import { useCallback, useEffect, useState } from 'react'
import { useLocation, useParams } from 'react-router-dom'

import {
  escalateOverdue,
  getConcern,
  getRerouteTargets,
  reviewConcern,
  simulateBreach,
} from '../../api/concerns.js'
import { useAuth } from '../../auth/AuthContext.jsx'
import { ROLE_LABEL } from '../../auth/roles.js'
import AppShell from '../../components/AppShell.jsx'
import { EscalationBadge, PriorityBadge, StatusBadge, TatBadge } from '../../components/Badges.jsx'
import useLoader from '../../hooks/useLoader.js'
import {
  CATEGORIES,
  DECISION_LABEL,
  EVENT_LABEL,
  PRIORITIES,
  REASON_LABEL,
  formatDateTime,
  formatRemaining,
  percent,
} from '../../utils/format.js'

const OPEN = ['PENDING_REVIEW', 'ASSIGNED', 'IN_PROGRESS']

function person(p) {
  if (!p) return '—'
  const level = p.authority_level ? ` · L${p.authority_level}` : ''
  return `${p.name} (${ROLE_LABEL[p.role] ?? p.role}${level})`
}

function Row({ label, children }) {
  return (
    <div className="status-row">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

/** Re-render periodically so the TAT countdown stays current. */
function useNow(intervalMs = 30_000) {
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
  const { authRequest, user } = useAuth()
  const loader = useCallback(() => getConcern(authRequest, code), [authRequest, code])
  const { data: complaint, error, loading, setData } = useLoader(loader)
  const now = useNow()

  if (loading && !complaint) {
    return (
      <AppShell>
        <p className="muted" role="status">Loading…</p>
      </AppShell>
    )
  }
  if (error) {
    return (
      <AppShell>
        <p className="alert alert--danger" role="alert">
          {error.status === 404 ? 'Complaint not found, or you do not have access to it.' : error.message}
        </p>
      </AppShell>
    )
  }

  const c = complaint
  const isOpen = OPEN.includes(c.status)
  const canAct = isOpen && user.permissions.includes('review_complaints') && c.assigned_to?.id === user.id
  const isOperator = user.permissions.includes('manage_rules_and_settings')

  return (
    <AppShell>
      {location.state?.justSubmitted && (
        <p className="alert alert--success" role="status">
          Complaint submitted. Keep your complaint ID <strong>{c.complaint_id}</strong> to track it.
        </p>
      )}

      <div className="page-head">
        <div>
          <p className="muted small">Complaint ID</p>
          <h1 className="content__title">{c.complaint_id}</h1>
        </div>
        <div className="badge-row">
          <StatusBadge status={c.status} />
          <PriorityBadge priority={c.priority} />
          <EscalationBadge complaint={c} />
        </div>
      </div>

      <div className="grid-2">
        <section className="card stack" aria-labelledby="complaint-heading">
          <h2 id="complaint-heading" className="card__title">Complaint</h2>
          <p className="description">{c.description}</p>
          <dl className="status-list">
            <Row label="Submitted by">{person(c.complainant)}</Row>
            <Row label="Submitted">{formatDateTime(c.created_at)}</Row>
            <Row label="Category">{c.category}</Row>
            <Row label="Priority">
              <PriorityBadge priority={c.priority} />
            </Row>
            <Row label="Decision">{DECISION_LABEL[c.decision_source] ?? c.decision_source}</Row>
            {c.resolution_note && <Row label="Resolution">{c.resolution_note}</Row>}
          </dl>
        </section>

        <section className="card stack" aria-labelledby="tat-heading">
          <h2 id="tat-heading" className="card__title">Assignment and TAT</h2>
          <dl className="status-list">
            <Row label="Assigned to">{person(c.assigned_to)}</Row>
            <Row label="Department">{c.handling_department?.name ?? '—'}</Row>
            <Row label="Escalation level">
              L{c.escalation_level}
              {c.escalated ? ' (escalated)' : ''}
            </Row>
            <Row label="TAT stage">{c.tat.stage === 'REVIEW' ? 'Human review' : 'Resolution'}</Row>
            <Row label="TAT">{c.tat.hours} hours</Row>
            <Row label="Deadline">{formatDateTime(c.tat.deadline_at)}</Row>
            <Row label="Time">
              <span className="badge-row">
                <TatBadge state={c.tat.state} />
                {c.tat.state !== 'STOPPED' && <span className="small">{formatRemaining(c.tat.deadline_at, now)}</span>}
              </span>
            </Row>
          </dl>
          {c.breached_at_top && (
            <p className="alert alert--danger small">
              The deadline passed at the highest configured level. An administrator must intervene.
            </p>
          )}
        </section>
      </div>

      <section className="card stack" aria-labelledby="ai-heading">
        <div>
          <h2 id="ai-heading" className="card__title">AI recommendation</h2>
          <p className="muted small">
            Suggested by {c.ai.model}. The AI does not make the final decision; an authorized reviewer does.
          </p>
        </div>
        <div className="ai-grid">
          <Meter label="Category" value={c.ai.category} confidence={c.ai.category_confidence} threshold={c.ai.threshold} />
          <Meter label="Priority" value={c.ai.priority} confidence={c.ai.priority_confidence} threshold={c.ai.threshold} />
        </div>
        <p className="small">
          Review threshold {c.ai.threshold} ({c.ai.threshold_source === 'CONFIG' ? 'configured' : 'selected on validation data'}).{' '}
          {c.ai.flagged_for_review ? (
            <strong>Human review required: {c.ai.flag_reasons.map((r) => REASON_LABEL[r] ?? r).join(', ')}.</strong>
          ) : (
            'No human review was required.'
          )}
        </p>
      </section>

      {canAct && <ReviewPanel complaint={c} onUpdated={setData} />}
      {isOperator && <DemoPanel complaint={c} onUpdated={setData} />}

      <section className="card stack" aria-labelledby="timeline-heading">
        <h2 id="timeline-heading" className="card__title">Timeline</h2>
        <ol className="timeline">
          {c.events.map((e) => (
            <li key={e.id} className="timeline__item">
              <div className="timeline__head">
                <strong>{EVENT_LABEL[e.action] ?? e.action}</strong>
                <span className="muted small">{formatDateTime(e.created_at)}</span>
              </div>
              <p className="muted small">By {e.actor ? person(e.actor) : 'System'}</p>
              <EventChange event={e} />
              {e.remarks && <p className="small">“{e.remarks}”</p>}
            </li>
          ))}
        </ol>
      </section>
    </AppShell>
  )
}

function Meter({ label, value, confidence, threshold }) {
  const low = confidence < threshold
  return (
    <div className="meter">
      <div className="meter__head">
        <span className="muted small">{label}</span>
        <strong>{value}</strong>
      </div>
      <div className="meter__track" aria-hidden="true">
        <div className={`meter__fill${low ? ' meter__fill--low' : ''}`} style={{ width: percent(confidence) }} />
        <div className="meter__threshold" style={{ left: percent(threshold) }} />
      </div>
      <span className="small">
        Confidence {percent(confidence)}
        {low ? ' — below threshold' : ''}
      </span>
    </div>
  )
}

const SHOWN_FIELDS = ['category', 'priority', 'status', 'assigned_user', 'escalation_level', 'deadline_at', 'tat_hours', 'reasons']

function display(key, value) {
  if (value == null) return '—'
  if (key === 'assigned_user') return value.name
  if (key === 'deadline_at') return formatDateTime(value)
  if (key === 'reasons') return value.map((r) => REASON_LABEL[r] ?? r).join(', ')
  if (key === 'escalation_level') return `L${value}`
  return String(value)
}

/** Shows previous → new for the fields that matter to a reader. */
function EventChange({ event }) {
  const prev = event.previous_value ?? {}
  const next = event.new_value ?? {}
  const keys = SHOWN_FIELDS.filter((k) => k in next && JSON.stringify(prev[k]) !== JSON.stringify(next[k]))
  if (keys.length === 0) return null
  return (
    <ul className="changes small">
      {keys.map((k) => (
        <li key={k}>
          <span className="muted">{k.replace('_', ' ')}:</span>{' '}
          {k in prev ? `${display(k, prev[k])} → ` : ''}
          {display(k, next[k])}
        </li>
      ))}
    </ul>
  )
}

function ReviewPanel({ complaint, onUpdated }) {
  const { authRequest } = useAuth()
  const [action, setAction] = useState(complaint.status === 'PENDING_REVIEW' ? 'accept' : 'reroute')
  const [category, setCategory] = useState(complaint.category)
  const [priority, setPriority] = useState(complaint.priority)
  const [targets, setTargets] = useState(null)
  const [targetId, setTargetId] = useState('')
  const [remarks, setRemarks] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null)

  const pending = complaint.status === 'PENDING_REVIEW'
  const humanDecided = ['HUMAN_ACCEPTED', 'HUMAN_OVERRIDDEN'].includes(complaint.decision_source)

  useEffect(() => {
    if (action !== 'reroute' || targets) return
    getRerouteTargets(authRequest, complaint.complaint_id)
      .then(setTargets)
      .catch((err) => setMessage({ tone: 'danger', text: err.message }))
  }, [action, targets, authRequest, complaint.complaint_id])

  async function submit(event) {
    event.preventDefault()
    const body = { action, remarks: remarks.trim() || undefined }
    if (action === 'override') {
      if (category !== complaint.category) body.category = category
      if (priority !== complaint.priority) body.priority = priority
    }
    if (action === 'reroute') body.target_user_id = Number(targetId)
    setBusy(true)
    setMessage(null)
    try {
      const updated = await reviewConcern(authRequest, complaint.complaint_id, body)
      onUpdated(updated)
      setRemarks('')
      setTargets(null)
      setMessage({ tone: 'success', text: 'Saved. The action has been added to the timeline.' })
    } catch (err) {
      setMessage({ tone: 'danger', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  const options = [
    !humanDecided && { value: 'accept', label: 'Accept AI recommendation' },
    { value: 'override', label: 'Override category / priority' },
    { value: 'reroute', label: 'Reroute to another authority' },
    !pending && { value: 'resolve', label: 'Resolve' },
  ].filter(Boolean)

  const overrideUnchanged = action === 'override' && category === complaint.category && priority === complaint.priority
  const disabled =
    busy || overrideUnchanged || (action === 'reroute' && !targetId) || (action === 'resolve' && !remarks.trim())

  return (
    <section className="card stack review-panel" aria-labelledby="review-heading">
      <div>
        <h2 id="review-heading" className="card__title">Your review</h2>
        <p className="muted small">
          {pending
            ? 'This complaint needs your decision before the resolution clock starts.'
            : 'This complaint is assigned to you.'}
        </p>
      </div>
      {message && (
        <p className={`alert alert--${message.tone}`} role="status">
          {message.text}
        </p>
      )}
      <form className="stack" onSubmit={submit}>
        <fieldset className="choice-group">
          <legend className="small">Action</legend>
          {options.map((o) => (
            <label key={o.value} className="choice">
              <input type="radio" name="action" value={o.value} checked={action === o.value} onChange={() => setAction(o.value)} />
              {o.label}
            </label>
          ))}
        </fieldset>

        {action === 'override' && (
          <div className="grid-2 grid-2--tight">
            <div className="field">
              <label htmlFor="category">Category</label>
              <select id="category" value={category} onChange={(e) => setCategory(e.target.value)}>
                {CATEGORIES.map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="priority">Priority</label>
              <select id="priority" value={priority} onChange={(e) => setPriority(e.target.value)}>
                {PRIORITIES.map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </div>
          </div>
        )}

        {action === 'reroute' && (
          <div className="field">
            <label htmlFor="target">Reroute to</label>
            <select id="target" value={targetId} onChange={(e) => setTargetId(e.target.value)} disabled={!targets}>
              <option value="">{targets ? 'Choose an authority…' : 'Loading…'}</option>
              {targets?.map((t) => (
                <option key={t.id} value={t.id}>
                  {person(t)}
                  {t.department ? ` — ${t.department.code}` : ''}
                </option>
              ))}
            </select>
          </div>
        )}

        <div className="field">
          <label htmlFor="remarks">{action === 'resolve' ? 'Resolution note (required)' : 'Remarks (optional)'}</label>
          <textarea id="remarks" rows={3} value={remarks} onChange={(e) => setRemarks(e.target.value)} maxLength={2000} />
        </div>

        <div className="form-actions">
          <button type="submit" className="btn btn--primary" disabled={disabled}>
            {busy ? 'Saving…' : 'Confirm'}
          </button>
        </div>
      </form>
    </section>
  )
}

/** Administrator tools for demonstrating TAT breach and escalation. */
function DemoPanel({ complaint, onUpdated }) {
  const { authRequest } = useAuth()
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null)
  const isOpen = OPEN.includes(complaint.status)

  async function run(task) {
    setBusy(true)
    setMessage(null)
    try {
      if (task === 'breach') {
        onUpdated(await simulateBreach(authRequest, complaint.complaint_id))
        setMessage({ tone: 'info', text: 'Deadline moved into the past. Now run the escalation check.' })
      } else {
        const result = await escalateOverdue(authRequest)
        onUpdated(await getConcern(authRequest, complaint.complaint_id))
        setMessage({
          tone: 'info',
          text: `Escalation check processed ${result.processed} overdue complaint(s)${
            result.processed === 0 ? ' — nothing was overdue, so nothing changed.' : '.'
          }`,
        })
      }
    } catch (err) {
      setMessage({
        tone: 'danger',
        text: err.status === 404 && task === 'breach' ? 'Demo mode is off on the server.' : err.message,
      })
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card stack demo-panel" aria-labelledby="demo-heading">
      <div>
        <h2 id="demo-heading" className="card__title">TAT breach demonstration</h2>
        <p className="muted small">
          Administrator tools. Simulating a breach works only when the server runs in demo mode and is recorded in the
          audit trail.
        </p>
      </div>
      {message && (
        <p className={`alert alert--${message.tone}`} role="status">
          {message.text}
        </p>
      )}
      <div className="form-actions">
        <button type="button" className="btn btn--secondary" onClick={() => run('breach')} disabled={busy || !isOpen}>
          Simulate TAT breach
        </button>
        <button type="button" className="btn btn--primary" onClick={() => run('escalate')} disabled={busy}>
          Run escalation check
        </button>
      </div>
    </section>
  )
}
