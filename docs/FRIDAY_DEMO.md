# Final presentation demo (Friday)

One live story: **AI triage → confidence check → human correction → automatic routing → automatic TAT
monitoring → automatic escalation → audit trail**, then the evaluation page. About 12 minutes.

## Before the demo

1. Close any other SafeSpeak servers (ports 8000 and 5173). Use the project's virtual environment, not
   the system Python (system Python has an older scikit-learn that cannot run the model).
2. `backend/.env` must contain `DEMO_MODE=true`. For a quick escalation on stage set
   `TAT_MONITOR_INTERVAL_SECONDS=20` (default 60). Do **not** set `CONFIDENCE_THRESHOLD`, so the
   cross-validated threshold 0.65 is used.
3. Backend (PowerShell, from `backend/`):

   ```
   .venv\Scripts\alembic upgrade head
   .venv\Scripts\python -m seed.demo_users
   .venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
   ```

   `seed.demo_users` is safe to repeat: it adds only what is missing (this release adds the Facilities
   Office authority and the Infrastructure routing chain). Use one worker process (the default).
4. Frontend (from `frontend/`): `npm install` (first time, for the new UI libraries), then `npm run dev`
   and open http://localhost:5173.
5. Passwords: `backend/demo_credentials.local.txt` (local only; never show it on screen).
6. Optional clean start: stop the backend, delete `backend/safespeak_dev.db`, then repeat step 3.

## Accounts (prototype / demo accounts)

| Role | Email | Used for |
|---|---|---|
| Student | `demo.student@safespeak.test` | submit, track |
| Department Authority L1 (MCA) | `demo.authority@safespeak.test` | human review |
| Facilities Office Authority L1 | `demo.facilities@safespeak.test` | receives Infrastructure complaints |
| Higher Authority L3 (sample "Dean") | `demo.higher@safespeak.test` | receives escalations |
| Director L4 | `demo.director@safespeak.test` | top of the chain |
| Admin | `demo.admin@safespeak.test` | dashboards, automation, breach simulation |
| Viewer | `demo.viewer@safespeak.test` | read-only oversight |

## Demo sequence

| # | Who / where | Do | Show and say |
|---|---|---|---|
| 1 | Login page | Point at the left panel and the "Prototype / demo accounts" note | "Accounts are seeded demo accounts; the role comes from the server account, never from the user. SSO is future work." |
| 2 | Student → New complaint | Submit **"Fee receipt for the second semester has not been issued even after payment two weeks ago."** | AI analysis card: Administrative / Fees ~100%, Medium ~86%, threshold 65% → **Continue automatically**. "Why this category" evidence, keyword baseline agrees. Right panel: assigned to L1 MCA authority, 72 h TAT, routing reason. |
| 3 | Student → New complaint | Submit **"There is some issue, please check."** | Category "Other" 49% < 65% → **Human review required**. "Nothing is final until a person decides." |
| 4 | Student → Dashboard | — | Stat cards, recent complaints with stage and TAT; bell shows the in-app notification. |
| 5 | Authority (MCA L1) → Dashboard | — | "Pending human reviews 1", "Low-confidence 1", confidence histogram, human review rate. Click the pending card → Review queue. |
| 6 | Authority → open the vague complaint | Override → category **Infrastructure and facilities**, priority Medium, comment "Student confirmed: classroom fan in room 204 is broken." → Review and confirm → Confirm | Confirmation dialog. After saving: "AI recommendation vs final decision" table (AI: Other → Final: Infrastructure, *changed by human*), reviewer, time, comment. **Automatic routing**: it moved to the **Facilities Office** (category-specific chain), new 48 h TAT. Audit trail shows both entries. |
| 7 | Admin → same complaint | "Simulate TAT breach" (demo only) | Toast: "the automatic monitor will escalate it within 20 s". **Do not press anything.** Talk about the monitor while waiting. |
| 8 | Same page (refreshes itself) | wait ≤ 20 s | Escalation card: **L1 → L2, Automatic**, from Facilities → Dean, missed deadline, new deadline. Timeline: "TAT breached" and "Escalated" by **Automatic TAT monitor** (system actor). |
| 9 | Admin → TAT automation | — | Monitor *Running*, interval, last automatic check, next check countdown, recent checks (the escalation appears with its ID). Chains and TAT rules are configuration (database rows). |
| 10 | Admin → Dashboard | — | Totals, overdue/escalated, AI vs human decisions, confidence distribution, escalations (automatic vs manual). Optional: breach twice more → "Chain exhausted — administrator attention" banner. |
| 11 | Any → AI evaluation | Switch Category/Priority tabs | Keyword baseline vs ML table, CV vs test, per-class F1, confusion matrix, threshold curve and trade-off table, calibration, robustness, probes, findings. Synthetic-data banner. |
| 12 | Backup | Swagger `http://127.0.0.1:8000/docs`, `pytest`, `scripts/demo_flow.py` | 215 backend tests. |

## What to say for each feature

- **Local AI categorisation.** "Category and priority come from a scikit-learn model that runs inside our
  backend. No OpenAI, Gemini or other external API is called. It is a hybrid: TF-IDF word and character
  n-grams plus counts from a keyword lexicon, with Logistic Regression."
- **ML vs keyword baseline.** "You were right: the Review-II model was weaker than the keyword baseline in
  cross-validation, 50% vs 62% macro-F1. We built the baseline into the pipeline, compared six models with
  5-fold grouped cross-validation, and kept one untouched test set for all of them. The selected hybrid
  scores 65% CV macro-F1 and beats keywords on the test set by about 14 points accuracy. Its explanations
  show the gain comes mostly from combining the lexicon with learned weights. On the test set a pure SVM
  scored slightly higher, but we did not switch, because choosing by test score is test-set tuning."
- **Confidence and calibration.** "Confidences are temperature-scaled. For category, calibration improved
  on the test set; for priority it did not, and we report that. The threshold 0.65 is the lowest value
  where both decisions are right at least 75% of the time out of fold. We show 0.20 to 0.65 in a
  trade-off table. We do not claim it is optimal."
- **Human in the loop.** "Below threshold, or any High/Critical prediction, goes to the L1 reviewer, who can
  accept, override or reroute. The AI output is stored unchanged; the human decision is stored separately
  with reviewer, time and comment. On the test set about 4 out of 5 complaints would need a person. That is
  the intended behaviour at this accuracy."
- **Automatic routing.** "Routing is data-driven: each category has a configured escalation chain. When the
  reviewer corrected 'Other' to 'Infrastructure', the system re-routed it to the Facilities Office by
  itself and recorded the reason."
- **Automatic TAT monitoring and escalation.** "A background job inside the API checks every N seconds. When
  a deadline passes it records the breach, moves the complaint up one level, assigns the new authority,
  sets a new deadline and writes the audit trail. A lock and the new deadline prevent duplicate
  escalation. At the top of the chain it stops, keeps the complaint with the highest authority and flags
  it for the administrator. No Redis or Celery: one lightweight loop is enough for one server process."
- **Audit trail.** "Append-only: every action with actor (or 'automatic TAT monitor'), time and old → new
  values. Neither the AI prediction nor the events can be edited."
- **Synthetic data.** "All training and test data is synthetic and controlled; we say so on the evaluation
  page. Real-world performance needs real, consented complaints."
- **Reviewer unavailable.** "Routing only picks active accounts. If no active authority exists at a level,
  that level is skipped and the skip is audited. A separate 'on leave' availability status is not
  implemented."

## Known limitations (say them if asked)

- Synthetic dataset; modest accuracy (category ~66%, priority ~50% on 90 test records).
- Priority calibration did not improve on the test split.
- The monitor runs inside the API process: run a single worker; a multi-server deployment would need a
  dedicated scheduler or database locking.
- Reviewer availability = active/inactive accounts only (no leave calendar or workload balancing).
- Notifications are in-app only (no email/SMS). Read state is kept in the browser.
- No admin screens to edit rules (read-only view only); no institutional SSO; SQLite only.
