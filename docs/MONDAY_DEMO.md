# Monday Review-II Demo (5 October 2026)

One complete grievance workflow, shown live in the browser, with the API docs and tests as backup.

## Before the demo

1. Close the old `PROJECT MCA\safespeak-app` servers if they are running (they use the same ports 8000 and 5173).
2. Check `backend/.env` contains `ALLOWED_EMAIL_DOMAINS=safespeak.test` and `DEMO_MODE=true`, and that
   `CONFIDENCE_THRESHOLD` is **not** set (the validation-selected threshold 0.24 is then used).
3. Start the backend (terminal 1, from `backend/`):

   ```
   .venv/Scripts/alembic upgrade head
   .venv/Scripts/python -m seed.demo_users
   .venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
   ```

   The first two commands are safe to repeat: they skip anything that already exists.

4. Start the frontend (terminal 2, from `frontend/`):

   ```
   npm run dev
   ```

5. Open `backend/demo_credentials.local.txt` (git-ignored, local only) for the demo passwords. Do not show
   this file on screen.
6. Optional check: http://127.0.0.1:8000/api/v1/health should show `"database": "ok"`,
   `"triage_model": "tfidf-logreg:v1"` and `"demo_mode": true`.

## Accounts

| Role | Email | Used in steps |
|---|---|---|
| Student | `demo.student@safespeak.test` | A–H |
| Department Authority (L1, MCA) | `demo.authority@safespeak.test` | I–K |
| Higher Authority (L3, sample "Dean") | `demo.higher@safespeak.test` | O (optional) |
| Admin | `demo.admin@safespeak.test` | L–O |

Passwords: `backend/demo_credentials.local.txt`. To set one memorable demo password for every account
before the demo (from `backend/`): `DEMO_PASSWORD='...' .venv/Scripts/python -m seed.demo_users --reset-passwords`.

## Complaint texts

| | Text | Expected AI output (model v1) |
|---|---|---|
| **Complaint 1** (normal path) | Fee receipt for the second semester has not been issued even after payment two weeks ago. | Administrative / Fees (0.294), Medium (0.412) → above 0.24, no review |
| **Complaint 2** (review path) | there is some issue, please check | Administrative / Fees (0.192), Medium (0.466) → below 0.24, human review |

## Steps

| Step | URL / page | Account | Action | Expected result |
|---|---|---|---|---|
| **A. Student login** | http://localhost:5173/login | Student | Enter email and password, Sign in | Lands on `/student`; home shows role "Student" and its two permissions (from the server). Optional: `someone@gmail.com` is refused with "Use your institutional email address". |
| **B. Complaint submission** | http://localhost:5173/concerns/new ("Submit complaint") | Student | Paste **Complaint 1**, Submit | Redirects to the complaint page with "Complaint submitted. Keep your complaint ID…" |
| **C. SSP complaint ID** | Complaint page `/concerns/SSP-2026-…` | Student | Read the heading | ID in the form `SSP-2026-000001` |
| **D. AI category** | Same page, "AI recommendation" card | Student | — | Category: Administrative / Fees, confidence 29% |
| **E. AI priority** | Same card | Student | — | Priority: Medium, confidence 41% |
| **F. AI confidence** | Same card | Student | — | Meters with the threshold marker; "Review threshold 0.24 (selected on validation data). No human review was required." Status "Assigned", assigned to Demo Department Authority (L1). |
| **G. Low-confidence human review** | "Submit complaint" again | Student | Submit **Complaint 2** | Status "Pending human review"; "Human review required: Low category confidence"; category confidence 19% shown below threshold |
| **H. TAT deadline** | "Assignment and TAT" card on each complaint | Student | — | Complaint 1: Resolution stage, 72 hours, deadline and time left. Complaint 2: Human review stage, 12 hours. Both "On track". |
| **I. Authority login** | Sign out → http://localhost:5173/login | Department Authority | Sign in, open "Review queue" (`/review`) | "Needs human review" tab lists Complaint 2; "All assigned to me" lists both |
| **J. Accept** | Complaint 1 page (`/concerns/SSP-2026-000001`) | Department Authority | "Your review" → Accept AI recommendation → Confirm | Decision "Reviewer accepted AI recommendation" |
| **J. Override** | Complaint 2 page | Department Authority | Override → Category "Infrastructure and facilities", Priority "Medium" → Confirm | Status "Assigned"; category changed; AI card still shows the original AI values; TAT becomes Resolution 48 hours (sample category rule) |
| **J. Reroute** | Complaint 2 page | Department Authority | Reroute → choose "Demo CSE Department Authority (L1)" → Confirm | Assigned to the CSE authority; department CSE; complaint leaves this authority's queue |
| **K. Audit timeline** | "Timeline" section of either complaint | Any viewer of the complaint | — | Entries for submitted, AI triage, (sent to human review), assigned, accepted / overridden (with old → new values) / rerouted, each with the acting person and time |
| **L. Admin login** | Sign out → http://localhost:5173/login | Admin | Sign in, open "All complaints" (`/concerns`) | Read-only list of both complaints |
| **M. Simulate TAT breach** | Complaint 1 page | Admin | "TAT breach demonstration" → Simulate TAT breach | Message "Deadline moved into the past"; TAT shows "Overdue"; timeline gets "TAT breach simulated (demo)" by Demo Admin |
| **N. Run escalation check** | Same panel | Admin | Run escalation check | "Escalation check processed N overdue complaint(s)." N is 1 on a fresh database; it can be higher if earlier test complaints have also passed their deadlines, because the check handles every overdue complaint. Clicking again processes 0 (no duplicate escalation). |
| **O. New authority and deadline** | Same page | Admin (optional: sign in as Higher Authority and open "Review queue") | — | Assigned to Demo Higher Authority (L3); "Escalated · L2"; Resolution 48 hours with a new deadline; timeline shows "TAT breached" and "Escalated" (L1 → L2, old → new deadline) |

## Backup evidence

All commands run from `backend/`.

- Scripted run of the same flow (with the API running): `.venv/Scripts/python scripts/demo_flow.py`
- Every complaint stored in the database, with the total count (read-only):
  `.venv/Scripts/python scripts/list_complaints.py`
- One complaint's database rows: complaint, AI prediction and audit events (read-only):
  `.venv/Scripts/python scripts/show_complaint.py SSP-2026-000001`
- Interactive API documentation: http://127.0.0.1:8000/docs; health: http://127.0.0.1:8000/api/v1/health
- Tests: `.venv/Scripts/python -m pytest` (198 tests, all passing on 5 October 2026)
- Repository history: `git log --oneline`
- Pseudocode → module mapping: `docs/implementation_flow.md`
- Module-wise completion: `docs/progress.md`

## What to say honestly

- Escalation is triggered by an administrator (`POST /api/v1/concerns/escalate-overdue`); there is no
  automatic background scheduler yet. The breach simulation only exists when `DEMO_MODE=true`.
- The TAT values and the authority chain are sample configuration, not the real PES hierarchy.
- The dataset is fully synthetic and the model is modest (see `docs/REVIEW_II_CHECKLIST.md`).

## Resetting for a clean run

Complaint numbers continue across runs: the steps above use `SSP-2026-000001` and `…000002`, but on a
database that already holds complaints the new ones get the next numbers (for example `…000005`). To start again from `SSP-2026-000001`, stop the backend, delete
`backend/safespeak_dev.db`, then run `alembic upgrade head` and `python -m seed.demo_users`. This creates
new demo passwords in `backend/demo_credentials.local.txt`.
