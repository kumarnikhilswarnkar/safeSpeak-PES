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
    { label: 'Assigned', detail: `Step ${c.escalation_level} · TAT running`, icon: UserPlus, state: 'done' },
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
          ? { label: 'Escalated', detail: `Now at step ${c.escalation_level}`, icon: ArrowUpCircle, state: 'alert' }
          : { label: 'Resolved / escalated', detail: 'Before / after deadline', icon: CheckCircle2, state: 'upcoming' },
  ]
}

const reached = (state) => ['done', 'alert', 'danger', 'current'].includes(state)

/** Workflow progress: a vertical list on phones, a horizontal stepper from 768px. */
export default function WorkflowStepper({ complaint }) {
  const items = steps(complaint)
  return (
    <div className="card px-4 py-4">
      <ol className="flex flex-col md:flex-row md:items-start">
        {items.map((s, i) => {
          const Icon = s.state === 'done' ? Check : s.state === 'skipped' ? Minus : s.icon
          return (
            <li
              key={s.label}
              className="relative flex animate-enter items-start gap-3 pb-4 last:pb-0 md:flex-1 md:flex-col md:items-center md:gap-0 md:pb-0 md:text-center"
              style={{ animationDelay: `${i * 60}ms` }}
            >
              {/* Connector: vertical (phones) to the next step, horizontal (tablet+) from the previous one. */}
              {i < items.length - 1 && (
                <span
                  className={cx('absolute top-8 bottom-0 left-4 w-0.5 -translate-x-1/2 md:hidden', reached(items[i + 1].state) ? 'bg-emerald-400' : 'bg-slate-200')}
                  aria-hidden="true"
                />
              )}
              {i > 0 && (
                <span
                  className={cx('absolute top-4 right-1/2 hidden h-0.5 w-full -translate-y-1/2 md:block', reached(s.state) ? 'bg-emerald-400' : 'bg-slate-200')}
                  aria-hidden="true"
                />
              )}
              <span className={cx('relative z-10 grid size-8 shrink-0 place-items-center rounded-full border-2 transition-colors', STYLE[s.state])}>
                <Icon className="size-4" aria-hidden="true" />
              </span>
              <span className="min-w-0 pt-1 md:pt-0">
                <span className={cx('block text-xs font-semibold md:mt-2', s.state === 'upcoming' ? 'text-slate-400' : 'text-slate-800')}>
                  {s.label}
                </span>
                <span className="mt-0.5 block text-[11px] text-slate-500 md:px-1">{s.detail}</span>
              </span>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
