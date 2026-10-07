# SafeSpeak PES: Roadmap

## Phase 1: PostgreSQL, Docker and CI/CD (completed, 6 October 2026)

- PostgreSQL support (JSONB, indexes, append-only audit triggers, least-privilege app role); SQLite kept for
  local development and tests.
- Docker Compose stack: PostgreSQL, migrate job, FastAPI backend, React/nginx frontend, nginx reverse proxy,
  healthchecks; development and production overrides; GitHub Codespaces dev container.
- GitHub Actions CI: backend tests on SQLite and PostgreSQL, ML/data integrity, frontend build, Docker image
  builds, Compose smoke test (verified green on branch `final-architecture`).
- Documentation: `docs/docker.md`, `docs/ci-cd.md`, `docs/deployment.md`, `docs/security.md`.

## Phase 2: ML pipeline and final model selection (implemented, 7 October 2026; awaiting review)

- Inspectable, reproducible local ML pipeline in `ml/safespeak_ml/` on the approved 600-record dataset.
- Candidates 0–9 for category and priority separately (majority floor, frozen keyword baseline, TF-IDF and
  n-gram linear models, hybrid, MiniLM embeddings + LR, SetFit if it passes its feasibility gate).
- 40-group / 120-record holdout, repeated grouped cross-validation, calibration, per-task thresholds,
  pre-declared selection rule, generated reports, versioned artifacts (`ml/artifacts/v3`).
- Backend loads exactly the selected artifacts (`deployed.json`). No external AI service.
- Result: category = hybrid (#7), priority = words + chars + LR (#5); SetFit not evaluated (gate failed);
  disclosed deployment constraint: no PyTorch in the backend. See `docs/ml_evaluation.md`.

## Phase 3: SafeSpeak chatbot and final application features (planned, not started)

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

Other Phase 3+ items (from the implementation phases): human-review UI refinements, admin rule editing,
frontend polish, full testing pass, and production deployment (HTTPS, backups, GHCR images).

## Later / future work

Institutional SSO, server-side notification read state, anonymous-to-reviewer mode, email/SMS notifications,
native mobile app, real-world (consented, anonymised) PES complaint data for re-training.
