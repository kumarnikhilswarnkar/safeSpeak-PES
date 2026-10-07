# SafeSpeak PES: Implementation Flow (Pseudocode → Modules)

This maps the end-to-end grievance workflow to the code that exists in this repository today.
Paths are relative to the repository root; line numbers refer to the current source.
Every API path is under `/api/v1`.

## End-to-end pseudocode

```
LOGIN(email, password)                                   # credentials only in the JSON body
    if no institutional domains configured  -> 503
    if email domain not allowed             -> 401
    user = find user by email
    if user missing or password wrong       -> 401 (same message for both)
    if user inactive                        -> 403
    return JWT(sub = user.id, role, exp)

AUTHENTICATE(request)                                    # on every protected call
    token = Authorization: Bearer <JWT>; verify signature, expiry, issuer, type   else 401
    user = load user by token.sub from DATABASE           (role is taken from here, not the token)
    if user inactive -> 403
    require_permission(user.role, P)                      else 403

SUBMIT_COMPLAINT(user, description)                      # body contains description only
    complaint_code = GENERATE_SSP_ID()
    ai = AI_TRIAGE(description)
    reasons = CONFIDENCE_CHECK(ai)
    status = PENDING_REVIEW if reasons else ASSIGNED
    routing = ROUTING(complaint, level = 1)
    deadline = TAT_CALCULATION(stage = REVIEW if reasons else RESOLUTION)
    store complaint, store ai_prediction (immutable)
    AUDIT(complaint_created, ai_triaged, [sent_to_human_review], [routing_levels_skipped], assigned)

GENERATE_SSP_ID()
    year = current year in Asia/Kolkata
    n = UPDATE id_counters SET last_value = last_value + 1 WHERE year = year RETURNING last_value
    return "SSP-{year}-{n:06d}"                          # UNIQUE constraint as final safeguard

AI_TRIAGE(text)
    category, category_confidence = argmax/max of category model probabilities
    priority, priority_confidence = argmax/max of priority model probabilities
    confidence = min(category_confidence, priority_confidence)

CONFIDENCE_CHECK(ai)
    threshold = CONFIDENCE_THRESHOLD if configured else model metadata (cross-validation-selected, 0.65 for v2)
    reasons = []
    if ai.category_confidence < threshold: reasons += LOW_CATEGORY_CONFIDENCE
    if ai.priority_confidence < threshold: reasons += LOW_PRIORITY_CONFIDENCE
    if ai.priority in {High, Critical}:    reasons += HIGH_SEVERITY
    return reasons                                        # non-empty -> HUMAN REVIEW REQUIRED

TAT_CALCULATION(stage, category, priority, level)
    rule = most specific active TATRule matching (stage, category|any, priority|any, level|any)
    if none or ambiguous -> 503 (no hidden default)
    deadline = stage_start + rule.tat_hours

ROUTING(complaint, start_level)
    chain = category's EscalationRules, else the default chain
    for rule in chain with level >= start_level:
        assignee = first active user with rule.role and rule.authority_level in rule.scope,
                   excluding the complainant
        if assignee: return (level, assignee)
    return none                                           # chain exhausted

REVIEW(reviewer, complaint, action)
    require review permission AND complaint.assigned_user == reviewer AND reviewer != complainant
    ACCEPT:   decision = HUMAN_ACCEPTED
    OVERRIDE: new category/priority required and must differ; decision = HUMAN_OVERRIDDEN
    REROUTE:  target must be another active authority; reassign; new deadline for current stage
    RESOLVE:  only after review; note required; status = RESOLVED
    if complaint was PENDING_REVIEW and action is accept/override:
        ROUTING(level = current); status = ASSIGNED; TAT_CALCULATION(RESOLUTION)
    AUDIT(action, actor = reviewer, previous, new, remarks)

TAT_BREACH(admin, complaint)                             # demo/testing only, DEMO_MODE=true
    complaint.deadline = now - 1 minute
    AUDIT(tat_breach_simulated, actor = admin, previous deadline, new deadline)

ESCALATION(triggered_by)                                 # automatic TAT monitor every N s (actor = system);
                                                         # admin can also run it now; one shared lock
    for complaint open AND deadline < now AND not breached_at_top:
        AUDIT(tat_breached)
        routing = ROUTING(complaint, level = current + 1)
        if none: breached_at_top = true; AUDIT(escalation_exhausted)       # once only
        else: reassign; escalated = true; TAT_CALCULATION(same stage, new level)
              AUDIT(escalation_triggered, previous assignee/deadline, new assignee/deadline)
    # repeat calls find nothing new: deadline is now in the future or breached_at_top is set
```

## Step → module mapping

Line numbers (l.NN) refer to the Review-II commit `86fa120`; later changes are described in
`docs/architecture.md` ("Friday release").

| Step | Backend file (function) | API endpoint | Database table(s) | Frontend page |
|---|---|---|---|---|
| **Login** | `backend/app/api/v1/auth.py` (`login`, l.16) → `backend/app/services/auth_service.py` (`authenticate`, l.31) → `backend/app/core/security.py` (`verify_password` l.29, `create_access_token` l.50) | `POST /auth/login` | `users`, `departments` | `frontend/src/pages/auth/LoginPage.jsx` |
| **Authenticate** | `backend/app/api/deps.py` (`get_current_user` l.29, `require_permission` l.57) → `security.py` (`decode_access_token` l.74); roles/permissions in `backend/app/core/permissions.py` | `GET /auth/me`; used by every protected route | `users` | `frontend/src/auth/AuthContext.jsx`, `frontend/src/auth/RequireAuth.jsx` |
| **Submit complaint** | `backend/app/api/v1/concerns.py` (`submit_concern`, l.50) → `backend/app/services/complaint_service.py` (`submit`, l.169); request schema `backend/app/schemas/complaint.py` (`ComplaintCreate`) | `POST /concerns` | `complaints` | `frontend/src/pages/complaints/SubmitComplaintPage.jsx` |
| **Generate SSP ID** | `backend/app/services/id_service.py` (`next_complaint_code`, l.14) | (inside `POST /concerns`) | `id_counters`, `complaints.complaint_code` (UNIQUE) | Shown on `ComplaintDetailPage.jsx` |
| **AI triage** | `backend/app/services/triage_service.py` (`DeployedTriageModel.predict`); models selected by `ml/scripts/run_experiments.py`, listed in `ml/artifacts/v3/deployed.json` | (inside `POST /concerns`) | `ai_predictions` (immutable) | "AI recommendation" card on `ComplaintDetailPage.jsx` |
| **Confidence check** | `triage_service.py` (`effective_threshold` l.127, `review_reasons` l.137); settings in `backend/app/core/config.py` (`confidence_threshold`, `review_high_severity`) | (inside `POST /concerns`) | `ai_predictions.threshold`, `.flag_reasons`; `complaints.review_reasons` | Confidence meters on `ComplaintDetailPage.jsx` |
| **Human review if required** | `complaint_service.py` (`submit` sets `PENDING_REVIEW`; `list_pending_review` l.132) | `GET /concerns/pending-triage` | `complaints.status`, `complaint_events` (`sent_to_human_review`) | `frontend/src/pages/complaints/ComplaintListPages.jsx` (`ReviewQueuePage`, "Needs human review") |
| **TAT calculation** | `backend/app/services/tat_service.py` (`resolve_rule` l.14, `apply_deadline` l.42); sample rules `backend/seed/prototype_rules.py` | (inside submit, review, escalation) | `tat_rules`; `complaints.tat_rule_id`, `.tat_hours`, `.deadline_at` | "Assignment and TAT" card on `ComplaintDetailPage.jsx` |
| **Routing** | `backend/app/services/routing_service.py` (`chain_for` l.20, `find_assignee` l.38, `route_from_level` l.55) | (inside submit, review, escalation) | `escalation_rules`; `complaints.assigned_user_id`, `.escalation_level` | "Assigned to" on `ComplaintDetailPage.jsx`; `ReviewQueuePage` |
| **Review** | `concerns.py` (`review_concern` l.115) → `complaint_service.py` (`_get_for_review` l.261, `review` l.292) | `POST /concerns/{id}/review`; `GET /concerns/{id}/reroute-targets`; `GET /concerns/queue` | `complaints` | `ComplaintDetailPage.jsx` ("Your review" panel) |
| **Accept / Override / Reroute** | `complaint_service.py` (`review` branches; `_confirm_review` l.274); request schema `ReviewRequest` (unknown fields rejected) | `POST /concerns/{id}/review` with `action` = `accept` / `override` / `reroute` (/ `resolve`) | `complaints.category`, `.priority`, `.decision_source`, `.assigned_user_id` | `ComplaintDetailPage.jsx` |
| **Audit** | `backend/app/services/audit_service.py` (`record`, l.10); append-only guard in `backend/app/models/complaint.py` (`_refuse_change`) | `GET /concerns/{id}` (`events`) | `complaint_events` | "Timeline" on `ComplaintDetailPage.jsx` |
| **TAT breach** | `concerns.py` (`simulate_breach` l.133, gated by `_require_demo_mode` l.43) → `complaint_service.py` (`simulate_breach`, l.396) | `POST /concerns/{id}/simulate_breach` (admin, `DEMO_MODE=true`) | `complaints.deadline_at`; `complaint_events` (`tat_breach_simulated`) | "TAT breach demonstration" panel on `ComplaintDetailPage.jsx` (admin) |
| **Escalation** | `concerns.py` (`escalate_overdue` l.85) → `complaint_service.py` (`escalate_overdue`, l.422) → `routing_service.route_from_level`, `tat_service.resolve_rule` | Automatic: `app/services/tat_monitor.py` (background loop); manual: `POST /concerns/escalate-overdue`, `POST /system/automation/run` (admin) | `complaints` (`assigned_user_id`, `escalation_level`, `escalated`, `breached_at_top`, `deadline_at`); `complaint_events` (`tat_breached`, `escalation_triggered`, `escalation_exhausted`) | Escalation card and audit timeline on `ComplaintDetailPage.jsx`; `AutomationPage.jsx` (monitor status) |

Database schema: migrations `backend/alembic/versions/2026_10_03_2004-897c2c62eb4b_create_departments_and_users.py`
and `backend/alembic/versions/2026_10_04_0219-f0ec376ae4d3_add_complaint_workflow_tables.py`;
models in `backend/app/models/`.

## Not part of the current flow

- `IN_PROGRESS` and `CLOSED` statuses exist in the model but no endpoint sets them.
