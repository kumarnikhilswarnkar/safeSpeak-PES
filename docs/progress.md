# SafeSpeak PES: Progress

A feature counts as implemented only when it works against the real backend and automated tests cover it.
Status as of 6 October 2026 (preparation for the final presentation). The Review-II status of
4 October 2026 is kept in git history and in `docs/REVIEW_II_CHECKLIST.md`.

## Module-wise completion

Percentages are a judgement against each module's agreed scope; the "Missing" column explains every
deduction. All modules are weighted equally.

| # | Module | Status | Evidence | Missing | % |
|---|---|---|---|---|---|
| 1 | Authentication / RBAC | Complete | `POST /api/v1/auth/login`, `GET /api/v1/auth/me`, `app/api/deps.py`, `app/core/permissions.py`; `test_auth_api.py`, `test_authorization.py`, `test_permissions.py`, `test_security.py`, `test_user_service.py` | Admin create/deactivate-user endpoints (accounts come from the seed); rate limiting; SSO | 90 |
| 2 | Database / migrations | Complete | 3 Alembic migrations, 8 application tables, foreign keys and CHECK constraints; `test_migrations.py` (upgrade, downgrade, no drift) | Only SQLite has been run; PostgreSQL untested | 90 |
| 3 | Complaint submission | Complete | `POST /api/v1/concerns`, `complaint_service.submit`; `test_concern_submission.py` | Anonymous complaints (decision D7, deferred) | 95 |
| 4 | Complaint ID generation | Complete | `id_service.next_complaint_code` (`SSP-YYYY-NNNNNN`, `id_counters`) | — | 100 |
| 5 | AI triage | Complete | Model v3 (`ml/scripts/run_experiments.py`, `ml/artifacts/v3`): 10 candidates per task, 5 × 5 grouped CV, 120-record holdout, per-task calibration and thresholds, checksummed deployment manifest; `test_ml_pipeline.py`, `test_ml_artifacts.py`, `test_triage_model.py` | Synthetic data; category gain over keyword rules is small; priority holdout below the 80% target (see `docs/ml_evaluation.md`) | 90 |
| 6 | Confidence / human review | Complete | Threshold 0.65 chosen out of fold; trade-off table 0.20–0.65; reasons shown; review queue tabs | Priority calibration did not transfer to the test split | 95 |
| 7 | TAT | Complete | `tat_service.py`, `tat_rules`; original/current deadline, overdue duration in API and UI; rules visible read-only | No admin screen to edit rules | 85 |
| 8 | Routing | Complete | `routing_service.py`, category-specific chains (Safety; Infrastructure → Facilities Office in the demo seed); routing reason stored and shown; inactive authorities skipped | No admin screen to edit chains; no workload balancing or leave calendar | 90 |
| 9 | Reviewer actions | Complete | `POST /api/v1/concerns/{id}/review` (accept, override, reroute, resolve) with confirmation dialog; human decision shown separately from the AI output; `test_concern_review.py` | `IN_PROGRESS` and `CLOSED` transitions have no endpoint | 85 |
| 10 | Audit | Complete | `complaint_events` (append-only, ORM guard); professional timeline with actor/system, old → new values, routing reasons | Admin rule/user changes are not audited (no such endpoints yet) | 95 |
| 11 | TAT breach | Complete | `POST /api/v1/concerns/{id}/simulate_breach` (admin, `DEMO_MODE`) | — (demo/testing mechanism by design) | 100 |
| 12 | Escalation | Complete | **Automatic TAT monitor** (`app/services/tat_monitor.py`, background loop, shared lock, idempotent, exhausted-chain flag); manual "run now"; status page; `test_automation_and_insights.py`, `test_concern_escalation.py` | Single API process only (no distributed scheduler) | 95 |
| 13 | Frontend | Complete | Redesigned with Tailwind CSS, lucide icons, Recharts: role dashboards, AI analysis, case page, automation and evaluation pages, notifications, toasts; production build passes | No admin configuration screens; no automated frontend tests | 85 |
| 14 | Tests | Partial | 215 backend tests passing | No frontend or browser-automation tests | 85 |
| 15 | Demo script | Complete | `backend/scripts/demo_flow.py`; read-only DB evidence scripts; `docs/FRIDAY_DEMO.md` | — | 100 |
| 16 | Documentation | Complete | `docs/architecture.md`, `docs/ml_evaluation.md`, `docs/FRIDAY_DEMO.md`, `docs/implementation_flow.md`, `README.md` | Detailed sequence diagram not in the repository | 95 |

**Core workflow scope (modules 1–16): (90+90+95+100+90+95+85+90+85+95+100+95+85+85+100+95) / 16 = 1475 / 16 = 92.2%**

### Planned modules beyond the core workflow

| Module | % |
|---|---|
| Research comparison (keyword baseline, Linear SVM, calibration, threshold analysis done; semantic model not) | 70 |
| Related-complaint retrieval (RQ4) | 0 |
| Admin configuration UI (users, TAT rules, escalation rules, settings) | 0 |
| Human evaluation study (RQ5) | 0 |
| Deployment and institutional login (PostgreSQL, Docker, university SSO or roster-based onboarding) | 0 |
| Chatbot | 0 |

**Whole planned project (22 modules, equal weights): (1475 + 70) / 22 = 1545 / 22 = 70.2%**

Use 92.2% for the core workflow scope and 70.2% for the overall project, and say which one is meant.

## Not implemented yet

- `IN_PROGRESS` and `CLOSED` transitions, reopening, complainant confirmation.
- Admin screens to edit users, TAT rules, escalation rules and settings (read-only view exists).
- Reviewer availability beyond active/inactive accounts (leave calendar, workload balancing).
- Anonymous complaints, attachments, email/SMS notifications (in-app notifications exist), chatbot.
- Rate limiting, refresh tokens, password reset; PostgreSQL deployment and Docker; a scheduler that is
  safe across several API processes.
- Institutional login: accounts are seeded demo data. University SSO is future work.

## Future research work

- Semantic (embedding) model compared on the same protocol.
- Related-complaint retrieval (Precision@K / Recall@K).
- Human evaluation of reviewer time and agreement (RQ5).
- Real or anonymised, consented data: the current dataset is fully synthetic.

## Current model results (v2)

Selected by 5-fold grouped cross-validation on train + val (510 records); reported once on the 90-record
held-out test split. Full tables: `docs/ml_evaluation.md`.

| Task | Model | Test accuracy | Test macro-F1 | CV macro-F1 | Keyword baseline (test acc / macro-F1) |
|---|---|---|---|---|---|
| Category | Hybrid (words + chars + keyword counts + LR) | 65.6% | 57.8% | 65.1% ± 6.2 | 51.1% / 42.8% |
| Priority | TF-IDF words + LR | 50.0% | 52.2% | 59.6% ± 7.0 | 40.0% / 25.2% |

Threshold 0.65: on the test split 19 of 90 complaints would be routed automatically (deployed policy with
the High/Critical rule) and 71 reviewed by a person.
