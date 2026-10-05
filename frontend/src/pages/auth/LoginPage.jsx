import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'

import { useAuth } from '../../auth/AuthContext.jsx'
import { homeFor } from '../../auth/roles.js'
import Wordmark from '../../components/Wordmark.jsx'

export default function LoginPage() {
  const { status, user, login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  if (status === 'authenticated') {
    return <Navigate to={homeFor(user.role)} replace />
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const signedIn = await login(email.trim(), password)
      // The landing page follows the role on the server account.
      navigate(homeFor(signedIn.role), { replace: true })
    } catch (err) {
      setError(err.message)
      setPassword('')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="login">
      <aside className="login__brand" aria-hidden="true">
        <Wordmark size="lg" inverse />
        <p className="login__tagline">Human-in-the-Loop Campus Concern Triage and Prioritization</p>
        <ul className="login__points">
          <li>Report a concern</li>
          <li>Track it to resolution</li>
          <li>Every decision made by a person</li>
        </ul>
      </aside>

      <main className="login__panel">
        <form className="card login__form" onSubmit={handleSubmit} noValidate>
          <div className="login__mobile-brand">
            <Wordmark />
          </div>
          <div>
            <h1 className="login__title">Sign in</h1>
            <p className="muted">Use your institutional email address.</p>
          </div>

          {error && (
            <p className="alert alert--danger" role="alert">
              {error}
            </p>
          )}

          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              autoComplete="username"
              inputMode="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={submitting}
            />
          </div>

          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={submitting}
            />
          </div>

          <button
            type="submit"
            className="btn btn--primary btn--block"
            disabled={submitting || !email.trim() || !password}
          >
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>

          <p className="muted login__note">
            Accounts are created by the SafeSpeak administrator. Your access is determined by your account.
          </p>
        </form>
      </main>
    </div>
  )
}
