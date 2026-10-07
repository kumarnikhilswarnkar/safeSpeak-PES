# Legacy ML files (v1 / v2) — kept for the record, not used

These files are kept unchanged so the Review-II and Friday-upgrade results remain
reproducible and auditable. **The application no longer loads them**: the backend
reads only `ml/artifacts/v3/deployed.json` (see [`ml/README.md`](../README.md)).

| File | What it was | Status |
|---|---|---|
| `ml/train_triage.py` | v1 training script (Review-II, TF-IDF words + LR) | legacy |
| `ml/train_triage_v2.py` | v2 training script (hybrid model, single train/val/test split) | legacy |
| `ml/artifacts/v1/` | v1 model files (`category.joblib`, `priority.joblib`, `metadata.json`) | legacy, not loadable by the v3 backend loader |
| `ml/artifacts/v2/` | v2 model files | legacy, not loadable by the v3 backend loader |
| `ml/reports/evaluation.json`, `ml/reports/evaluation.md` | v2 evaluation report | legacy; replaced by `ml/reports/v3/` |

Why they were replaced (Phase 2):

- v1/v2 selected models on one split; v3 uses 5 × 5 grouped cross-validation on the
  development partition and a 40-group holdout that is never used for any choice.
- v1/v2 used one confidence threshold for both tasks; v3 selects category and
  priority thresholds independently.
- v1/v2 stored no per-file checksums in a deployment manifest; v3 does
  (`deployed.json`), and the backend refuses to load files that do not match.

The files stay in their original locations (moving them would break the commands
recorded in their own reports). Do not delete them.
