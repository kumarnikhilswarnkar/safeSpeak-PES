import { STATUS_LABEL } from '../utils/format.js'

const STATUS_TONE = {
  PENDING_REVIEW: 'warning',
  ASSIGNED: 'info',
  IN_PROGRESS: 'info',
  RESOLVED: 'success',
  CLOSED: 'neutral',
}

const PRIORITY_TONE = { Low: 'neutral', Medium: 'info', High: 'warning', Critical: 'danger' }

const TAT_TONE = { ON_TRACK: 'success', DUE_SOON: 'warning', OVERDUE: 'danger', STOPPED: 'neutral' }
const TAT_LABEL = { ON_TRACK: 'On track', DUE_SOON: 'Due soon', OVERDUE: 'Overdue', STOPPED: 'Stopped' }

export function StatusBadge({ status }) {
  return <span className={`pill pill--${STATUS_TONE[status] ?? 'neutral'}`}>{STATUS_LABEL[status] ?? status}</span>
}

export function PriorityBadge({ priority }) {
  return <span className={`pill pill--${PRIORITY_TONE[priority] ?? 'neutral'}`}>{priority}</span>
}

export function TatBadge({ state }) {
  return <span className={`pill pill--${TAT_TONE[state] ?? 'neutral'}`}>{TAT_LABEL[state] ?? state}</span>
}

export function EscalationBadge({ complaint }) {
  if (!complaint.escalated && !complaint.breached_at_top) return null
  return (
    <span className="pill pill--danger">
      {complaint.breached_at_top ? 'Escalation exhausted' : `Escalated · L${complaint.escalation_level}`}
    </span>
  )
}
