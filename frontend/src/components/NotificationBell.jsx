import { ArrowUpCircle, Bell, Bot, CheckCircle2, ShieldAlert, UserCog, UserPlus } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { getNotifications } from '../api/insights.js'
import { useAuth } from '../auth/AuthContext.jsx'
import { timeAgo } from '../utils/format.js'
import { cx } from './ui.jsx'

const POLL_MS = 30_000

const TEXT = {
  sent_to_human_review: [UserCog, 'needs human review'],
  assigned: [UserPlus, 'was assigned'],
  accepted: [CheckCircle2, 'AI recommendation accepted by reviewer'],
  overridden: [UserCog, 'category/priority corrected by reviewer'],
  rerouted: [UserPlus, 'was rerouted'],
  escalation_triggered: [ArrowUpCircle, 'was escalated (TAT breached)'],
  escalation_exhausted: [ShieldAlert, 'reached the top of the chain'],
  tat_breached: [ShieldAlert, 'missed its deadline'],
  deadline_recalculated: [Bot, 'deadline recalculated'],
  resolved: [CheckCircle2, 'was resolved'],
}

// Read state is a per-browser convenience only; the list itself comes from the server.
function lastSeenKey(userId) {
  return `safespeak.notifications.lastSeen.${userId}`
}
function readLastSeen(userId) {
  try {
    return Number(localStorage.getItem(lastSeenKey(userId)) ?? 0)
  } catch {
    return 0
  }
}
function writeLastSeen(userId, id) {
  try {
    localStorage.setItem(lastSeenKey(userId), String(id))
  } catch {
    /* storage unavailable */
  }
}

export default function NotificationBell() {
  const { authRequest, user } = useAuth()
  const [items, setItems] = useState([])
  const [open, setOpen] = useState(false)
  const [lastSeen, setLastSeen] = useState(() => readLastSeen(user.id))
  const box = useRef(null)

  const load = useCallback(() => {
    getNotifications(authRequest)
      .then(setItems)
      .catch(() => {})
  }, [authRequest])

  useEffect(() => {
    load()
    const id = setInterval(load, POLL_MS)
    return () => clearInterval(id)
  }, [load])

  useEffect(() => {
    if (!open) return undefined
    const close = (e) => box.current && !box.current.contains(e.target) && setOpen(false)
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  const unread = items.filter((n) => n.id > lastSeen).length

  function toggle() {
    const next = !open
    setOpen(next)
    if (next && items.length) {
      writeLastSeen(user.id, items[0].id)
      setTimeout(() => setLastSeen(items[0].id), 1500)
    }
  }

  return (
    <div className="relative" ref={box}>
      <button type="button" className="btn-ghost relative p-2" onClick={toggle} aria-label={`Notifications (${unread} new)`}>
        <Bell className="size-4.5" />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 grid min-w-4.5 place-items-center rounded-full bg-accent-500 px-1 text-[10px] font-semibold text-white">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="card absolute right-0 z-40 mt-2 w-[22rem] overflow-hidden shadow-(--shadow-pop)">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
            <p className="text-sm font-semibold text-slate-900">Notifications</p>
            <p className="text-xs text-slate-500">In-app only · last 30 days</p>
          </div>
          {items.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-slate-500">Nothing new.</p>
          ) : (
            <ul className="max-h-96 divide-y divide-slate-100 overflow-y-auto">
              {items.map((n) => {
                const [Icon, text] = TEXT[n.action] ?? [Bell, n.action]
                return (
                  <li key={n.id}>
                    <Link
                      to={`/concerns/${n.complaint_id}`}
                      onClick={() => setOpen(false)}
                      className={cx('flex gap-3 px-4 py-3 hover:bg-slate-50', n.id > lastSeen && 'bg-brand-50/50')}
                    >
                      <Icon className="mt-0.5 size-4 shrink-0 text-slate-400" aria-hidden="true" />
                      <span className="min-w-0 text-sm">
                        <span className="font-mono text-xs font-medium text-brand-700">{n.complaint_id}</span>{' '}
                        <span className="text-slate-700">{text}</span>
                        <span className="mt-0.5 block text-xs text-slate-500">
                          {timeAgo(n.created_at)}
                          {n.automatic ? ' · automatic' : ''}
                        </span>
                      </span>
                    </Link>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
