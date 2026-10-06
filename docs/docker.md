# Docker: running the complete SafeSpeak PES stack

## Where SafeSpeak runs

| Environment | What runs | Database | Purpose |
|---|---|---|---|
| Local laptop (native) | `uvicorn` + `npm run dev` from the project virtualenvs | SQLite file `backend/safespeak_dev.db` | Lightweight development and tests (no Docker needed) |
| Docker / GitHub Codespaces | Full stack: PostgreSQL, migrate job, FastAPI backend, React/nginx frontend, nginx reverse proxy | PostgreSQL (named volume `pgdata`) | Integrated, production-like application and faculty demonstration |
| GitHub Actions | Tests on SQLite and PostgreSQL, ML integrity, frontend build, image builds, Compose smoke test | Ephemeral PostgreSQL | Automated CI verification (`docs/ci-cd.md`) |
| Production (Phase 8) | Same images behind nginx with HTTPS | PostgreSQL (managed or server) | Deployment (`docs/deployment.md`) |

The ML training environment is **not** part of the stack: models are trained offline
from approved, versioned data and the selected artifact is copied into the backend image.
The backend only performs inference and never trains on live complaints.

## Services

```
Browser ─► proxy (nginx :8080) ─┬─ /api/* ─► backend (FastAPI :8000, 1 worker, TAT monitor, ML inference)
                                 └─ /*     ─► frontend (nginx :8080, React build)
migrate (one-shot: alembic upgrade head, owner role) ─► db (PostgreSQL 17, volume pgdata)
backend (least-privilege app role) ─► db
seed (on demand: base data + demo accounts)         ─► db
```

| Service | Image | Port | Healthcheck |
|---|---|---|---|
| `db` | `postgres:17-alpine` | not published (dev override: `127.0.0.1:5433`) | `pg_isready` |
| `migrate` | `safespeak-backend:local` | — | exits 0 after `alembic upgrade head` |
| `backend` | `backend/Dockerfile` | not published (dev override: `127.0.0.1:8000`) | `/api/v1/health` with database `ok` and model loaded |
| `frontend` | `frontend/Dockerfile` | internal 8080 | `GET /` |
| `proxy` | `nginx:1.27-alpine` + `deploy/nginx/default.conf` | **`8080`** | `/healthz` |
| `seed` (profile) | `safespeak-backend:local` | — | run on demand |

Database accounts (created by `deploy/postgres/init/01-roles.sh` on first start):
`safespeak_owner` owns the schema and is used only by `migrate`/`seed`; `safespeak_app` is used
by the API and can read, insert and update rows but cannot delete, truncate or change the schema
(`deploy/postgres/app_role_grants.sql`). Audit and AI-prediction rows are also protected by
database triggers.

## Quick start (local Docker or Codespaces)

```bash
python scripts/generate_env.py        # once: .env with random secrets (git-ignored, never printed)
docker compose up --build             # build images, start db -> migrate -> backend/frontend -> proxy
```
In a second terminal, once the services are healthy (`docker compose ps`):
```bash
docker compose run --rm seed          # once per fresh database: sample departments/rules + demo accounts
```
Open http://localhost:8080 (Codespaces: the forwarded port 8080 link). Demo accounts are
`demo.student@safespeak.test`, `demo.authority@safespeak.test`, `demo.admin@safespeak.test`, … and
all use the `DEMO_PASSWORD` value from `.env`.

Stop: `docker compose down` (keeps data) · reset everything: `docker compose down -v`.

## GitHub Codespaces (recommended on low-memory machines)

1. On GitHub open the repository, switch to the `final-architecture` branch.
2. **Code ▸ Codespaces ▸ ⋯ ▸ New with options** → branch `final-architecture`, machine type
   **4-core / 8 GB** or larger (the dev container requests at least 2 CPU / 8 GB) → *Create codespace*.
3. Wait for the container to build. `.devcontainer/devcontainer.json` installs Docker (docker-in-docker)
   and Node 22, and runs `python scripts/generate_env.py --if-missing` (creates `.env`).
4. In the Codespaces terminal run the demo commands below.

### Demo commands

```bash
docker compose up --build -d                          # start the stack in the background
docker compose ps                                     # all services "healthy", migrate "exited (0)"
docker compose run --rm seed                          # base data + demo accounts
curl -s http://localhost:8080/healthz                 # reverse proxy: ok
curl -s http://localhost:8080/api/v1/health           # backend: database ok, triage_model loaded
docker compose exec db pg_isready                     # PostgreSQL accepting connections
```
Open the frontend: **Ports** tab ▸ port 8080 ▸ *Open in Browser* (or `http://localhost:8080` locally).

Submit a complaint through the API (same as the UI) and read it back from PostgreSQL:
```bash
set -a; . ./.env; set +a                              # load DEMO_PASSWORD etc. into this shell (not printed)
TOKEN=$(curl -s -X POST http://localhost:8080/api/v1/auth/login -H 'Content-Type: application/json' \
  -d "{\"email\":\"demo.student@safespeak.test\",\"password\":\"$DEMO_PASSWORD\"}" | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -s -X POST http://localhost:8080/api/v1/concerns -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"description":"The projector in classroom 052 has not been working for two weeks."}' | python -m json.tool | head -40
```
The response shows `complaint_id`, the AI `category`, `priority`, `category_confidence`,
`priority_confidence`, `threshold`, `model` and whether human review is required.

```bash
docker compose exec db psql -U postgres -d safespeak -c \
  "select complaint_code, category, priority, status, escalation_level from complaints order by id desc limit 5;"
docker compose exec db psql -U postgres -d safespeak -c \
  "select c.complaint_code, p.model_name, p.model_version, p.category, round(p.category_confidence::numeric,2) as conf, p.flagged_for_review
     from ai_predictions p join complaints c on c.id = p.complaint_id order by p.id desc limit 5;"
docker compose exec db psql -U postgres -d safespeak -c \
  "select c.complaint_code, e.action, coalesce(u.name, 'system') as actor, e.created_at
     from complaint_events e join complaints c on c.id = e.complaint_id left join users u on u.id = e.actor_user_id
     order by e.id desc limit 15;"
```

Run the whole end-to-end check (health, login, submission, AI, audit, human review,
automatic escalation after a simulated TAT breach):
```bash
set -a; . ./.env; set +a
python scripts/smoke_test.py http://localhost:8080
```

TAT/automatic escalation in the UI: sign in as `demo.admin@…`, open a complaint, *Simulate TAT breach*
(demo mode only), wait up to `TAT_MONITOR_INTERVAL_SECONDS` (30 s in `.env`): the Escalation card shows
**L1 → L2, Automatic** and the timeline shows "TAT breached" / "Escalated" by *Automatic TAT monitor*.

## Development mode

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```
Publishes PostgreSQL on `127.0.0.1:5433` and the API on `127.0.0.1:8000` (Swagger `/docs`) and
reloads the backend when `backend/app` changes. Run the backend tests against this PostgreSQL:
```bash
set -a; . ./.env; set +a
cd backend
TEST_DATABASE_URL="postgresql+psycopg://$OWNER_DB_USER:$OWNER_DB_PASSWORD@127.0.0.1:5433/${APP_DB_NAME}_test" python -m pytest
```
(`safespeak_test` is a separate, disposable database created by the init script; tests drop and
recreate its schema.)

## Images

| Image | Base | Contents | User |
|---|---|---|---|
| `safespeak-backend` | `python:3.13-slim` (multi-stage) | virtualenv, `backend/app`, Alembic, seeds, `ml/artifacts/<MODEL_VERSION>`, `ml/reports` | `app` (uid 10001, non-root) |
| `safespeak-frontend` | `node:22` build → `nginx-unprivileged:1.27-alpine` | static React build | non-root nginx |

No secrets, `.env` files, databases or credentials are copied into images (`.dockerignore`).
All configuration comes from environment variables (`.env.example` documents each one).

## Troubleshooting

- `docker compose logs backend` / `migrate` / `db` show startup errors (passwords are never logged).
- Changed `.env` passwords after the first start? The roles were created with the old ones:
  `docker compose down -v` (deletes the database) and start again.
- `CONFIDENCE_THRESHOLD` is not passed by default (the threshold recorded with the model is used);
  add it to the `backend` environment in a local override file only if you need to override it.
