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

## AI triage model

The categorisation model is a local scikit-learn model that runs inside the backend; no external AI
service is used. `ml/train_triage_v2.py` compares a keyword baseline with several ML models
(5-fold grouped cross-validation, one held-out test set), calibrates the confidences, selects the
review threshold and writes `ml/artifacts/v2/` plus the report `ml/reports/evaluation.json`
(shown on the AI evaluation page). From the repository root:

```bash
backend/.venv/Scripts/python ml/train_triage_v2.py
```

The dataset is synthetic/controlled (AI-generated complaints and paraphrases), not real student data.
`ml/train_triage.py` reproduces the earlier v1 model (Review-II).

## Frontend setup

From the `frontend` folder:

```bash
npm install
npm run dev
```

Open http://localhost:5173. The dev server forwards `/api` requests to the backend on port 8000
(set `SAFESPEAK_API_URL` to use a different backend address).

## Configuration and secrets

Configuration lives in `backend/.env`, which is never committed. `backend/.env.example` lists every
setting. The private annotation answer key and any other secrets must never be added to the repository.
