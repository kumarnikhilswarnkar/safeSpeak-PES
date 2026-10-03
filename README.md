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
docs/       Architecture, progress and (later) demo documentation
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

Apply database migrations and start the API:

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

The API runs at http://127.0.0.1:8000. Interactive docs are at http://127.0.0.1:8000/docs and
the health check is at http://127.0.0.1:8000/api/v1/health.

Run the tests:

```bash
pytest
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
