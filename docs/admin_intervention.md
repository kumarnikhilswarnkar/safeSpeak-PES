# Administrator intervention (exhausted escalation chain)

When an open complaint misses its deadline at the **last step** of its configured escalation
chain, the TAT monitor marks it `breached_at_top` ("Chain exhausted"). No further automatic
escalation is possible, so an administrator decides who handles it next.

Code: `complaint_service.intervention_options` / `admin_reassign`
(`backend/app/services/complaint_service.py`), endpoints in `backend/app/api/v1/concerns.py`,
UI `frontend/src/components/AdminInterventionPanel.jsx` (shown on the complaint page).
Tests: `backend/tests/test_admin_intervention.py`.

## Workflow

1. The administrator dashboard lists exhausted complaints ("need administrator attention").
2. On the complaint page the administrator sees the full case (description, AI recommendation,
   human decisions, audit trail, TAT and escalation history) and an **Administrator
   intervention** section.
3. Choose a **department/office**, then a **designation/authority** in it (active department or
   higher authorities; never the complainant or the current assignee).
4. Enter a **mandatory reason** (at least 10 characters).
5. The **new deadline** comes from the configured TAT rules (same stage, category, priority and
   chain step) and is shown before confirming.
6. Confirm in a dialog that shows previous -> new authority, reason and deadline.

## What the system does

| Rule | Implementation |
|---|---|
| Only administrators | New permission `intervene_exhausted_complaints` (administrator only). It is separate from reviewer permissions: an administrator still cannot accept, override or resolve. |
| Only exhausted, open complaints | 409 otherwise (resolved complaints and complaints still inside their chain are refused). |
| No duplicate or inconsistent reassignment | The request carries `expected_assignee_id`; if the complaint changed since the page was opened -> 409. After a reassignment the chain is no longer exhausted, so a repeated request -> 409. The row is locked (`SELECT ... FOR UPDATE`) on PostgreSQL. |
| Valid target | Active authority, not the complainant, not the current assignee -> otherwise 422. |
| Never resolves | A complaint waiting for human review stays in review (review TAT); otherwise it becomes `ASSIGNED` (resolution TAT). |
| Audit | One append-only `admin_reassigned` event: administrator (actor), reason, previous and new authority and department, previous and new deadline, `breached_at_top` true -> false. The AI recommendation and earlier human decisions are untouched. |
| Notifications | The new authority and the complainant are notified (in-app notifications derived from the audit trail). |
| Continues normally | The complaint is monitored again. If the new deadline passes, there is still no higher step, so it is flagged as exhausted again for the administrator. |
| Review keeps the choice | When the new authority accepts the AI recommendation (or overrides only the priority), the administrator's choice of authority is kept; only a category change routes it by the chain for the new category. The same applies to a reviewer's manual reroute (this fixed a bug where accepting a rerouted complaint sent it back to the original reviewer). |

## API

- `GET /api/v1/concerns/{id}/intervention-options` -> eligible authorities, departments, new stage
  and status, rule-based TAT preview.
- `POST /api/v1/concerns/{id}/admin-reassign` with
  `{"target_user_id": 12, "reason": "...", "expected_assignee_id": 10}` -> the updated complaint.

No database migration was needed (existing columns and the audit table are used).
