// Complaint API calls. Each takes the authRequest function from useAuth(), so the
// JWT is attached and an expired session signs the user out.

export const submitConcern = (authRequest, description) =>
  authRequest('/concerns', { method: 'POST', body: { description } })

export const listMine = (authRequest) => authRequest('/concerns/mine')
export const listQueue = (authRequest) => authRequest('/concerns/queue')
export const listPendingReview = (authRequest) => authRequest('/concerns/pending-triage')
export const listInScope = (authRequest) => authRequest('/concerns')

export const getConcern = (authRequest, code) => authRequest(`/concerns/${encodeURIComponent(code)}`)

export const getRerouteTargets = (authRequest, code) =>
  authRequest(`/concerns/${encodeURIComponent(code)}/reroute-targets`)

export const reviewConcern = (authRequest, code, body) =>
  authRequest(`/concerns/${encodeURIComponent(code)}/review`, { method: 'POST', body })

export const simulateBreach = (authRequest, code) =>
  authRequest(`/concerns/${encodeURIComponent(code)}/simulate_breach`, { method: 'POST' })

export const escalateOverdue = (authRequest) => authRequest('/concerns/escalate-overdue', { method: 'POST' })
