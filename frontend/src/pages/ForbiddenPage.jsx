import { Link } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext.jsx'
import { homeFor } from '../auth/roles.js'
import Wordmark from '../components/Wordmark.jsx'

export default function ForbiddenPage() {
  const { user } = useAuth()

  return (
    <div className="page-center">
      <main className="card status-card">
        <Wordmark />
        <div>
          <p className="error-code">403</p>
          <h1 className="status-card__title">You don&apos;t have access to this page</h1>
        </div>
        <p className="muted">This page is not available for your account&apos;s role.</p>
        <Link className="btn btn--primary" to={user ? homeFor(user.role) : '/login'}>
          Go to my home page
        </Link>
      </main>
    </div>
  )
}
