import {
  Activity,
  ClipboardList,
  FilePlus2,
  FlaskConical,
  Inbox,
  LayoutDashboard,
  ListChecks,
  LogOut,
  Menu,
  Search,
  X,
} from 'lucide-react'
import { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext.jsx'
import { ROLE_LABEL, homeFor } from '../auth/roles.js'
import NotificationBell from './NotificationBell.jsx'
import { cx } from './ui.jsx'
import Wordmark from './Wordmark.jsx'

// Navigation follows the permissions the server reported for this account.
function navSections(user) {
  const can = (p) => user.permissions.includes(p)
  const work = [{ to: homeFor(user.role), label: 'Dashboard', icon: LayoutDashboard, end: true }]
  if (can('submit_complaint')) work.push({ to: '/concerns/new', label: 'New complaint', icon: FilePlus2 })
  if (can('view_own_complaints')) work.push({ to: '/concerns/mine', label: 'My complaints', icon: ClipboardList })
  if (can('view_assigned_complaints')) work.push({ to: '/review', label: 'Review queue', icon: ListChecks })
  if (can('view_scoped_complaints')) work.push({ to: '/concerns', label: 'All complaints', icon: Inbox, end: true })
  const insight = [
    { to: '/automation', label: 'TAT automation', icon: Activity },
    { to: '/research', label: 'AI evaluation', icon: FlaskConical },
  ]
  return [
    { title: 'Workspace', items: work },
    { title: 'Insights', items: insight },
  ]
}

function SideNav({ user, onNavigate }) {
  return (
    <nav className="flex flex-1 flex-col gap-6 px-3 py-4" aria-label="Main">
      {navSections(user).map((section) => (
        <div key={section.title}>
          <p className="px-3 pb-2 text-[11px] font-semibold tracking-wider text-brand-100/50 uppercase">{section.title}</p>
          <ul className="space-y-0.5">
            {section.items.map(({ to, label, icon: Icon, end }) => (
              <li key={to}>
                <NavLink
                  to={to}
                  end={end}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    cx(
                      'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                      isActive ? 'bg-white/10 text-white' : 'text-brand-100/75 hover:bg-white/5 hover:text-white',
                    )
                  }
                >
                  {({ isActive }) => (
                    <>
                      <Icon className={cx('size-4', isActive ? 'text-accent-500' : '')} aria-hidden="true" />
                      {label}
                    </>
                  )}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  )
}

function SearchBox() {
  const navigate = useNavigate()
  const [value, setValue] = useState('')
  function submit(e) {
    e.preventDefault()
    const code = value.trim().toUpperCase()
    if (code) navigate(`/concerns/${encodeURIComponent(code)}`)
    setValue('')
  }
  return (
    <form onSubmit={submit} className="relative hidden w-full max-w-xs md:block" role="search">
      <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
      <input
        className="input pl-9"
        placeholder="Open complaint by ID (SSP-2026-…)"
        aria-label="Open complaint by ID"
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
    </form>
  )
}

export default function AppShell({ children }) {
  const { user, logout } = useAuth()
  const [mobileOpen, setMobileOpen] = useState(false)
  const initials = user.name
    .split(' ')
    .map((w) => w[0])
    .slice(0, 2)
    .join('')

  const sidebar = (
    <div className="flex h-full flex-col bg-brand-900">
      <div className="flex h-16 items-center px-5">
        <Wordmark inverse />
      </div>
      <SideNav user={user} onNavigate={() => setMobileOpen(false)} />
      <div className="m-3 rounded-lg bg-white/5 p-3 text-xs text-brand-100/70">
        <p className="font-medium text-brand-100">Human-in-the-loop triage</p>
        <p className="mt-1">AI recommends. An authorised person decides.</p>
      </div>
    </div>
  )

  return (
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 lg:block">{sidebar}</aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/50" onClick={() => setMobileOpen(false)} aria-hidden="true" />
          <aside className="relative h-full w-64">{sidebar}</aside>
          <button
            type="button"
            className="absolute top-4 left-68 rounded-md bg-white/10 p-1.5 text-white"
            onClick={() => setMobileOpen(false)}
            aria-label="Close menu"
          >
            <X className="size-5" />
          </button>
        </div>
      )}

      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-slate-200 bg-white/90 px-4 backdrop-blur sm:px-6">
          <button type="button" className="btn-ghost p-2 lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Open menu">
            <Menu className="size-5" />
          </button>
          <SearchBox />
          <div className="ml-auto flex items-center gap-2">
            <NotificationBell />
            <div className="hidden h-8 w-px bg-slate-200 sm:block" aria-hidden="true" />
            <div className="flex items-center gap-3">
              <span className="grid size-8 place-items-center rounded-full bg-brand-100 text-xs font-semibold text-brand-700">
                {initials}
              </span>
              <div className="hidden leading-tight sm:block">
                <p className="text-sm font-medium text-slate-900">{user.name}</p>
                <p className="text-xs text-slate-500">
                  {ROLE_LABEL[user.role]}
                  {user.authority_level ? ` · L${user.authority_level}` : ''}
                  {user.department ? ` · ${user.department.code}` : ''}
                </p>
              </div>
            </div>
            <button type="button" className="btn-ghost p-2" onClick={logout} aria-label="Sign out" title="Sign out">
              <LogOut className="size-4" />
            </button>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:py-8">{children}</main>
      </div>
    </div>
  )
}

