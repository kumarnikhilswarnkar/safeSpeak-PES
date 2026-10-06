import { ArrowRight, CheckCircle2, Clock, FilePlus2, Lock, Route, Send, ShieldCheck, UserCog } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { submitConcern } from '../../api/concerns.js'
import { useAuth } from '../../auth/AuthContext.jsx'
import AiAnalysisCard from '../../components/AiAnalysisCard.jsx'
import AppShell from '../../components/AppShell.jsx'
import { PriorityBadge } from '../../components/Badges.jsx'
import { useToast } from '../../components/Toast.jsx'
import { Alert, Card, KeyValue, PageHeader, Spinner } from '../../components/ui.jsx'
import { SCOPE_LABEL, formatDateTime, personLabel } from '../../utils/format.js'

const MIN = 10
const MAX = 5000

function Result({ complaint: c, onAnother }) {
  const review = c.ai.flagged_for_review
  const last = c.routing?.last_decision
  return (
    <div className="space-y-6">
      <Alert tone="green" icon={CheckCircle2} title={`Complaint ${c.complaint_id} submitted`}>
        Keep this ID to track your complaint. Everything below happened automatically within the request.
      </Alert>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <AiAnalysisCard ai={c.ai} compact={false} />
        </div>
        <Card title="What happens next" icon={Route}>
          <dl className="space-y-3">
            <KeyValue label="Complaint ID">
              <span className="font-mono font-semibold text-brand-700">{c.complaint_id}</span>
            </KeyValue>
            <KeyValue label="Human review">
              {review ? (
                <span className="inline-flex items-center gap-1 font-medium text-violet-700">
                  <UserCog className="size-4" /> Required
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 font-medium text-emerald-700">
                  <CheckCircle2 className="size-4" /> Not required
                </span>
              )}
            </KeyValue>
            <KeyValue label={review ? 'Reviewer' : 'Assigned to'}>{personLabel(c.assigned_to)}</KeyValue>
            <KeyValue label="Priority">
              <PriorityBadge priority={c.priority} />
            </KeyValue>
            <KeyValue label="TAT">
              <span className="inline-flex items-center gap-1">
                <Clock className="size-4 text-slate-400" />
                {c.tat.stage === 'REVIEW' ? 'Review' : 'Resolution'} within {c.tat.hours} h
              </span>
              <span className="block text-xs text-slate-500">Deadline {formatDateTime(c.tat.deadline_at)}</span>
            </KeyValue>
          </dl>
          {last && (
            <p className="mt-4 rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
              Routed by the {last.chain === 'category' ? 'category-specific' : 'default'} chain for{' '}
              <strong>{last.category}</strong> → {last.rule_label} ({SCOPE_LABEL[last.target_scope]}).
            </p>
          )}
          <div className="mt-5 flex flex-col gap-2">
            <Link to={`/concerns/${c.complaint_id}`} className="btn-primary">
              Open case file <ArrowRight className="size-4" />
            </Link>
            <button type="button" className="btn-secondary" onClick={onAnother}>
              Submit another complaint
            </button>
          </div>
        </Card>
      </div>
    </div>
  )
}

export default function SubmitComplaintPage() {
  const { authRequest } = useAuth()
  const toast = useToast()
  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

  const length = description.trim().length

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const created = await submitConcern(authRequest, description.trim())
      setResult(created)
      setDescription('')
      toast(`${created.complaint_id} created`, { title: 'Complaint submitted' })
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AppShell>
      <PageHeader
        eyebrow="New complaint"
        title={result ? 'AI analysis' : 'Describe your concern'}
        description={
          result
            ? 'The local AI model analysed your complaint, the confidence check decided whether a person must review it, and the workflow assigned it with a deadline.'
            : 'Write in your own words. SafeSpeak suggests a category and priority; an authorised person reviews anything uncertain or serious.'
        }
      />

      {result ? (
        <Result complaint={result} onAnother={() => setResult(null)} />
      ) : (
        <div className="grid gap-6 lg:grid-cols-3">
          <form className="card p-5 lg:col-span-2" onSubmit={handleSubmit} noValidate>
            {error && (
              <Alert tone="red" className="mb-4">
                {error}
              </Alert>
            )}
            <label htmlFor="description" className="label">
              What happened?
            </label>
            <textarea
              id="description"
              rows={9}
              className="input resize-y text-[15px] leading-relaxed"
              placeholder="Example: The projector in room 204 has not worked for two weeks, so lectures are delayed every day."
              maxLength={MAX}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={submitting}
              autoFocus
            />
            <div className="mt-2 flex items-center justify-between text-xs text-slate-500">
              <span>{length < MIN ? `At least ${MIN} characters` : 'Looks good'}</span>
              <span className="tabular-nums">
                {description.length} / {MAX}
              </span>
            </div>
            <div className="mt-5 flex items-center justify-end gap-3 border-t border-slate-100 pt-4">
              <p className="mr-auto hidden items-center gap-1.5 text-xs text-slate-500 sm:flex">
                <Lock className="size-3.5" /> Analysed by a local model inside SafeSpeak; not sent to any external AI service.
              </p>
              <button type="submit" className="btn-accent" disabled={submitting || length < MIN}>
                {submitting ? <Spinner /> : <Send className="size-4" />}
                {submitting ? 'Analysing…' : 'Submit for triage'}
              </button>
            </div>
          </form>

          <Card title="How your complaint is handled" icon={ShieldCheck}>
            <ol className="space-y-4 text-sm">
              {[
                [FilePlus2, 'A unique SSP complaint ID is issued.'],
                [ShieldCheck, 'The AI suggests a category and priority with a confidence score.'],
                [UserCog, 'Low confidence or High/Critical priority → a human reviewer decides first.'],
                [Route, 'It is routed to the responsible authority with a deadline (TAT).'],
                [Clock, 'If the deadline passes, it escalates automatically to the next level.'],
              ].map(([Icon, text]) => (
                <li key={text} className="flex gap-3">
                  <Icon className="mt-0.5 size-4 shrink-0 text-brand-500" aria-hidden="true" />
                  <span className="text-slate-600">{text}</span>
                </li>
              ))}
            </ol>
            <p className="mt-4 border-t border-slate-100 pt-3 text-xs text-slate-500">
              Tip: mention the place, how long it has been happening, and who is affected. Specific complaints are routed
              faster.
            </p>
          </Card>
        </div>
      )}
    </AppShell>
  )
}
