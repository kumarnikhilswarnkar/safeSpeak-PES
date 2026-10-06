import { ShieldX } from 'lucide-react'
import { Link } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext.jsx'
import { homeFor } from '../auth/roles.js'
import CenteredPage from '../components/CenteredPage.jsx'

export default function ForbiddenPage() {
  const { user } = useAuth()
  return (
    <CenteredPage>
      <ShieldX className="size-8 text-red-500" aria-hidden="true" />
      <p className="mt-3 text-sm font-semibold text-red-600">403 · Forbidden</p>
      <h1 className="mt-1 text-xl font-semibold text-slate-900">You don&apos;t have access to this page</h1>
      <p className="mt-2 text-sm text-slate-500">This page is not available for your account&apos;s role. The server enforces the same rule.</p>
      <Link className="btn-primary mt-6 w-full" to={user ? homeFor(user.role) : '/login'}>
        Go to my dashboard
      </Link>
    </CenteredPage>
  )
}
