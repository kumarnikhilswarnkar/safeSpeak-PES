# SafeSpeak PES

Human-in-the-Loop Campus Concern Triage and Prioritization: an MCA capstone project.

Students and staff submit campus concerns. An AI model suggests a category, a priority and a
confidence score; an authorized human reviewer always makes the final decision. Every complaint
gets a turnaround time (TAT) and escalates to the next configured authority if that deadline is missed.

Overdue complaints are detected and escalated by an automatic TAT monitor running inside the API, and
every action is written to an append-only audit trail.

See [docs/architecture.md](docs/architecture.md) for the design, [docs/progress.md](docs/progress.md)
for what is implemented, [docs/ml_evaluation.md](docs/ml_evaluation.md) for the model evaluation and
[docs/FRIDAY_DEMO.md](docs/FRIDAY_DEMO.md) for the final demo.

## Quick start (one command, Windows)

After the one-time setup (backend virtual environment and `npm install`, see below), start the whole
application from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\start-safespeak.ps1
```

or double-click `start-safespeak.cmd`. It checks the database schema (backing it up first if a
migration is pending; it never resets data), starts the backend on port 8001, waits until it is
healthy, starts the frontend and opens http://localhost:5173. **Ctrl+C** in that window stops both.
For the containerised version (one URL behind nginx, PostgreSQL) see [docs/docker.md](docs/docker.md).

## Where SafeSpeak runs

| Environment | How | Database |
|---|---|---|
| Local laptop (native) | backend virtualenv + `npm run dev` (below) | SQLite (lightweight development and tests) |
| Docker / GitHub Codespaces | `docker compose up --build`: PostgreSQL, migrations, FastAPI, React/nginx, nginx reverse proxy | PostgreSQL ([docs/docker.md](docs/docker.md)) |
| GitHub Actions | automated tests, ML integrity, frontend build, Docker builds, Compose smoke test | ephemeral PostgreSQL ([docs/ci-cd.md](docs/ci-cd.md)) |
| Production | same images, HTTPS, proper secrets ([docs/deployment.md](docs/deployment.md)) | PostgreSQL |

Security status: [docs/security.md](docs/security.md).

## Project structure

```
backend/    FastAPI API, SQLAlchemy models, Alembic migrations, pytest tests
frontend/   React + Vite single-page app
ml/         Research dataset, training script and the trained triage model
docs/       Architecture, security, Docker, CI/CD, deployment, progress and demo guides
deploy/     nginx reverse-proxy and PostgreSQL role configuration for Docker
scripts/    .env generator, Docker smoke test, SQLite backup
```

## Requirements

- Python 3.12 or newer
- Node.js 20 or newer

## Backend setup

From the `backend` folder:

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash; PowerShell: .venv\Scripts\Activate.ps1; macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

Then edit `.env`:

- `JWT_SECRET_KEY`: required, at least 32 characters. Generate one with
  `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
- `ALLOWED_EMAIL_DOMAINS`: the institutional email domain(s) allowed to sign in.

Apply database migrations, create the demo accounts (development only) and start the API:

```bash
alembic upgrade head
python -m seed.demo_users
uvicorn app.main:app --reload
```

The seed creates sample departments, demo accounts for every role, and the sample TAT and
escalation rules. Their passwords are written to
`backend/demo_credentials.local.txt`, which is git-ignored. Run `python -m seed.demo_users --reset-passwords`
to issue new ones. There is no public sign-up.

The API runs at http://127.0.0.1:8000. Interactive docs are at http://127.0.0.1:8000/docs and
the health check is at http://127.0.0.1:8000/api/v1/health.

Run the tests:

```bash
pytest
```

Run the end-to-end demo against the running API (needs `DEMO_MODE=true` in `backend/.env`):

```bash
python scripts/demo_flow.py
```

## Demo and evidence commands (Windows)

From the `backend` folder, without activating the virtual environment:

| Purpose | Command |
|---|---|
| Start the API on port 8000 (also starts the automatic TAT monitor) | `.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000` |
| Run all tests | `.venv\Scripts\python -m pytest` |
| List every stored complaint with the total count (read-only) | `.venv\Scripts\python scripts\list_complaints.py` |
| Show one complaint's database rows (read-only) | `.venv\Scripts\python scripts\show_complaint.py SSP-2026-000001` |
| Swagger / OpenAPI | http://127.0.0.1:8000/docs |

The two scripts open `backend/safespeak_dev.db` read-only and print no passwords, hashes or tokens.
Always start the API with the project's `.venv` Python: the system Python may have an older
scikit-learn that cannot run the model (the API then refuses to load it and submissions return 503).
The final demo walkthrough is in [docs/FRIDAY_DEMO.md](docs/FRIDAY_DEMO.md).

## SafeSpeak Assistant

Every signed-in page has an **Ask SafeSpeak** button (and the `/assistant` page): ask for a complaint's status,
deadline (TAT), current authority, escalation or timeline in plain language. Answers come only from the
database and only for complaints you may open; no external AI service is used. See
[docs/assistant.md](docs/assistant.md).

## AI triage model

Two local scikit-learn models (category and priority) run inside the backend; no external AI service
is used. The v3 pipeline (`ml/scripts/run_experiments.py`, see [ml/README.md](ml/README.md)) compares
10 candidates per task with 5 × 5 grouped cross-validation, applies a pre-declared selection rule,
calibrates confidences, chooses a separate review threshold per task, reports a 120-record holdout
once, and writes `ml/artifacts/v3/` (with `deployed.json`, the only file the backend reads) and
`ml/reports/v3/` (shown on the AI evaluation page). Results: [docs/ml_evaluation.md](docs/ml_evaluation.md).

```bash
ml/.venv-ml/Scripts/python ml/scripts/run_experiments.py
backend/.venv/Scripts/python ml/scripts/predict_demo.py
```

The dataset is synthetic/controlled (AI-generated complaints and paraphrases), not real student data.
The v1/v2 scripts and artifacts are kept as legacy ([ml/legacy/README.md](ml/legacy/README.md)).

## Frontend setup

From the `frontend` folder:

```bash
npm install
npm run dev
```

Open http://localhost:5173. The dev server forwards `/api` requests to the backend at
`SAFESPEAK_API_URL`, read from the shell or from `frontend/.env.local` (git-ignored), e.g.
`SAFESPEAK_API_URL=http://127.0.0.1:8000`; if it is not set, `http://127.0.0.1:8001` is used.

## Configuration and secrets

Configuration lives in `backend/.env`, which is never committed. `backend/.env.example` lists every
setting. The private annotation answer key and any other secrets must never be added to the repository.
