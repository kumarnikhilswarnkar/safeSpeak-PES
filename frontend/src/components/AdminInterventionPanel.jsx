import { ArrowRight, Building2, Clock, RefreshCw, ShieldAlert, UserCog } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { adminReassign, getInterventionOptions } from '../api/concerns.js'
import { useAuth } from '../auth/AuthContext.jsx'
import { ROLE_SHORT, formatDateTime, personLabel } from '../utils/format.js'
import { useToast } from './Toast.jsx'
import { Alert, Card, Modal, Spinner } from './ui.jsx'

const NO_DEPARTMENT = 'none'

function designation(u) {
  return `${ROLE_SHORT[u.role] ?? u.role}${u.authority_level ? ` · L${u.authority_level}` : ''}`
}

/**
 * Administrator intervention for a complaint whose escalation chain is exhausted:
 * choose a department/office and an authority, give a mandatory reason, review the new
 * rule-based deadline, then confirm. The server re-checks everything (permission,
 * exhausted state, stale view, valid target) and records one append-only audit event.
 */
export default function AdminInterventionPanel({ complaint: c, onUpdated }) {
  const { authRequest } = useAuth()
  const toast = useToast()
  const [options, setOptions] = useState(null)
  const [loadError, setLoadError] = useState(null)
  const [department, setDepartment] = useState('')
  const [targetId, setTargetId] = useState('')
  const [reason, setReason] = useState('')
  const [confirming, setConfirming] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const load = useCallback(() => {
    setLoadError(null)
    getInterventionOptions(authRequest, c.complaint_id).then(setOptions).catch(setLoadError)
  }, [authRequest, c.complaint_id])
  useEffect(load, [load])

  const candidates = useMemo(() => {
    if (!options || !department) return []
    return options.candidates.filter((u) =>
      department === NO_DEPARTMENT ? u.department_id == null : String(u.department_id) === department,
    )
  }, [options, department])
  const target = options?.candidates.find((u) => String(u.id) === targetId)
  const minReason = options?.reason_min_length ?? 10
  const valid = target && reason.trim().length >= minReason
  const hasInstitutionWide = options?.candidates.some((u) => u.department_id == null)
  const departmentName = (id) => options?.departments.find((d) => d.id === id)?.name ?? 'Institution-wide'

  async function confirm() {
    setSaving(true)
    setError(null)
    try {
      const updated = await adminReassign(authRequest, c.complaint_id, {
        target_user_id: target.id,
        reason: reason.trim(),
        expected_assignee_id: c.assigned_to?.id ?? null,
      })
      setConfirming(false)
      toast(`${c.complaint_id} is now with ${updated.assigned_to?.name}. They have been notified.`, { title: 'Complaint reassigned' })
      onUpdated(updated)
    } catch (err) {
      setError(err.status === 409 ? `${err.message} The page will show the latest state after you reload.` : err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card
      title="Administrator intervention"
      subtitle="The escalation chain is exhausted. Choose who handles this complaint next."
      icon={ShieldAlert}
      className="border-red-200 ring-1 ring-red-100"
    >
      {loadError ? (
        <Alert tone="red" title="Could not load reassignment options">
          {loadError.message}{' '}
          <button type="button" className="underline" onClick={load}>
            Retry
          </button>
        </Alert>
      ) : !options ? (
        <div className="flex items-center gap-2 py-4 text-sm text-slate-500">
          <Spinner /> Loading eligible authorities…
        </div>
      ) : (
        <div className="space-y-5">
          <dl className="grid gap-3 rounded-lg bg-slate-50 p-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-xs text-slate-500">Currently with (last step of the chain)</dt>
              <dd className="font-medium text-slate-900">{personLabel(c.assigned_to)}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Category · priority</dt>
              <dd className="font-medium text-slate-900">
                {c.category} · {c.priority}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Missed deadline</dt>
              <dd className="text-slate-900">{formatDateTime(c.tat.deadline_at)}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Escalations so far</dt>
              <dd className="text-slate-900">{c.escalation.history.filter((h) => h.result === 'escalated').length}</dd>
            </div>
          </dl>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="int-dept" className="label flex items-center gap-1.5">
                <Building2 className="size-4 text-slate-400" aria-hidden="true" /> Department / office
              </label>
              <select
                id="int-dept"
                className="input"
                value={department}
                onChange={(e) => {
                  setDepartment(e.target.value)
                  setTargetId('')
                }}
              >
                <option value="">Choose…</option>
                {options.departments.map((d) => (
                  <option key={d.id} value={String(d.id)}>
                    {d.name}
                  </option>
                ))}
                {hasInstitutionWide && <option value={NO_DEPARTMENT}>Institution-wide (higher authorities)</option>}
              </select>
            </div>
            <div>
              <label htmlFor="int-target" className="label flex items-center gap-1.5">
                <UserCog className="size-4 text-slate-400" aria-hidden="true" /> Designation / authority
              </label>
              <select id="int-target" className="input" value={targetId} onChange={(e) => setTargetId(e.target.value)} disabled={!department}>
                <option value="">{department ? 'Choose…' : 'Choose a department first'}</option>
                {candidates.map((u) => (
                  <option key={u.id} value={String(u.id)}>
                    {u.name} — {designation(u)}
                  </option>
                ))}
              </select>
              {department && candidates.length === 0 && (
                <p className="mt-1 text-xs text-amber-700">No other active authority in this department/office.</p>
              )}
            </div>
          </div>

          <div>
            <label htmlFor="int-reason" className="label">
              Reason for reassignment <span className="font-normal text-red-600">(required)</span>
            </label>
            <textarea
              id="int-reason"
              className="input min-h-24"
              maxLength={2000}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Why this authority, and anything they need to know (recorded in the audit trail and shown to the complainant)."
            />
            <p className={`mt-1 text-xs ${reason.trim().length >= minReason ? 'text-slate-500' : 'text-amber-700'}`}>
              {reason.trim().length}/{minReason} characters minimum
            </p>
          </div>

          <div className="flex items-start gap-2.5 rounded-lg border border-slate-200 px-3 py-2.5 text-sm">
            <Clock className="mt-0.5 size-4 shrink-0 text-slate-400" aria-hidden="true" />
            <p className="text-slate-700">
              New {options.new_stage === 'REVIEW' ? 'review' : 'resolution'} deadline from the configured TAT rules:{' '}
              <strong>{options.tat.hours} h</strong> (rule #{options.tat.rule_id}), about {formatDateTime(options.tat.deadline_at)}. The
              complaint stays open ({options.new_status === 'PENDING_REVIEW' ? 'awaiting the new authority’s review' : 'assigned'}) and is
              monitored again.
            </p>
          </div>

          <div className="flex justify-end">
            <button type="button" className="btn-primary w-full sm:w-auto" disabled={!valid} onClick={() => setConfirming(true)}>
              Review and reassign
            </button>
          </div>
        </div>
      )}

      <Modal
        open={confirming}
        title="Confirm reassignment"
        description="This is recorded permanently in the audit trail. The complaint is not resolved by this action."
        onClose={() => !saving && setConfirming(false)}
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setConfirming(false)} disabled={saving}>
              Cancel
            </button>
            <button type="button" className="btn-primary" onClick={confirm} disabled={saving}>
              {saving ? <Spinner /> : <RefreshCw className="size-4" />} Confirm reassignment
            </button>
          </>
        }
      >
        {target && (
          <div className="space-y-3 text-sm">
            <div className="flex flex-col gap-2 rounded-lg bg-slate-50 p-3 sm:flex-row sm:items-center">
              <span className="min-w-0 flex-1">
                <span className="block text-xs text-slate-500">From</span>
                <span className="font-medium">{personLabel(c.assigned_to)}</span>
              </span>
              <ArrowRight className="hidden size-4 shrink-0 text-slate-400 sm:block" aria-hidden="true" />
              <span className="min-w-0 flex-1">
                <span className="block text-xs text-slate-500">To</span>
                <span className="font-medium">{target.name}</span>
                <span className="block text-xs text-slate-500">
                  {designation(target)} · {departmentName(target.department_id)}
                </span>
              </span>
            </div>
            <p>
              <span className="text-slate-500">Reason:</span> “{reason.trim()}”
            </p>
            <p>
              <span className="text-slate-500">New deadline:</span> {options.tat.hours} h, about {formatDateTime(options.tat.deadline_at)}
            </p>
            {error && <Alert tone="red">{error}</Alert>}
          </div>
        )}
      </Modal>
    </Card>
  )
}
