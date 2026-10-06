import { ArrowUpCircle, Bot, Check, CheckCircle2, FileText, Minus, ShieldAlert, UserCheck, UserCog, UserPlus } from 'lucide-react'

import { cx } from './ui.jsx'

// done = completed, current = waiting here now, skipped = not needed, alert = escalated, upcoming = not reached
const STYLE = {
  done: 'border-emerald-500 bg-emerald-500 text-white',
  current: 'border-violet-500 bg-violet-50 text-violet-700 ring-4 ring-violet-100',
  skipped: 'border-slate-300 bg-white text-slate-400',
  alert: 'border-accent-500 bg-accent-500 text-white',
  danger: 'border-red-600 bg-red-600 text-white',
  upcoming: 'border-slate-200 bg-white text-slate-300',
}

function steps(c) {
  const flagged = c.ai.flagged_for_review
  const human = c.human_decision
  const resolved = c.status === 'RESOLVED' || c.status === 'CLOSED'
  return [
    { label: 'Submitted', detail: 'SSP ID issued', icon: FileText, state: 'done' },
    { label: 'AI analysed', detail: 'Category, priority, confidence', icon: Bot, state: 'done' },
    {
      label: 'Review check',
      detail: flagged ? 'Human review required' : 'Confident: not required',
      icon: UserCog,
      state: flagged ? (c.status === 'PENDING_REVIEW' ? 'current' : 'done') : 'skipped',
    },
    { label: 'Assigned', detail: `L${c.escalation_level} · TAT running`, icon: UserPlus, state: 'done' },
    {
      label: 'Human decision',
      detail: human ? (human.action === 'accepted' ? 'AI accepted' : 'AI overridden') : flagged ? 'Pending' : 'AI applied',
      icon: UserCheck,
      state: human ? 'done' : flagged ? 'upcoming' : 'skipped',
    },
    resolved
      ? { label: 'Resolved', detail: 'Closed with a note', icon: CheckCircle2, state: 'done' }
      : c.breached_at_top
        ? { label: 'Exhausted', detail: 'Admin attention', icon: ShieldAlert, state: 'danger' }
        : c.escalated
          ? { label: 'Escalated', detail: `Now at L${c.escalation_level}`, icon: ArrowUpCircle, state: 'alert' }
          : { label: 'Resolved / escalated', detail: 'Before / after deadline', icon: CheckCircle2, state: 'upcoming' },
  ]
}

export default function WorkflowStepper({ complaint }) {
  const items = steps(complaint)
  return (
    <div className="card overflow-x-auto px-4 py-4">
      <ol className="flex min-w-[720px] items-start">
        {items.map((s, i) => {
          const Icon = s.state === 'done' ? Check : s.state === 'skipped' ? Minus : s.icon
          return (
            <li key={s.label} className="relative flex flex-1 flex-col items-center text-center">
              {i > 0 && (
                <span
                  className={cx(
                    'absolute top-4 right-1/2 h-0.5 w-full -translate-y-1/2',
                    ['done', 'alert', 'danger', 'current'].includes(s.state) ? 'bg-emerald-400' : 'bg-slate-200',
                  )}
                  aria-hidden="true"
                />
              )}
              <span className={cx('relative z-10 grid size-8 place-items-center rounded-full border-2', STYLE[s.state])}>
                <Icon className="size-4" aria-hidden="true" />
              </span>
              <span className={cx('mt-2 text-xs font-semibold', s.state === 'upcoming' ? 'text-slate-400' : 'text-slate-800')}>
                {s.label}
              </span>
              <span className="mt-0.5 px-1 text-[11px] text-slate-500">{s.detail}</span>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
