# SafeSpeak PES

Human-in-the-Loop Campus Concern Triage and Prioritization: an MCA capstone project.

Students and staff submit campus concerns. An AI model suggests a category, a priority and a
confidence score; an authorized human reviewer always makes the final decision. Every complaint
gets a turnaround time (TAT) and escalates to the next configured authority if that deadline is missed.

See [docs/architecture.md](docs/architecture.md) for the design and [docs/progress.md](docs/progress.md)
for what is implemented so far.

## Project structure

```
backend/    FastAPI API, SQLAlchemy models, Alembic migrations, pytest tests
frontend/   React + Vite single-page app
ml/         Research dataset, training script and the trained triage model
docs/       Architecture, progress, implementation flow, Review-II checklist and demo guide
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
| Start the API on port 8000 | `.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000` |
| Run all tests | `.venv\Scripts\python -m pytest` |
| List every stored complaint with the total count (read-only) | `.venv\Scripts\python scripts\list_complaints.py` |
| Show one complaint's database rows (read-only) | `.venv\Scripts\python scripts\show_complaint.py SSP-2026-000001` |
| Swagger / OpenAPI | http://127.0.0.1:8000/docs |

The two scripts open `backend/safespeak_dev.db` read-only and print no passwords, hashes or tokens.
The full demo walkthrough is in [docs/MONDAY_DEMO.md](docs/MONDAY_DEMO.md).

## AI triage model

`ml/train_triage.py` trains the category and priority models from `ml/data/SafeSpeak_dataset_split_600.csv`
and writes `ml/artifacts/v1/`. From the repository root:

```bash
backend/.venv/Scripts/python ml/train_triage.py
```

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
