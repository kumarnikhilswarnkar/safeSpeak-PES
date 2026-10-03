import { Link } from 'react-router-dom'

import Wordmark from '../components/Wordmark.jsx'

export default function NotFoundPage() {
  return (
    <div className="page-center">
      <main className="card status-card">
        <Wordmark />
        <h1 className="status-card__title">Page not found</h1>
        <p className="muted">The page you are looking for does not exist.</p>
        <Link className="btn btn--primary" to="/">
          Go to home
        </Link>
      </main>
    </div>
  )
}
