# SafeSpeak PES: Roadmap

## Phase 1: PostgreSQL, Docker and CI/CD (completed, 6 October 2026)

- PostgreSQL support (JSONB, indexes, append-only audit triggers, least-privilege app role); SQLite kept for
  local development and tests.
- Docker Compose stack: PostgreSQL, migrate job, FastAPI backend, React/nginx frontend, nginx reverse proxy,
  healthchecks; development and production overrides; GitHub Codespaces dev container.
- GitHub Actions CI: backend tests on SQLite and PostgreSQL, ML/data integrity, frontend build, Docker image
  builds, Compose smoke test (verified green on branch `final-architecture`).
- Documentation: `docs/docker.md`, `docs/ci-cd.md`, `docs/deployment.md`, `docs/security.md`.

## Phase 2: ML pipeline and final model selection (completed, 7 October 2026)

- Reproducible local ML pipeline in `ml/safespeak_ml/` on the approved 600-record dataset; candidates 0-9 for
  category and priority, 5 x 5 grouped cross-validation, 40-group / 120-record holdout, per-task calibration and
  thresholds, generated reports (`ml/reports/v3`), checksummed artifacts (`ml/artifacts/v3/deployed.json`).
- Deployed: category = hybrid (#7), threshold 0.57; priority = words + chars + LR (#5), threshold 0.63; disclosed
  deployment constraint (no PyTorch in the backend); SetFit not evaluated (failed its 10-minute gate).
- Committed as `a5a8c3a` and pushed; CI green (backend on SQLite and PostgreSQL, ML integrity, frontend build,
  Docker images and Compose smoke test). Details: `docs/ml_evaluation.md`.

## Phase 3: SafeSpeak chatbot and final application features (in progress)

The chatbot **must** be built in Phase 3 and meet all of these requirements:

1. **SafeSpeak chatbot** inside the application.
2. **Student/staff complaint-status queries** ("What is the status of my complaint?").
3. **Complaint-ID based status lookup** (e.g. "SSP-2026-000123").
4. **TAT, deadline and current-authority information** for a complaint.
5. **Strict RBAC:** a user can only ask about complaints they are allowed to see (same server-side scope rules as
   the API; out-of-scope complaints are indistinguishable from non-existent ones).
6. **Database-backed answers only:** every answer is built from the database; nothing is fabricated or guessed.
7. **No external LLM/API** unless separately approved.
8. **Docker + CI/CD integration** (runs in the Compose stack, covered by the CI pipeline).
9. **Tests for unauthorized complaint access** (other users' complaints, inactive users, unauthenticated calls).
10. **UI integration** in the React frontend.

### Phase 3 progress (7 October 2026, uncommitted, awaiting review)

| Requirement | Status |
|---|---|
| 1-7 Assistant: status, ID lookup, TAT/deadline/authority, strict RBAC, database-only answers, no external AI | Done: `docs/assistant.md` |
| 8 Docker + CI/CD | Done in code (new tests run in the existing CI job; no new service); CI not yet run on Phase 3 |
| 9 Unauthorized-access tests | Done: `backend/tests/test_assistant.py` (27 tests) |
| 10 UI integration | Done: floating assistant on every page + `/assistant` page |
| ML failure handling | Done: a missing or failing model no longer rejects complaints; they go to human review |
| Professional UI, animations, responsive 375 / 768 / 1280 px | Done: motion system, skeletons, responsive lists/dialogs/menus; checked by DOM measurement |
| One-URL deployment readiness | Done: nginx single entry point; container health no longer depends on the model |
| PES branding, collapsible sidebar, Log out/Profile placement | Done (12 October 2026) |
| Self-service profile with photo upload | Done: migration `d4e8b1f27a90`, `backend/tests/test_profile.py` |
| Inspection findings A-F re-verified | Done: `backend/tests/test_access_and_routing.py`; TAT panel scope/reset labels clarified |
| Administrator intervention for exhausted chains | Done (2 November 2026): `docs/admin_intervention.md`, `backend/tests/test_admin_intervention.py` |
| Assistant conversation engine (follow-ups, why/review/summary, paging) | Done: `docs/assistant.md`, conversation tests in `backend/tests/test_assistant.py` |
| Escalation step vs authority level display; reroute-then-accept bug; IST day buckets; metric definitions; student-facing AI card | Done (see the audit in the 2 November report) |
| One-command local start | Done: `start-safespeak.ps1` / `start-safespeak.cmd` |

Other Phase 3+ items (from the implementation phases): human-review UI refinements, admin rule editing,
frontend polish, full testing pass, and production deployment (HTTPS, backups, GHCR images).

## Later / future work

Institutional SSO, server-side notification read state, anonymous-to-reviewer mode, email/SMS notifications,
native mobile app, real-world (consented, anonymised) PES complaint data for re-training.
