import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { submitConcern } from '../../api/concerns.js'
import { useAuth } from '../../auth/AuthContext.jsx'
import AppShell from '../../components/AppShell.jsx'

const MAX = 5000

export default function SubmitComplaintPage() {
  const { authRequest } = useAuth()
  const navigate = useNavigate()
  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  const trimmed = description.trim()

  async function handleSubmit(event) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const created = await submitConcern(authRequest, trimmed)
      navigate(`/concerns/${created.complaint_id}`, { state: { justSubmitted: true } })
    } catch (err) {
      setError(err.message)
      setSubmitting(false)
    }
  }

  return (
    <AppShell>
      <div>
        <h1 className="content__title">Submit a complaint</h1>
        <p className="muted">
          Describe the concern in your own words. The system suggests a category and priority; an authorized
          reviewer makes the final decision.
        </p>
      </div>

      <form className="card stack" onSubmit={handleSubmit}>
        {error && (
          <p className="alert alert--danger" role="alert">
            {error}
          </p>
        )}
        <div className="field">
          <label htmlFor="description">Description</label>
          <textarea
            id="description"
            rows={7}
            maxLength={MAX}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            disabled={submitting}
            placeholder="What happened, where, and since when?"
            required
          />
          <span className="muted small">
            {trimmed.length < 10 ? 'At least 10 characters. ' : ''}
            {description.length}/{MAX}
          </span>
        </div>
        <div className="form-actions">
          <button type="submit" className="btn btn--primary" disabled={submitting || trimmed.length < 10}>
            {submitting ? 'Submitting…' : 'Submit complaint'}
          </button>
          <Link className="btn btn--ghost" to="/concerns/mine">
            Cancel
          </Link>
        </div>
      </form>
    </AppShell>
  )
}
