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
  MessageCircleQuestion,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  UserRound,
  X,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext.jsx'
import { ROLE_LABEL, homeFor } from '../auth/roles.js'
import AssistantLauncher from './assistant/AssistantLauncher.jsx'
import Avatar from './Avatar.jsx'
import NotificationBell from './NotificationBell.jsx'
import PesLogo from './PesLogo.jsx'
import { cx } from './ui.jsx'
import Wordmark, { ShieldMark } from './Wordmark.jsx'

const COLLAPSED_KEY = 'safespeak.sidebarCollapsed'

// Navigation follows the permissions the server reported for this account.
// Account actions (Log out, Profile) are deliberately NOT here: they live at the bottom.
function navSections(user) {
  const can = (p) => user.permissions.includes(p)
  const work = [{ to: homeFor(user.role), label: 'Dashboard', icon: LayoutDashboard, end: true }]
  if (can('submit_complaint')) work.push({ to: '/concerns/new', label: 'New complaint', icon: FilePlus2 })
  if (can('view_own_complaints')) work.push({ to: '/concerns/mine', label: 'My complaints', icon: ClipboardList })
  if (can('view_assigned_complaints')) work.push({ to: '/review', label: 'Review queue', icon: ListChecks })
  if (can('view_scoped_complaints')) work.push({ to: '/concerns', label: 'All complaints', icon: Inbox, end: true })
  work.push({ to: '/assistant', label: 'Assistant', icon: MessageCircleQuestion })
  const insight = [
    { to: '/automation', label: 'TAT automation', icon: Activity },
    { to: '/research', label: 'AI evaluation', icon: FlaskConical },
  ]
  return [
    { title: 'Workspace', items: work },
    { title: 'Insights', items: insight },
  ]
}

function readCollapsed() {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === '1'
  } catch {
    return false
  }
}

/** Tooltip for icon-only (collapsed) items: shown on hover and on keyboard focus. Visual only;
 * the accessible name comes from the link/button text. */
function Tip({ show, children }) {
  if (!show) return null
  return (
    <span
      aria-hidden="true"
      className="pointer-events-none absolute top-1/2 left-full z-50 ml-3 -translate-y-1/2 rounded-md bg-slate-900 px-2.5 py-1.5 text-xs font-medium whitespace-nowrap text-white opacity-0 shadow-lg transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100"
    >
      {children}
    </span>
  )
}

const itemClass = (collapsed, active) =>
  cx(
    'group relative flex min-h-11 items-center gap-3 rounded-lg text-sm font-medium transition-colors focus-visible:outline-accent-500 lg:min-h-10',
    collapsed ? 'justify-center px-0' : 'px-3',
    active ? 'bg-white/10 text-white' : 'text-brand-100/75 hover:bg-white/5 hover:text-white',
  )

function SideNav({ user, collapsed, onNavigate }) {
  return (
    // Collapsed: no scroll container, so the tooltips beside each icon are not clipped.
    <nav
      className={cx('flex flex-1 flex-col gap-5 py-4', collapsed ? 'overflow-visible px-2.5' : 'overflow-x-hidden overflow-y-auto px-3')}
      aria-label="Main"
    >
      {navSections(user).map((section, i) => (
        <div key={section.title}>
          {collapsed ? (
            i > 0 && <div className="mx-2 mb-3 border-t border-white/10" aria-hidden="true" />
          ) : (
            <p className="px-3 pb-2 text-[11px] font-semibold tracking-wider text-brand-100/50 uppercase">{section.title}</p>
          )}
          <ul className="space-y-0.5">
            {section.items.map(({ to, label, icon: Icon, end }) => (
              <li key={to}>
                <NavLink to={to} end={end} onClick={onNavigate} className={({ isActive }) => itemClass(collapsed, isActive)}>
                  {({ isActive }) => (
                    <>
                      {isActive && (
                        <span
                          className={cx('absolute top-2 bottom-2 w-1 animate-fade rounded-r-full bg-accent-500', collapsed ? '-left-2.5' : '-left-3')}
                          aria-hidden="true"
                        />
                      )}
                      <Icon className={cx('size-4.5 shrink-0 transition-transform group-hover:scale-110', isActive && 'text-accent-500')} aria-hidden="true" />
                      <span className={collapsed ? 'sr-only' : 'truncate'}>{label}</span>
                      <Tip show={collapsed}>{label}</Tip>
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

/** Bottom of the sidebar: who is signed in, then Log out, then Profile (the very last item). */
function AccountActions({ user, collapsed, onNavigate, onLogout }) {
  return (
    <div className={cx('border-t border-white/10 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]', collapsed ? 'px-2.5' : 'px-3')}>
      {!collapsed && (
        <div className="mb-2 flex items-center gap-3 rounded-lg bg-white/5 px-3 py-2.5">
          <Avatar className="size-9 text-xs" ring />
          <div className="min-w-0 leading-tight">
            <p className="truncate text-sm font-medium text-white">{user.name}</p>
            <p className="truncate text-xs text-brand-100/60">
              {ROLE_LABEL[user.role]}
              {user.department ? ` · ${user.department.code}` : ''}
            </p>
          </div>
        </div>
      )}
      <ul className="space-y-0.5">
        <li>
          <button type="button" onClick={onLogout} className={cx(itemClass(collapsed, false), 'w-full hover:bg-red-500/15 hover:text-red-100')}>
            <LogOut className="size-4.5 shrink-0" aria-hidden="true" />
            <span className={collapsed ? 'sr-only' : ''}>Log out</span>
            <Tip show={collapsed}>Log out</Tip>
          </button>
        </li>
        <li>
          <NavLink to="/profile" onClick={onNavigate} className={({ isActive }) => itemClass(collapsed, isActive)}>
            {({ isActive }) => (
              <>
                {collapsed ? (
                  <Avatar className="size-7 text-[10px]" ring={isActive} />
                ) : (
                  <UserRound className={cx('size-4.5 shrink-0', isActive && 'text-accent-500')} aria-hidden="true" />
                )}
                <span className={collapsed ? 'sr-only' : ''}>Profile</span>
                <Tip show={collapsed}>Profile</Tip>
              </>
            )}
          </NavLink>
        </li>
      </ul>
    </div>
  )
}

function SearchBox({ className = 'relative hidden w-full max-w-xs md:block', autoFocus, onDone }) {
  const navigate = useNavigate()
  const [value, setValue] = useState('')
  function submit(e) {
    e.preventDefault()
    const code = value.trim().toUpperCase()
    if (code) navigate(`/concerns/${encodeURIComponent(code)}`)
    setValue('')
    onDone?.()
  }
  return (
    <form onSubmit={submit} className={className} role="search">
      <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
      <input
        className="input pl-9"
        placeholder="Open complaint by ID (SSP-2026-…)"
        aria-label="Open complaint by ID"
        value={value}
        autoFocus={autoFocus}
        onChange={(e) => setValue(e.target.value)}
      />
    </form>
  )
}

export default function AppShell({ children }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = useState(readCollapsed)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const location = useLocation()
  const menuButton = useRef(null)
  const closeButton = useRef(null)

  function toggleCollapsed() {
    setCollapsed((c) => {
      try {
        localStorage.setItem(COLLAPSED_KEY, c ? '0' : '1')
      } catch {
        // Not critical: the choice just is not remembered.
      }
      return !c
    })
  }

  function signOut() {
    setMobileOpen(false)
    logout() // clears the token and session (AuthContext)
    navigate('/login', { replace: true })
  }

  // Close the phone menu/search after navigating.
  useEffect(() => {
    setMobileOpen(false)
    setSearchOpen(false)
  }, [location.pathname])

  // Phone drawer: lock the page behind it, Escape closes, focus moves in and back out.
  useEffect(() => {
    if (!mobileOpen) return undefined
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    closeButton.current?.focus()
    const opener = menuButton.current
    const onKey = (e) => e.key === 'Escape' && setMobileOpen(false)
    window.addEventListener('keydown', onKey)
    return () => {
      document.body.style.overflow = previous
      window.removeEventListener('keydown', onKey)
      opener?.focus()
    }
  }, [mobileOpen])

  // Desktop sidebar (collapsible) and phone drawer (always expanded) share the same content.
  const sidebar = (isCollapsed, inDrawer) => (
    <div className="flex h-full flex-col bg-brand-900">
      <div className={cx('flex h-16 shrink-0 items-center gap-2 border-b border-white/5', isCollapsed ? 'justify-center px-2' : 'justify-between px-4')}>
        <Link to={homeFor(user.role)} className="flex min-w-0 items-center rounded-md" aria-label="SafeSpeak PES home">
          {isCollapsed ? <ShieldMark className="size-7" inverse /> : <Wordmark inverse />}
        </Link>
        {inDrawer ? (
          <button
            ref={closeButton}
            type="button"
            className="grid size-10 place-items-center rounded-lg text-brand-100/80 hover:bg-white/10 hover:text-white"
            onClick={() => setMobileOpen(false)}
            aria-label="Close menu"
          >
            <X className="size-5" />
          </button>
        ) : (
          !isCollapsed && (
            <button
              type="button"
              onClick={toggleCollapsed}
              className="grid size-8 place-items-center rounded-lg text-brand-100/70 transition-colors hover:bg-white/10 hover:text-white"
              aria-label="Collapse sidebar"
              aria-expanded="true"
              aria-controls="app-sidebar"
              title="Collapse sidebar"
            >
              <PanelLeftClose className="size-4.5" />
            </button>
          )
        )}
      </div>
      {!inDrawer && isCollapsed && (
        <div className="flex justify-center pt-3">
          <button
            type="button"
            onClick={toggleCollapsed}
            className="group relative grid size-10 place-items-center rounded-lg bg-white/5 text-brand-100/80 ring-1 ring-white/10 transition-colors hover:bg-white/10 hover:text-white"
            aria-label="Expand sidebar"
            aria-expanded="false"
            aria-controls="app-sidebar"
          >
            <PanelLeftOpen className="size-4.5" />
            <Tip show>Expand sidebar</Tip>
          </button>
        </div>
      )}
      <SideNav user={user} collapsed={isCollapsed} onNavigate={() => setMobileOpen(false)} />
      {!isCollapsed && (
        <div className="mx-3 mb-3 rounded-lg bg-white/5 p-3 text-xs text-brand-100/70">
          <p className="font-medium text-brand-100">Human-in-the-loop triage</p>
          <p className="mt-1">AI recommends. An authorised person decides.</p>
        </div>
      )}
      <AccountActions user={user} collapsed={isCollapsed} onNavigate={() => setMobileOpen(false)} onLogout={signOut} />
    </div>
  )

  return (
    <div className="min-h-screen">
      <aside
        id="app-sidebar"
        className={cx('fixed inset-y-0 left-0 z-30 hidden transition-[width] duration-200 ease-out lg:block', collapsed ? 'w-[4.5rem]' : 'w-64')}
        aria-label="Sidebar"
      >
        {sidebar(collapsed, false)}
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <div className="absolute inset-0 animate-fade bg-slate-900/50 backdrop-blur-[2px]" onClick={() => setMobileOpen(false)} aria-hidden="true" />
          <aside className="relative h-full w-[min(18rem,85vw)] animate-drawer shadow-2xl">{sidebar(false, true)}</aside>
        </div>
      )}

      <div className={cx('min-w-0 transition-[padding] duration-200 ease-out', collapsed ? 'lg:pl-[4.5rem]' : 'lg:pl-64')}>
        <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-slate-200 bg-white/90 px-4 backdrop-blur sm:px-6">
          <button
            ref={menuButton}
            type="button"
            className="btn-ghost -ml-1 grid size-10 place-items-center p-0 lg:hidden"
            onClick={() => setMobileOpen(true)}
            aria-label="Open menu"
            aria-expanded={mobileOpen}
          >
            <Menu className="size-5" />
          </button>
          <SearchBox />
          <span className="md:hidden">
            <Wordmark />
          </span>
          <div className="ml-auto flex items-center gap-1 sm:gap-2">
            {/* Official university logo: on the white header, where its navy lettering is legible. */}
            <PesLogo className="mr-2 hidden h-8 lg:block" />
            <button
              type="button"
              className="btn-ghost grid size-10 place-items-center p-0 md:hidden"
              onClick={() => setSearchOpen((v) => !v)}
              aria-label="Find a complaint by ID"
              aria-expanded={searchOpen}
            >
              <Search className="size-4.5" />
            </button>
            <NotificationBell />
            <div className="hidden h-8 w-px bg-slate-200 sm:block" aria-hidden="true" />
            <Link to="/profile" className="flex items-center gap-3 rounded-lg p-1 transition-colors hover:bg-slate-100" aria-label="Your profile">
              <Avatar className="size-8 text-xs" />
              <div className="hidden leading-tight sm:block">
                <p className="max-w-40 truncate text-sm font-medium text-slate-900">{user.name}</p>
                <p className="max-w-40 truncate text-xs text-slate-500">
                  {ROLE_LABEL[user.role]}
                  {user.authority_level ? ` · L${user.authority_level}` : ''}
                  {user.department ? ` · ${user.department.code}` : ''}
                </p>
              </div>
            </Link>
          </div>
        </header>
        {searchOpen && (
          <div className="sticky top-16 z-20 animate-pop border-b border-slate-200 bg-white px-4 py-3 md:hidden">
            <SearchBox className="relative" autoFocus onDone={() => setSearchOpen(false)} />
          </div>
        )}
        {/* Keyed by route: each page enters with a short fade-up. Bottom padding keeps content clear of the assistant button. */}
        <main key={location.pathname} className="mx-auto max-w-7xl animate-enter px-4 pt-6 pb-24 sm:px-6 lg:pt-8">
          {children}
        </main>
      </div>
      <AssistantLauncher />
    </div>
  )
}
