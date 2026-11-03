# SafeSpeak Assistant (Phase 3)

A chat assistant inside the application that answers questions about complaints from the
SafeSpeak database. It is **deterministic**: there is no language model and no external AI
service. Code: `backend/app/services/assistant_service.py`, `backend/app/api/v1/assistant.py`,
`frontend/src/components/assistant/`, `frontend/src/pages/AssistantPage.jsx`.
Tests: `backend/tests/test_assistant.py`.

## What it answers

| Question type | Example | Answer built from |
|---|---|---|
| Status | "status of SSP-2026-000123" | status, category, priority, current authority, review reasons, deadline |
| TAT / deadline | "when is the deadline?" | TAT stage, hours, rule ID, start, deadline, time left / overdue |
| Current authority | "who is handling it?" | assigned person, role, department, escalation step, configured chain |
| Escalation | "was it escalated?" | escalation history from the audit trail (automatic / manual, steps, people) |
| Timeline | "show the timeline" | the complaint's audit events (label, time, actor) |
| Category / priority | "category and priority" | current values, decision source, original AI output and confidences |
| Resolution | "is it resolved?" | resolution time and note, or current status |
| Lists | "show my complaints", "my queue", "any overdue?" | the same lists as the API (`/concerns/mine`, `/queue`, scoped list) |
| Why unresolved | "why is it unresolved?", "why has it not been resolved?" | current state and who has it, deadline, escalations, administrator interventions, exhausted chain, last activity (and a note that internal reasons are not recorded) |
| Human review / decision | "has a human reviewed it?", "what was the final decision?" | whether review was required and why, the reviewer's decision (accepted/changed, values, note, time) or that it is still waiting |
| Summary | "tell me about that complaint" | status, authority, deadline, escalations, decision |
| Paging | "show more", "next", "show all" | next page (8) or everything (up to 50 at a time) of the last list |

A complaint ID (`SSP-YYYY-NNNNNN`; `ssp 2026 12` is also understood) selects the complaint.
Without an ID, a follow-up uses the complaint from the previous answer ("it", "its deadline",
"that complaint", "is it overdue?"); "the second one" / "number 3" picks from the last list shown;
a user with exactly one open complaint gets that one (the reply says so); otherwise the assistant
lists the user's complaints and asks which one. Unrecognised messages get the help text (with
suggestions for the complaint being discussed); nothing is guessed.

**Conversation state** is kept by the browser and sent with each message: the complaint being
discussed and the last list shown (`list_context`: kind, offset, page size, total). It is only a
hint: every complaint and every list page is fetched again with the user's own permissions, so a
forged context cannot widen access (a student sending a "scoped" or "queue" list gets nothing).
Lists are sorted deterministically (newest first; queues and overdue lists by earliest deadline),
so pages never repeat or skip a complaint.

**Students see plain language**: model names, confidence percentages and thresholds are only
included for reviewers, read-only authorities and administrators.

## Security and privacy

- **Same authorization as the API.** A complaint is read only through
  `complaint_service.get_visible` (the rule behind `GET /concerns/{id}`); lists only through
  `list_mine` / `list_queue` / `list_scoped`. The reply is built from the same serializer as
  the complaint page, so the assistant never shows more than that page.
- **No probing.** An ID the user may not open gets exactly the same reply as an ID that
  does not exist (tested for other students, staff, other-department authorities and viewers,
  and an unassigned higher authority).
- **Identity only from the token.** The request body accepts only `message` (≤ 500 characters)
  and an optional `context_complaint_id`; any other field (e.g. `user_id`, `role`) is rejected
  with 422. The context ID is only a hint and is re-authorized on every message.
- **Authenticated, active accounts only** (401 / 403 otherwise).
- **Nothing stored.** Messages are not written to the database or logs; the conversation
  lives in the browser's memory and is cleared on sign-out or account change.
- **Read-only.** It cannot submit, review, reroute or resolve complaints.

## API

`POST /api/v1/assistant/messages` → `{ reply, intent, complaint_id, cards, suggestions }`.
`cards` carry structured data for the UI (`complaint`, `list`, `timeline`); `suggestions` are
follow-up questions shown as chips.

## Limitations

- Fixed intents and patterns (English). Questions outside them get the help text.
- It explains records; it does not give advice or predict outcomes.
