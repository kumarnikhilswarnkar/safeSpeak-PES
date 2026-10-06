# CI/CD

## Continuous integration: `.github/workflows/ci.yml`

Runs on every push and pull request (and manually). Any failing step fails the run.

```
backend job ──────────────┐
  pytest on SQLite         │
  pytest on PostgreSQL     ├─► docker job
  ML/data integrity        │     build backend image ─► build frontend image
frontend job ─────────────┘     generate .env (random secrets) ─► docker compose up
  npm ci ─► npm run build          wait: db/backend/frontend/proxy healthy, migrate exited 0
                                   seed ─► smoke test through the proxy
                                   verify rows in PostgreSQL ─► app role cannot DELETE
                                   (logs on failure) ─► docker compose down -v
```

| Stage | Command | Fails when |
|---|---|---|
| Backend tests (SQLite) | `pytest -m "not ml_integrity"` | any test fails |
| Backend tests (PostgreSQL) | same, with `TEST_DATABASE_URL` → CI PostgreSQL service | any test fails (includes migrations on PostgreSQL, JSONB, triggers, row locking, app-role privileges) |
| ML / data integrity | `pytest -m ml_integrity` | dataset or model checksum mismatch, incomplete metadata, model cannot load, invalid inference output |
| Frontend build | `npm ci && npm run build` | build error |
| Docker builds | `docker buildx build` backend + frontend | image build error |
| Compose health | wait loop over container health | a service is not healthy within 5 min or `migrate` fails |
| Smoke test | `scripts/smoke_test.py http://localhost:8080` | health, login, submission, AI output, audit events, human-review decision, TAT monitor, or automatic escalation fails |
| Persistence | `psql` row counts | complaints / predictions / automatic escalation not stored |
| Least privilege | `DELETE` as `safespeak_app` | the app role can delete |

CI never trains a model. It verifies the committed artifact the backend loads.
CI secrets: none are needed; the workflow generates random throwaway values for its ephemeral stack.

Run the same checks locally:
```bash
cd backend && python -m pytest -m "not ml_integrity" && python -m pytest -m ml_integrity
cd frontend && npm ci && npm run build
python scripts/generate_env.py --if-missing && docker compose up --build -d && docker compose run --rm seed
set -a; . ./.env; set +a; python scripts/smoke_test.py http://localhost:8080
```

## ML training: `.github/workflows/ml-training.yml`

Manual only (*Actions ▸ ML training (manual) ▸ Run workflow*). Trains from the approved, checksummed
dataset in `ml/data` on a clean runner and uploads `ml/artifacts/` and `ml/reports/` as a workflow
artifact for review. It never commits, deploys or reads live complaints. A person reviews the results
and commits the selected artifact; the next CI run then verifies it. (Phase 2 replaces the default
script with the modular ML pipeline.)

## Delivery (Phase 8)

`release.yml` (planned) builds versioned images on a tag and pushes them to GitHub Container Registry
(`ghcr.io/<owner>/safespeak-backend`, `…-frontend`). Deployment to a server pulls those images and runs
`docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d` (see `docs/deployment.md`).

## Branch policy (current)

Work happens on `final-architecture`; `main` is not changed until explicitly approved.
