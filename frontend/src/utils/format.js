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

export const OPEN_STATUSES = ['PENDING_REVIEW', 'ASSIGNED', 'IN_PROGRESS']

export function formatDateTime(iso) {
  if (!iso) return '—'
  return new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short', timeZone: IST }).format(
    new Date(iso),
  )
}

export function formatDuration(ms) {
  const abs = Math.abs(ms)
  const days = Math.floor(abs / 86_400_000)
  const hours = Math.floor((abs % 86_400_000) / 3_600_000)
  const minutes = Math.floor((abs % 3_600_000) / 60_000)
  if (days >= 2) return `${days}d ${hours}h`
  if (days === 1 || hours > 0) return `${days * 24 + hours}h ${minutes}m`
  return `${minutes}m`
}

export function formatRemaining(deadlineIso, now = Date.now()) {
  const ms = new Date(deadlineIso).getTime() - now
  return ms >= 0 ? `${formatDuration(ms)} left` : `overdue by ${formatDuration(ms)}`
}

export function timeAgo(iso, now = Date.now()) {
  const ms = now - new Date(iso).getTime()
  if (ms < 60_000) return 'just now'
  return `${formatDuration(ms)} ago`
}

export const percent = (value, digits = 0) => (value == null ? '—' : `${(value * 100).toFixed(digits)}%`)

export const STATUS_LABEL = {
  PENDING_REVIEW: 'Human review',
  ASSIGNED: 'Assigned',
  IN_PROGRESS: 'In progress',
  RESOLVED: 'Resolved',
  CLOSED: 'Closed',
}

export const DECISION_LABEL = {
  AI_PENDING_REVIEW: 'Awaiting human review',
  AI_AUTO: 'AI recommendation applied automatically',
  HUMAN_ACCEPTED: 'Reviewer accepted the AI recommendation',
  HUMAN_OVERRIDDEN: 'Reviewer overrode the AI recommendation',
}

export const REASON_LABEL = {
  LOW_CATEGORY_CONFIDENCE: 'Category confidence below threshold',
  LOW_PRIORITY_CONFIDENCE: 'Priority confidence below threshold',
  HIGH_SEVERITY: 'High/Critical priority always needs a human',
}

export const EVENT_LABEL = {
  complaint_created: 'Complaint submitted',
  ai_triaged: 'AI analysis completed',
  sent_to_human_review: 'Human review required',
  routing_levels_skipped: 'Unavailable levels skipped',
  assigned: 'Assigned',
  accepted: 'AI recommendation accepted',
  overridden: 'AI recommendation overridden',
  rerouted: 'Rerouted by reviewer',
  deadline_recalculated: 'Deadline recalculated',
  resolved: 'Resolved',
  tat_breach_simulated: 'TAT breach simulated (demo)',
  tat_breached: 'TAT breached',
  escalation_triggered: 'Escalated',
  escalation_exhausted: 'Escalation chain exhausted',
}

export const SCOPE_LABEL = {
  COMPLAINANT_DEPARTMENT: "complainant's department",
  FIXED_DEPARTMENT: 'named office',
  INSTITUTION: 'institution-wide',
}

export const ROLE_SHORT = {
  student: 'Student',
  teaching_staff: 'Teaching staff',
  non_teaching_staff: 'Non-teaching staff',
  department_authority: 'Department authority',
  higher_authority: 'Higher authority',
  viewer: 'View-only',
  admin: 'Administrator',
}

export function personLabel(p) {
  if (!p) return '—'
  const level = p.authority_level && !p.name.includes(`(L${p.authority_level})`) ? ` · L${p.authority_level}` : ''
  return `${p.name}${level}`
}

/** Where a complaint is in the workflow, in plain words. */
export function stageLabel(c) {
  if (c.status === 'RESOLVED' || c.status === 'CLOSED') return 'Resolved'
  if (c.breached_at_top) return 'Needs admin attention'
  if (c.status === 'PENDING_REVIEW') return 'Awaiting human review'
  if (c.escalated) return `Escalated · L${c.escalation_level}`
  return `With L${c.escalation_level} authority`
}
