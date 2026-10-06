import {
  AlarmClock,
  ArrowUpCircle,
  Bot,
  CheckCircle2,
  CircleDot,
  FilePlus2,
  GitBranch,
  Route,
  ShieldAlert,
  SkipForward,
  TimerReset,
  UserCheck,
  UserCog,
  UserPlus,
} from 'lucide-react'

import { EVENT_LABEL, REASON_LABEL, ROLE_SHORT, formatDateTime } from '../utils/format.js'
import { Badge, cx } from './ui.jsx'

const EVENT_STYLE = {
  complaint_created: [FilePlus2, 'bg-slate-100 text-slate-600'],
  ai_triaged: [Bot, 'bg-brand-50 text-brand-600'],
  sent_to_human_review: [UserCog, 'bg-violet-50 text-violet-600'],
  routing_levels_skipped: [SkipForward, 'bg-amber-50 text-amber-600'],
  assigned: [UserPlus, 'bg-sky-50 text-sky-600'],
  accepted: [UserCheck, 'bg-emerald-50 text-emerald-600'],
  overridden: [UserCog, 'bg-amber-50 text-amber-700'],
  rerouted: [Route, 'bg-sky-50 text-sky-600'],
  deadline_recalculated: [TimerReset, 'bg-slate-100 text-slate-600'],
  resolved: [CheckCircle2, 'bg-emerald-50 text-emerald-600'],
  tat_breach_simulated: [TimerReset, 'bg-slate-100 text-slate-600'],
  tat_breached: [AlarmClock, 'bg-red-50 text-red-600'],
  escalation_triggered: [ArrowUpCircle, 'bg-accent-50 text-accent-600'],
  escalation_exhausted: [ShieldAlert, 'bg-red-50 text-red-600'],
}

function fmt(key, value) {
  if (value == null) return '—'
  if (key === 'assigned_user') return value.name
  if (key === 'deadline_at') return formatDateTime(value)
  if (key === 'escalation_level') return `L${value}`
  if (key === 'tat_hours') return `${value} h`
  if (key === 'reasons') return value.map((r) => REASON_LABEL[r] ?? r).join(', ')
  if (key === 'confidence' || key.endsWith('_confidence') || key === 'threshold') return `${Math.round(value * 100)}%`
  return String(value)
}

const LABELS = {
  category: 'Category',
  priority: 'Priority',
  status: 'Status',
  assigned_user: 'Assigned to',
  escalation_level: 'Level',
  deadline_at: 'Deadline',
  tat_hours: 'TAT',
  reasons: 'Reasons',
  decision_source: 'Decision',
}

function Changes({ event }) {
  const prev = event.previous_value ?? {}
  const next = event.new_value ?? {}
  if (event.action === 'ai_triaged') {
    return (
      <p className="text-xs text-slate-600">
        {next.category} ({fmt('confidence', next.category_confidence)}) · {next.priority} ({fmt('confidence', next.priority_confidence)}) ·
        threshold {fmt('threshold', next.threshold)} · model {next.model}
      </p>
    )
  }
  const keys = Object.keys(LABELS).filter((k) => k in next && JSON.stringify(prev[k]) !== JSON.stringify(next[k]))
  if (keys.length === 0 && !next.routing) return null
  return (
    <div className="space-y-1">
      {keys.length > 0 && (
        <dl className="grid gap-x-4 gap-y-0.5 text-xs sm:grid-cols-[auto_1fr]">
          {keys.map((k) => (
            <div key={k} className="contents">
              <dt className="text-slate-500">{LABELS[k]}</dt>
              <dd className="text-slate-800">
                {k in prev && <span className="text-slate-400 line-through">{fmt(k, prev[k])}</span>}
                {k in prev && ' → '}
                <span className="font-medium">{fmt(k, next[k])}</span>
              </dd>
            </div>
          ))}
        </dl>
      )}
      {next.routing && (
        <p className="flex items-center gap-1 text-xs text-slate-500">
          <GitBranch className="size-3" /> {next.routing.rule_label} · {next.routing.chain} chain for {next.routing.category}
        </p>
      )}
    </div>
  )
}

export default function AuditTimeline({ events }) {
  return (
    <ol className="relative space-y-5">
      <span className="absolute top-2 bottom-2 left-4 w-px bg-slate-200" aria-hidden="true" />
      {events.map((e) => {
        const [Icon, tone] = EVENT_STYLE[e.action] ?? [CircleDot, 'bg-slate-100 text-slate-600']
        const system = !e.actor
        return (
          <li key={e.id} className="relative flex gap-3">
            <span className={cx('relative z-10 grid size-8 shrink-0 place-items-center rounded-full ring-4 ring-white', tone)}>
              <Icon className="size-4" aria-hidden="true" />
            </span>
            <div className="min-w-0 flex-1 pt-1">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <p className="text-sm font-medium text-slate-900">{EVENT_LABEL[e.action] ?? e.action}</p>
                {system ? (
                  <Badge tone="brand" icon={Bot}>
                    {e.new_value?.triggered_by === 'automatic TAT monitor' ? 'Automatic TAT monitor' : 'System'}
                  </Badge>
                ) : (
                  <span className="text-xs text-slate-500">
                    by <span className="font-medium text-slate-700">{e.actor.name}</span> ({ROLE_SHORT[e.actor.role] ?? e.actor.role})
                  </span>
                )}
                <time className="ml-auto text-xs whitespace-nowrap text-slate-400">{formatDateTime(e.created_at)}</time>
              </div>
              <div className="mt-1">
                <Changes event={e} />
              </div>
              {e.remarks && <p className="mt-1 rounded-md bg-slate-50 px-2.5 py-1.5 text-xs text-slate-600 italic">“{e.remarks}”</p>}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
