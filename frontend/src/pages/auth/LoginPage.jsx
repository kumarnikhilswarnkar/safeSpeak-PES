import { ArrowRight, ArrowUpCircle, Bot, Eye, EyeOff, FilePlus2, Info, LogIn, MessageCircleQuestion, Timer, UserCheck } from 'lucide-react'
import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'

import campusPhoto from '../../assets/brand/pes-campus.webp'
import { useAuth } from '../../auth/AuthContext.jsx'
import { homeFor } from '../../auth/roles.js'
import PesLogo from '../../components/PesLogo.jsx'
import { Alert, AnimatedText, Spinner } from '../../components/ui.jsx'
import Wordmark from '../../components/Wordmark.jsx'

const POINTS = [
  [Bot, 'Local AI triage', 'Category, priority and a calibrated confidence for every complaint, computed on our own server.'],
  [UserCheck, 'Human in the loop', 'Uncertain or serious cases go to a reviewer, who can accept, override or reroute.'],
  [Timer, 'Automatic TAT monitoring', 'Every deadline is watched continuously, not by hand.'],
  [ArrowUpCircle, 'Automatic escalation', 'Missed deadlines move up the configured chain, with a full audit trail.'],
  [MessageCircleQuestion, 'SafeSpeak Assistant', 'Ask for status, deadline or timeline, answered from live records.'],
]

const FLOW = [
  [FilePlus2, 'Submit'],
  [Bot, 'AI triage'],
  [UserCheck, 'Human review'],
  [Timer, 'TAT tracked'],
]

/** PES University campus photograph under a SafeSpeak navy overlay (fixed: covers the viewport, never stretched). */
function CampusBackground() {
  return (
    <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden bg-brand-900" aria-hidden="true">
      <img
        src={campusPhoto}
        alt=""
        width={750}
        height={500}
        decoding="async"
        className="size-full animate-fade object-cover object-[62%_45%] [animation-duration:900ms]"
      />
      {/* Stronger on the left/top where text sits, lighter on the right so the campus stays visible. */}
      <div className="absolute inset-0 bg-gradient-to-br from-brand-950/92 via-brand-900/80 to-brand-800/60" />
      <div className="absolute inset-x-0 bottom-0 h-1/3 bg-gradient-to-t from-brand-950/60 to-transparent" />
    </div>
  )
}

export default function LoginPage() {
  const { status, user, login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
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
    <div className="relative isolate grid min-h-dvh lg:grid-cols-[1.15fr_1fr]">
      <CampusBackground />

      {/* Story (desktop) / compact headline (phones and tablets), white text on the overlay. */}
      <aside className="flex flex-col px-5 pt-8 pb-14 text-white sm:px-8 lg:px-12 lg:py-12">
        <span className="inline-block animate-fade">
          <Wordmark inverse size="lg" />
        </span>
        <AnimatedText
          as="h1"
          delay={150}
          text="Campus concerns, triaged in seconds and decided by people."
          className="mt-6 block max-w-lg text-xl leading-snug font-semibold tracking-tight text-balance sm:text-2xl lg:mt-14 lg:text-[2.1rem] lg:leading-tight"
        />
        <p className="mt-4 hidden max-w-md animate-enter text-brand-100/85 [animation-delay:500ms] lg:block">
          SafeSpeak PES routes every grievance to the right authority, watches every deadline, and keeps a complete,
          tamper-evident record.
        </p>

        <ol className="mt-8 hidden max-w-lg animate-enter flex-wrap items-center gap-2 [animation-delay:650ms] lg:flex" aria-label="How it works">
          {FLOW.map(([Icon, label], i) => (
            <li key={label} className="flex items-center gap-2">
              <span className="flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1.5 text-xs font-medium ring-1 ring-white/20 backdrop-blur-sm">
                <Icon className="size-3.5 text-accent-500" aria-hidden="true" />
                {label}
              </span>
              {i < FLOW.length - 1 && <ArrowRight className="size-3.5 text-brand-100/50" aria-hidden="true" />}
            </li>
          ))}
        </ol>

        <ul className="mt-10 hidden max-w-lg gap-4 lg:grid">
          {POINTS.map(([Icon, title, text], i) => (
            <li key={title} className="flex animate-enter gap-3.5" style={{ animationDelay: `${800 + i * 70}ms` }}>
              <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-white/10 ring-1 ring-white/15">
                <Icon className="size-4.5 text-accent-500" aria-hidden="true" />
              </span>
              <span>
                <span className="block text-sm font-semibold">{title}</span>
                <span className="block text-sm text-brand-100/75">{text}</span>
              </span>
            </li>
          ))}
        </ul>
        <p className="mt-auto hidden pt-10 text-xs text-brand-100/60 lg:block">
          PES University, Bengaluru · MCA Capstone, Department of Computer Applications
        </p>
      </aside>

      <main className="flex items-start justify-center px-4 pb-10 lg:items-center lg:px-10 lg:py-12">
        <div className="-mt-6 w-full max-w-md animate-enter rounded-2xl bg-white/97 p-6 shadow-(--shadow-pop) ring-1 ring-black/5 [animation-delay:120ms] sm:p-8 lg:mt-0">
          {/* Official logo on the white card: its navy lettering needs a light background to stay legible. */}
          <div className="flex items-center justify-between gap-4 border-b border-slate-100 pb-5">
            <PesLogo className="h-11 sm:h-12" />
            <span className="text-right text-[11px] leading-tight font-medium tracking-wide text-slate-500 uppercase">
              Grievance
              <br />
              portal
            </span>
          </div>

          <h2 className="mt-6 text-2xl font-semibold tracking-tight text-slate-900">Sign in</h2>
          <p className="mt-1 text-sm text-slate-500">Use your institutional email address. Your role comes from your account.</p>

          <form className="mt-7 space-y-5" onSubmit={handleSubmit} noValidate>
            {error && (
              <div className="animate-pop">
                <Alert tone="red">{error}</Alert>
              </div>
            )}
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
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  className="input pr-11"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={submitting}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute inset-y-0 right-0 grid w-11 place-items-center rounded-r-lg text-slate-400 hover:text-slate-600"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  aria-pressed={showPassword}
                >
                  {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
            </div>
            <button type="submit" className="btn-primary group w-full py-2.5" disabled={submitting || !email.trim() || !password}>
              {submitting ? <Spinner /> : <LogIn className="size-4" />}
              {submitting ? 'Signing in…' : 'Sign in'}
              {!submitting && <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" aria-hidden="true" />}
            </button>
          </form>

          <div className="mt-7 flex gap-2.5 rounded-lg border border-amber-200 bg-amber-50 px-3.5 py-3 text-xs text-amber-900">
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
