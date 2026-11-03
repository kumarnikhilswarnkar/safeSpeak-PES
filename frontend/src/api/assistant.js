// SafeSpeak Assistant: deterministic, database-backed answers (no external AI).
// The server re-checks access on every message; the context ID is only a hint.
// listContext = the list shown last (kind/offset/limit/total), for "show more" and "the second one".
export const askAssistant = (authRequest, message, contextComplaintId, listContext) =>
  authRequest('/assistant/messages', {
    method: 'POST',
    body: { message, context_complaint_id: contextComplaintId ?? null, list_context: listContext ?? null },
  })
