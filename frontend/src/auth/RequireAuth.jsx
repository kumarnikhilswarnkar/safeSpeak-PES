import { Navigate, Outlet, useLocation } from 'react-router-dom'

import ForbiddenPage from '../pages/ForbiddenPage.jsx'
import { useAuth } from './AuthContext.jsx'

/**
 * Route guard for the user interface only. It decides what to *show*; every
 * API call is still authorized by the backend independently.
 */
export default function RequireAuth({ roles, permission, children }) {
  const { status, user } = useAuth()
  const location = useLocation()

  if (status === 'loading') {
    return (
      <div className="grid min-h-screen place-items-center text-sm text-slate-500" role="status">
        Loading…
      </div>
    )
  }
  if (status !== 'authenticated') {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  if ((roles && !roles.includes(user.role)) || (permission && !user.permissions.includes(permission))) {
    return <ForbiddenPage />
  }
  return children ?? <Outlet />
}
