import { AlarmClock, ArrowUpCircle, Bot, CheckCircle2, Clock, Hourglass, ShieldAlert, UserCheck, UserCog } from 'lucide-react'

import { STATUS_LABEL } from '../utils/format.js'
import { Badge } from './ui.jsx'

const STATUS_TONE = {
  PENDING_REVIEW: ['violet', UserCog],
  ASSIGNED: ['brand', Clock],
  IN_PROGRESS: ['sky', Hourglass],
  RESOLVED: ['green', CheckCircle2],
  CLOSED: ['slate', CheckCircle2],
}

export function StatusBadge({ status }) {
  const [tone, icon] = STATUS_TONE[status] ?? ['slate', null]
  return (
    <Badge tone={tone} icon={icon}>
      {STATUS_LABEL[status] ?? status}
    </Badge>
  )
}

const PRIORITY_TONE = { Low: 'slate', Medium: 'sky', High: 'amber', Critical: 'red' }

export function PriorityBadge({ priority }) {
  return (
    <Badge tone={PRIORITY_TONE[priority] ?? 'slate'}>
      <span
        className={`size-1.5 rounded-full ${
          { Low: 'bg-slate-400', Medium: 'bg-sky-500', High: 'bg-amber-500', Critical: 'bg-red-600' }[priority] ?? 'bg-slate-400'
        }`}
        aria-hidden="true"
      />
      {priority}
    </Badge>
  )
}

const TAT = {
  ON_TRACK: ['green', 'On track', Clock],
  DUE_SOON: ['amber', 'Due soon', AlarmClock],
  OVERDUE: ['red', 'Overdue', AlarmClock],
  STOPPED: ['slate', 'Stopped', CheckCircle2],
}

export function TatBadge({ state }) {
  const [tone, label, icon] = TAT[state] ?? ['slate', state, null]
  return (
    <Badge tone={tone} icon={icon}>
      {label}
    </Badge>
  )
}

export function EscalationBadge({ complaint }) {
  if (complaint.breached_at_top) {
    return (
      <Badge tone="red" icon={ShieldAlert}>
        Chain exhausted
      </Badge>
    )
  }
  if (!complaint.escalated) return null
  return (
    <Badge tone="accent" icon={ArrowUpCircle}>
      Escalated · L{complaint.escalation_level}
    </Badge>
  )
}

export function DecisionBadge({ source }) {
  if (source === 'AI_AUTO') return <Badge tone="brand" icon={Bot}>AI · auto</Badge>
  if (source === 'AI_PENDING_REVIEW') return <Badge tone="violet" icon={UserCog}>Awaiting human</Badge>
  if (source === 'HUMAN_ACCEPTED') return <Badge tone="green" icon={UserCheck}>Human · accepted</Badge>
  if (source === 'HUMAN_OVERRIDDEN') return <Badge tone="amber" icon={UserCheck}>Human · overridden</Badge>
  return null
}

/** Compact confidence bar with the review threshold marked. */
export function ConfidenceBar({ value, threshold, size = 'md' }) {
  const low = threshold != null && value < threshold
  return (
    <div className="flex items-center gap-2">
      <div className={`relative w-full overflow-hidden rounded-full bg-slate-100 ${size === 'sm' ? 'h-1.5' : 'h-2.5'}`}>
        <div
          className={`h-full rounded-full ${low ? 'bg-violet-500' : 'bg-emerald-500'}`}
          style={{ width: `${Math.max(2, Math.round(value * 100))}%` }}
        />
        {threshold != null && (
          <div
            className="absolute inset-y-0 w-0.5 bg-slate-900/70"
            style={{ left: `${threshold * 100}%` }}
            title={`Threshold ${Math.round(threshold * 100)}%`}
          />
        )}
      </div>
      <span className={`w-10 shrink-0 text-right text-xs font-medium tabular-nums ${low ? 'text-violet-700' : 'text-slate-700'}`}>
        {Math.round(value * 100)}%
      </span>
    </div>
  )
}
