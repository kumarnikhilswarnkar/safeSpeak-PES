import { NavLink } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext.jsx'
import { ROLE_LABEL, homeFor } from '../auth/roles.js'
import Wordmark from './Wordmark.jsx'

// Navigation follows the permissions the server reported for this account.
function navItems(user) {
  const can = (p) => user.permissions.includes(p)
  const items = [{ to: homeFor(user.role), label: 'Home', end: true }]
  if (can('submit_complaint')) items.push({ to: '/concerns/new', label: 'Submit complaint' })
  if (can('view_own_complaints')) items.push({ to: '/concerns/mine', label: 'My complaints' })
  if (can('view_assigned_complaints')) items.push({ to: '/review', label: 'Review queue' })
  if (can('view_scoped_complaints')) items.push({ to: '/concerns', label: 'All complaints', end: true })
  return items
}

export default function AppShell({ children }) {
  const { user, logout } = useAuth()

  return (
    <div className="shell">
      <header className="topbar">
        <Wordmark />
        <div className="topbar__user">
          <span className="topbar__name">{user.name}</span>
          <span className="pill pill--info">{ROLE_LABEL[user.role]}</span>
          <button type="button" className="btn btn--ghost" onClick={logout}>
            Sign out
          </button>
        </div>
      </header>
      <nav className="subnav" aria-label="Main">
        {navItems(user).map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end} className="subnav__link">
            {item.label}
          </NavLink>
        ))}
      </nav>
      <main className="content">{children}</main>
    </div>
  )
}
