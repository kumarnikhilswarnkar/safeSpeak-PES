# Review-II Checklist

> **Historical record of the Review-II state (model v1).** Changes since then are summarised in
> [progress.md](progress.md), [ml_evaluation.md](ml_evaluation.md) and [architecture.md](architecture.md).

Maps the faculty's "Expected demonstration on Monday, 5 October 2026" items to the current repository.
All API paths are under `/api/v1`. Step letters refer to `docs/MONDAY_DEMO.md`.

## The nine demonstration items

| # | Faculty item | Status | Evidence |
|---|---|---|---|
| 1 | Log in with a valid role; reject an invalid role or non-college account | **Implemented** | `POST /auth/login`, `GET /auth/me`; `app/services/auth_service.py`, `app/api/deps.py`. Role comes only from the database account (no role selector; a forged role in the body is rejected with 422, and a token's role claim is ignored). Non-institutional email → 401, inactive account → 403. Tests: `test_auth_api.py`, `test_authorization.py`. Demo step A. |
| 2 | Submit one grievance and show its stored database record | **Implemented** | `POST /concerns`, `GET /concerns/{id}`; `complaint_service.submit`; tables `complaints`, `ai_predictions`, `complaint_events`; ID `SSP-YYYY-NNNNNN` from `id_counters`. Tests: `test_concern_submission.py`. Demo steps B–C. |
| 3 | Display AI-suggested category, priority and confidence | **Implemented** | `triage_service.SklearnTriageModel` (TF-IDF + Logistic Regression, `ml/artifacts/v1`); response field `ai`; "AI recommendation" card. Stored separately from the human decision and never modified. Tests: `test_triage_model.py`. Demo steps D–F. |
| 4 | Show how a low-confidence prediction is flagged for human review | **Implemented** | `triage_service.review_reasons`; threshold 0.24 from validation data (`CONFIDENCE_THRESHOLD` overrides it); High/Critical also require review; `GET /concerns/pending-triage`; review TAT assigned. Tests: `test_concern_submission.py`. Demo step G. |
| 5 | Route through a configurable EscalationRule; assign a deadline from TATRule | **Implemented** | Tables `escalation_rules`, `tat_rules` (sample data from `seed/prototype_rules.py`); `routing_service.route_from_level`, `tat_service.resolve_rule`. Missing rule → explicit 503 (no hidden default). Tests: `test_concern_submission.py`. Demo step H. |
| 6 | Reviewer accept / override / reroute, with the audit event | **Implemented** | `POST /concerns/{id}/review`; only the assigned authority may act; reviewer identity from the JWT; unknown fields (e.g. `reviewer_id`) rejected; `complaint_events` stores actor, role, previous and new values. Tests: `test_concern_review.py`. Demo steps I–K. |
| 7 | Simulate a TAT breach and demonstrate reassignment to the next level | **Implemented, with a documented limitation** | `POST /concerns/{id}/simulate_breach` (admin, only when `DEMO_MODE=true`) and `POST /concerns/escalate-overdue` (admin): reassigns to the next level, sets a new deadline, audits, never duplicates, stops once at the top of the chain. **There is no automatic scheduler yet**: an administrator triggers the escalation job. The job is a plain service function (`complaint_service.escalate_overdue`) that a scheduler can call later. Tests: `test_concern_escalation.py`. Demo steps L–O. |
| 8 | Show the pseudocode beside the live flow, mapped to modules | **Implemented** | `docs/implementation_flow.md` (pseudocode and a step → file / endpoint / table / page mapping). |
| 9 | Repository history, tests/API evidence, exact module-wise completion | **Partially implemented** | Tests: 198 backend tests passing (`.venv\Scripts\python -m pytest`); API docs at `/docs` (14 operations); scripted run `backend/scripts/demo_flow.py`; read-only database evidence `backend/scripts/list_complaints.py` and `show_complaint.py`. Completion: `docs/progress.md` (87.8% of the Review-II workflow scope; 63.9% of the whole planned project, equal weights). **Remaining:** the Phase 2 and workflow work is not yet committed, so the repository history currently shows only the project foundation. |

## Other gaps from the feedback

| Feedback point | Status | Evidence / remaining |
|---|---|---|
| 1. Progress inconsistency (20% vs 49%) | Addressed | One module-wise calculation in `docs/progress.md`; state which figure is meant (workflow scope 87.8%, whole project 63.9%). |
| 2. Main workflow not integrated | Addressed | One flow from login to escalation (items 1–7). |
| 3. Hierarchy not frozen | Addressed for the prototype | Configurable sample chain in `escalation_rules`: L1 Department Authority → L3 Dean → L4 Director (safety: L1 → L4). Labelled as sample, not the real PES hierarchy. |
| 4. AI confidence handling incomplete | Addressed | Threshold, low-confidence behaviour, review queue and review TAT (item 4). |
| 5. Evaluation needs balance | Partially addressed | Confusion matrices, macro-F1, per-class F1 and false-positive/false-negative counts are recorded in `ml/artifacts/v1/metadata.json` and summarised below. Not yet presented as figures in the report or slides. |
| 6. Dataset evidence | Addressed in documentation | See "Dataset source" below. |
| 7. PPT coverage | Partially addressed | Updated report (template sections, 13-paper literature survey, FR/NFR, design, database, implementation flow, testing, references) and a 14-slide deck, kept outside the code (`deliverables/`, not committed). Remaining: insert screenshots in the report. |
| 8. Report filename SRN | Addressed | The new report PDF and deck carry PES1PG25CA142; the earlier file with the incorrect SRN is not resubmitted. |

## Dataset source

- **600 records**: `ml/data/SafeSpeak_dataset_split_600.csv`.
- **Entirely synthetic.** 200 AI-generated seed texts (`ai_generated_batch1_v2`: 100, `ai_generated_batch2`: 100)
  plus 400 AI paraphrases of those seeds (`ai_paraphrase_of_batch1`: 200, `ai_paraphrase_of_batch2`: 200).
  No real complaints are included.
- **Labels**: 8 categories (72–78 each); priorities Low 159, Medium 210, High 147, Critical 84.
- **Leakage control**: each seed and its paraphrases share a `group_id` (200 groups of 3), and whole groups are
  assigned to one split: 420 train / 90 validation / 90 test. `ml/train_triage.py` checks that no group crosses splits.
- **Annotation study**: two annotators labelled a 200-record subset. The reported agreement (Cohen's κ 0.75
  category, weighted κ 0.81 priority) uses annotator B's revised sheet; the first round was much lower. The
  revision process should be described in the report.

## Model and method

- **Model**: TF-IDF (word 1–2 grams) + Logistic Regression (class-balanced), one model for category and one for
  priority, trained on the train split only (`ml/train_triage.py`, version v1, scikit-learn 1.9.1). Model files are
  checksum-verified when loaded.
- **Confidence**: highest class probability per task; overall confidence = the lower of the two.
- **Threshold 0.24**: chosen on the validation split as the lowest value at which the complaints at or above it have
  both labels correct at least 70% of the time (validation: 17 of 90 covered, 70.6%). On the test split the same
  threshold covers 18 of 90 complaints at 61.1%. Everything below it, and every High/Critical prediction, goes to a human.
- **Test results (90 records, reported once)**:

  | Task | Accuracy | Macro-F1 | Other |
  |---|---|---|---|
  | Category | 51.1% | 47.4% | Academic / Department F1 = 0 |
  | Priority | 53.3% | 55.6% | Critical recall 91.7% (11 of 12); High+Critical recall 61.9% (16 serious complaints predicted Low/Medium; 9 Low/Medium predicted High/Critical) |

  Priority confusion matrix (rows = true, columns = predicted; Low, Medium, High, Critical):

  ```
  Low       15   5   1   0
  Medium     6  13   7   1
  High       3  12   9   6
  Critical   1   0   0  11
  ```

## Limitations to state

- Category accuracy (~51%) is low and below the keyword baseline reported earlier (58.9%); the rule baseline and
  Linear SVM are not yet part of this repository's training pipeline, so that comparison is not reproduced here.
- The Critical-recall figure rests on 12 test records from 4 paraphrase groups; it is not a stable estimate.
- Validation and test splits have 90 records each and are not stratified (validation has only 6 Critical records).
- The data is synthetic, so the results say nothing yet about real campus complaints.
- With the 0.24 threshold, at least 80% of test complaints fall below it, and High/Critical predictions are
  reviewed regardless, so most complaints go to human review. That is safe but means the AI saves little
  reviewer effort at this model quality.
- Escalation is triggered manually (no scheduler), and TAT values and the hierarchy are sample configuration.
