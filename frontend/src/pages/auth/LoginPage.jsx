import { ArrowUpCircle, Bot, Info, LogIn, Timer, UserCheck } from 'lucide-react'
import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'

import { useAuth } from '../../auth/AuthContext.jsx'
import { homeFor } from '../../auth/roles.js'
import { Alert, Spinner } from '../../components/ui.jsx'
import Wordmark from '../../components/Wordmark.jsx'

const POINTS = [
  [Bot, 'Local AI triage', 'Category, priority and a calibrated confidence for every complaint.'],
  [UserCheck, 'Human in the loop', 'Uncertain or serious cases go to a reviewer, who can accept, override or reroute.'],
  [Timer, 'Automatic TAT monitoring', 'Deadlines are watched continuously, not by hand.'],
  [ArrowUpCircle, 'Automatic escalation', 'Missed deadlines move up the configured chain, with a full audit trail.'],
]

export default function LoginPage() {
  const { status, user, login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  if (status === 'authenticated') return <Navigate to={homeFor(user.role)} replace />

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
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <aside className="relative hidden overflow-hidden bg-brand-900 px-12 py-12 text-white lg:flex lg:flex-col">
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.07]"
          style={{ backgroundImage: 'radial-gradient(circle at 1px 1px, white 1px, transparent 0)', backgroundSize: '24px 24px' }}
          aria-hidden="true"
        />
        <div className="relative">
          <Wordmark inverse size="lg" />
          <h1 className="mt-16 max-w-md text-3xl leading-tight font-semibold tracking-tight">
            Human-in-the-loop campus concern triage and prioritization
          </h1>
          <p className="mt-3 max-w-md text-brand-100/80">
            AI assists. People decide. Every deadline is monitored and every action is recorded.
          </p>
          <ul className="mt-10 grid max-w-lg gap-5">
            {POINTS.map(([Icon, title, text]) => (
              <li key={title} className="flex gap-3.5">
                <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-white/10">
                  <Icon className="size-4.5 text-accent-500" aria-hidden="true" />
                </span>
                <span>
                  <span className="block text-sm font-semibold">{title}</span>
                  <span className="block text-sm text-brand-100/70">{text}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
        <p className="relative mt-auto pt-10 text-xs text-brand-100/50">MCA Capstone · Department of Computer Applications</p>
      </aside>

      <main className="flex items-center justify-center bg-slate-50 px-4 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-8 lg:hidden">
            <Wordmark size="lg" />
          </div>
          <h2 className="text-2xl font-semibold tracking-tight text-slate-900">Sign in</h2>
          <p className="mt-1 text-sm text-slate-500">Use your institutional email address. Your role comes from your account.</p>

          <form className="mt-8 space-y-5" onSubmit={handleSubmit} noValidate>
            {error && <Alert tone="red">{error}</Alert>}
            <div>
              <label htmlFor="email" className="label">
                Email
              </label>
              <input
                id="email"
                type="email"
                className="input"
                autoComplete="username"
                inputMode="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={submitting}
                placeholder="name@institution.edu"
              />
            </div>
            <div>
              <label htmlFor="password" className="label">
                Password
              </label>
              <input
                id="password"
                type="password"
                className="input"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={submitting}
              />
            </div>
            <button type="submit" className="btn-primary w-full py-2.5" disabled={submitting || !email.trim() || !password}>
              {submitting ? <Spinner /> : <LogIn className="size-4" />}
              {submitting ? 'Signing in…' : 'Sign in'}
            </button>
          </form>

          <div className="mt-8 flex gap-2.5 rounded-lg border border-amber-200 bg-amber-50 px-3.5 py-3 text-xs text-amber-900">
            <Info className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <p>
              <strong>Prototype / demo accounts.</strong> This build uses locally seeded demo accounts (one per role); passwords
              are kept in a local, git-ignored file. Institutional SSO is future work. There is no public sign-up.
            </p>
          </div>
        </div>
      </main>
    </div>
  )
}
