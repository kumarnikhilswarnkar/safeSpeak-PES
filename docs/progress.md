# SafeSpeak PES: Progress

A feature counts as implemented only when it works against the real backend and automated tests cover it.
Status as of 4 October 2026.

## Module-wise completion

Percentages are a judgement against each module's agreed scope; the "Missing" column explains every
deduction. All modules are weighted equally.

| # | Module | Status | Evidence | Missing | % |
|---|---|---|---|---|---|
| 1 | Authentication / RBAC | Complete | `POST /api/v1/auth/login`, `GET /api/v1/auth/me`, `app/api/deps.py`, `app/core/permissions.py`; `test_auth_api.py` (32), `test_authorization.py` (13), `test_permissions.py` (13), `test_security.py` (7), `test_user_service.py` (19) | Admin create/deactivate-user endpoints (accounts come from the seed); rate limiting | 90 |
| 2 | Database / migrations | Complete | 2 Alembic migrations, 8 application tables, foreign keys and CHECK constraints; `test_migrations.py` (upgrade, downgrade, no drift) | Only SQLite has been run; PostgreSQL untested | 90 |
| 3 | Complaint submission | Complete | `POST /api/v1/concerns`, `complaint_service.submit`; `test_concern_submission.py` (29) | Anonymous complaints (decision D7, deferred) | 95 |
| 4 | Complaint ID generation | Complete | `id_service.next_complaint_code` (`SSP-YYYY-NNNNNN`, `id_counters`); uniqueness test | — | 100 |
| 5 | AI triage | Partial | `triage_service.py`, `ml/train_triage.py`, `ml/artifacts/v1`; `test_triage_model.py` (12) | Rule baseline and Linear SVM not in the training pipeline; no semantic model; low accuracy (see limitations) | 80 |
| 6 | Confidence / human review | Complete | `effective_threshold`, `review_reasons`; `GET /api/v1/concerns/pending-triage`; review TAT; tests in `test_concern_submission.py`, `test_triage_model.py` | Threshold chosen on only 90 validation rows; no calibration check | 90 |
| 7 | TAT | Complete | `tat_service.py`, `tat_rules` (19 sample rules); deadline and countdown in API and UI | No admin screen to edit rules | 85 |
| 8 | Routing | Complete | `routing_service.py`, `escalation_rules` (5 sample rules); unavailable levels skipped; never routed to the complainant | No admin screen to edit the chain; first matching authority is chosen (no workload balancing) | 85 |
| 9 | Reviewer actions | Complete | `POST /api/v1/concerns/{id}/review` (accept, override, reroute, resolve); `test_concern_review.py` (30) | `IN_PROGRESS` and `CLOSED` transitions have no endpoint | 85 |
| 10 | Audit | Complete | `audit_service.record`, `complaint_events` (append-only, ORM guard); immutability test | Admin rule/user changes are not audited (no such endpoints yet) | 95 |
| 11 | TAT breach | Complete | `POST /api/v1/concerns/{id}/simulate_breach` (admin, `DEMO_MODE`); tests in `test_concern_escalation.py` | — (demo/testing mechanism by design) | 100 |
| 12 | Escalation | Partial | `POST /api/v1/concerns/escalate-overdue`, `complaint_service.escalate_overdue`; no-duplicate and end-of-chain tests | No automatic scheduler: an administrator triggers the job | 70 |
| 13 | Frontend | Partial | Login, role homes, submit, my complaints, details with timeline, review queue and actions, read-only list, admin breach/escalation tools; production build passes | No admin configuration screens; no automated frontend tests; visual polish pending | 70 |
| 14 | Tests | Partial | 198 backend tests passing | No frontend or browser-automation tests | 80 |
| 15 | Demo script | Complete | `backend/scripts/demo_flow.py` (real logins against the live API); read-only database evidence `backend/scripts/list_complaints.py` and `show_complaint.py`; `docs/MONDAY_DEMO.md` | — | 100 |
| 16 | Documentation | Complete | `docs/architecture.md`, `docs/implementation_flow.md`, `docs/MONDAY_DEMO.md`, `docs/REVIEW_II_CHECKLIST.md`, `README.md` | Detailed sequence diagram not in the repository | 90 |

**Review-II workflow scope (modules 1–16): (90+90+95+100+80+90+85+85+85+95+100+70+70+80+100+90) / 16 = 1405 / 16 = 87.8%**

### Planned modules not started

| Module | % |
|---|---|
| Research comparison in this repository (rule baseline, Linear SVM, semantic model) | 0 |
| Related-complaint retrieval (RQ4) | 0 |
| Admin configuration UI (users, TAT rules, escalation rules, settings) | 0 |
| Human evaluation study (RQ5) | 0 |
| Deployment and institutional login (PostgreSQL, Docker, university SSO or roster-based onboarding) | 0 |
| Chatbot | 0 |

**Whole planned project (22 modules, equal weights): 1405 / 22 = 63.9%**

Use 87.8% when describing the Review-II implementation scope and 63.9% for the overall project, and
say which one is meant.

## Not implemented yet

- Background scheduler for escalation (the job runs on demand via `POST /api/v1/concerns/escalate-overdue`).
- `IN_PROGRESS` and `CLOSED` transitions, reopening, complainant confirmation.
- Admin screens to edit users, TAT rules, escalation rules and settings (rules are seeded sample data).
- Anonymous complaints, notifications, attachments, analytics, chatbot.
- Rate limiting, refresh tokens, password reset; PostgreSQL deployment and Docker.
- Institutional login: accounts are seeded demo data. University SSO, or importing the official
  student/staff list with email-link activation, is planned for deployment.

## Future research work

- Rule-based baseline and TF-IDF + Linear SVM in the training pipeline; semantic model.
- Grouped cross-validation (the 90-row validation and test splits are small and not stratified).
- Confidence calibration and a fuller coverage/accuracy analysis for the threshold.
- Related-complaint retrieval (Precision@K / Recall@K).
- Human evaluation of reviewer time and agreement (RQ5).
- Real or anonymised data: the current dataset is fully synthetic.

## Current model results (v1)

Trained on the 420-row train split; threshold chosen on the 90-row validation split; reported on the
90-row test split (paraphrase groups never cross splits).

| Task | Split | Accuracy | Macro-F1 | Notes |
|---|---|---|---|---|
| Category | Test | 51.1% | 47.4% | Academic / Department F1 = 0 on test |
| Priority | Test | 53.3% | 55.6% | Critical recall 91.7% (11 of 12); High+Critical recall 61.9% (16 missed, 9 false alarms) |
| Category | Validation | 57.8% | 49.8% | |
| Priority | Validation | 68.9% | 64.7% | Critical recall 83.3% |

Full metrics, both confusion matrices and the threshold table are in `ml/artifacts/v1/metadata.json`.
