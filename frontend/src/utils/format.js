const IST = 'Asia/Kolkata'

export const CATEGORIES = [
  'Hostel',
  'Exam',
  'Academic / Department',
  'Infrastructure and facilities',
  'Safety and welfare',
  'Administrative / Fees',
  'Library / Transport',
  'Other',
]

export const PRIORITIES = ['Low', 'Medium', 'High', 'Critical']

export function formatDateTime(iso) {
  if (!iso) return '—'
  return new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short', timeZone: IST }).format(
    new Date(iso),
  )
}

export function formatRemaining(deadlineIso, now = Date.now()) {
  const ms = new Date(deadlineIso).getTime() - now
  const abs = Math.abs(ms)
  const hours = Math.floor(abs / 3_600_000)
  const minutes = Math.floor((abs % 3_600_000) / 60_000)
  const text = hours >= 48 ? `${Math.floor(hours / 24)}d ${hours % 24}h` : `${hours}h ${minutes}m`
  return ms >= 0 ? `${text} left` : `overdue by ${text}`
}

export const percent = (value) => `${Math.round(value * 100)}%`

export const STATUS_LABEL = {
  PENDING_REVIEW: 'Pending human review',
  ASSIGNED: 'Assigned',
  IN_PROGRESS: 'In progress',
  RESOLVED: 'Resolved',
  CLOSED: 'Closed',
}

export const DECISION_LABEL = {
  AI_PENDING_REVIEW: 'AI recommendation, awaiting review',
  AI_AUTO: 'AI recommendation (no review required)',
  HUMAN_ACCEPTED: 'Reviewer accepted AI recommendation',
  HUMAN_OVERRIDDEN: 'Reviewer overrode AI recommendation',
}

export const REASON_LABEL = {
  LOW_CATEGORY_CONFIDENCE: 'Low category confidence',
  LOW_PRIORITY_CONFIDENCE: 'Low priority confidence',
  HIGH_SEVERITY: 'High/Critical priority',
}

export const EVENT_LABEL = {
  complaint_created: 'Complaint submitted',
  ai_triaged: 'AI triage completed',
  sent_to_human_review: 'Sent to human review',
  routing_levels_skipped: 'Unavailable levels skipped',
  assigned: 'Assigned',
  accepted: 'AI recommendation accepted',
  overridden: 'AI recommendation overridden',
  rerouted: 'Rerouted',
  deadline_recalculated: 'Deadline recalculated',
  resolved: 'Resolved',
  tat_breach_simulated: 'TAT breach simulated (demo)',
  tat_breached: 'TAT breached',
  escalation_triggered: 'Escalated',
  escalation_exhausted: 'Escalation chain exhausted',
}
