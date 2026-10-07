# SafeSpeak ML pipeline (v3)

Local, inspectable and reproducible training of the two triage models the backend uses:
**category** (8 classes) and **priority** (Low / Medium / High / Critical). No external
API is called at prediction time, and the model never trains on live complaints; it
only learns from the checksummed dataset in `ml/data/`.

Results: [`reports/v3/model_comparison.md`](reports/v3/model_comparison.md) (generated;
every number in it is computed by the scripts below). Old v1/v2 files:
[`legacy/README.md`](legacy/README.md).

## Layout

```
ml/
  data/SafeSpeak_dataset_split_600.csv   dataset (SHA-256 pinned in safespeak_ml/config.py; see DATASET.md)
  data/splits/v3_split.csv               fixed development/holdout split (40 groups held out)
  encoders.lock.json                     pinned MiniLM revision + SHA-256 of every encoder file
  requirements-experiments.txt           exact package versions for the experiments
  safespeak_ml/
    config.py                            every setting: seeds, folds, grids, hyperparameters, paths
    data.py                              loading, checksum, split, grouped CV folds (leakage asserts)
    features/                            TF-IDF words/chars, frozen keyword counts, MiniLM embeddings
    models/                              candidates 0-9, one file each; registry.py lists them
    evaluation/                          metrics, cross-validation, calibration, thresholds, selection
    training/                            per-task experiment and artifact export
  scripts/
    download_encoder.py                  fetch + verify the encoder (once)
    make_split.py [--check]              create (once) or verify the holdout split
    setfit_pilot.py                      SetFit feasibility gate (decides whether candidate 9 runs)
    run_experiments.py                   the whole experiment -> artifacts/v3 + reports/v3
    predict_demo.py                      predict through the BACKEND loader (what the API does)
  artifacts/v3/                          deployed.json + every trained candidate per task
  reports/v3/                            all reports listed below
```

## Reproduce

```bash
python -m venv ml/.venv-ml
ml/.venv-ml/Scripts/python -m pip install -r ml/requirements-experiments.txt
ml/.venv-ml/Scripts/python ml/scripts/download_encoder.py
ml/.venv-ml/Scripts/python ml/scripts/make_split.py --check
ml/.venv-ml/Scripts/python ml/scripts/setfit_pilot.py
ml/.venv-ml/Scripts/python ml/scripts/run_experiments.py
backend/.venv/Scripts/python ml/scripts/predict_demo.py
```

(On Linux/macOS use `bin/python` instead of `Scripts/python`.) With the same package
versions, seeds and files, the reports and model files are reproduced; the
`reproducibility.json` report records versions, seeds, checksums and the git commit.

## Protocol (fixed before any result was seen)

1. **Data.** 600 synthetic records = 200 paraphrase groups × 3. The SHA-256 is checked on
   every load. A group (one seed complaint and its paraphrases) is never split.
2. **Holdout.** 40 whole groups (120 records), stratified by category, seed 42. It is
   used once, after every decision, for reporting only: never for choosing a model,
   features, calibration or threshold.
3. **Cross-validation** on the 480 development records: `StratifiedGroupKFold`,
   5 folds × 5 repeats (seeds 42–46) = 25 fits per candidate per task. The training fold
   never contains a group from the validation fold (asserted in code and in tests).
4. **Candidates** (same folds for all):

   | # | Candidate | Notes |
   |---|---|---|
   | 0 | Majority class | floor |
   | 1 | Frozen keyword rules | backend lexicon, SHA-256 pinned, not tuned |
   | 2 | TF-IDF words (1–2) + LR | |
   | 3 | TF-IDF words (1–2) + linear SVM | |
   | 4 | Word n-grams (1–3) + LR | |
   | 5 | Words + characters (2–5) + LR | |
   | 6 | Words + characters + linear SVM | |
   | 7 | Hybrid: words + characters + keyword counts + LR | |
   | 8 | MiniLM sentence embeddings + LR | frozen encoder, pinned revision |
   | 9 | SetFit (MiniLM fine-tuned) | only if the feasibility gate passes |

5. **Metrics.** Accuracy, macro precision/recall/F1, weighted F1, per-class metrics,
   confusion matrices; CV mean ± SD over the 25 folds. Priority also reports Critical
   recall and High-or-Critical recall.
6. **Selection rule** (CV only; candidates 2–9 are selectable, 0–1 are baselines):
   highest mean CV macro-F1; candidates within 1 SD of the best are tied → among them
   keep the most stable (lowest SD; SDs within 0.005 of the lowest count as equal) →
   then the simpler model. The selected model is compared with the frozen keyword
   baseline.
7. **Calibration**, per task, on cross-fitted out-of-fold scores: raw softmax,
   temperature scaling, per-class sigmoid. The method with the lowest log-loss is used;
   raw is kept if nothing improves it. Holdout calibration is reported, not used.
8. **Thresholds**, per task, independently, on the calibrated out-of-fold confidences
   of the selected model: the lowest threshold `t` (grid 0.05–0.95) at which complaints
   with confidence ≥ `t` are correct at least 80% of the time *and* at least 10% of
   complaints are above `t`. If no `t` meets this, `t = 1.0` (everything goes to a
   human). 80% is the target accuracy of automatic decisions, **not** the threshold.
9. **Deployment constraint (disclosed; added 2026-10-07 after the first full run, by the
   project owner's decision).** The backend must run without PyTorch, so only linear-text
   candidates (2–7, `config.DEPLOYABLE`) can be deployed. The first run's rule picked
   MiniLM + LR (#8) for category, which would add about +530 MB to the backend image,
   +370 MB RAM and +30 s startup. The same rule is applied to the deployable pool; the
   unconstrained winner is computed and reported every run (`selection.json` →
   `unconstrained`, `model_comparison.md`).
10. **Deployment.** `run_experiments.py` refits every candidate on all 480 development
   records, saves them, and writes `artifacts/v3/deployed.json` naming the selected
   model per task with the SHA-256 of every file and probe predictions. The backend
   reads only this file, verifies every checksum, and refuses to start the model
   otherwise.

## The backend at prediction time

`backend/app/services/triage_service.py`: for each task, scores → calibration (same
formulas as `evaluation/calibration.py`; a test checks they are equal) → label =
most probable class, confidence = its probability. A complaint goes to human review if
the category confidence < category threshold, the priority confidence < priority
threshold, or the predicted priority is High/Critical. `CONFIDENCE_THRESHOLD` and
`PRIORITY_CONFIDENCE_THRESHOLD` override the stored thresholds. Each prediction stores
the model name (`<category model>+<priority model>`) and version (`v3`).

**Explanations.** Linear models (2–7): the words that pushed the score towards the
predicted class (feature value × class weight; character fragments are left out
because they are not readable). Embedding models (8–9): there are no word weights, so
the reviewer sees only the labels of the most similar training complaints. This is a
weaker explanation and is documented as a limitation.

## Reports (`reports/v3/`)

| File | Content |
|---|---|
| `model_comparison.json` / `.md` | every candidate, both tasks: CV mean ± SD and holdout metrics |
| `cross_validation.json` | per-fold metrics and pooled out-of-fold metrics |
| `holdout_results.json` | holdout metrics for every candidate; calibration/threshold table for the selected model |
| `per_class_metrics/<task>__<model>.csv` | per-class precision/recall/F1 (CV and holdout) |
| `confusion_matrices/<task>__<model>__{cv,holdout}.csv` | confusion matrices |
| `calibration.json` | raw / temperature / sigmoid comparison per model and task |
| `thresholds.json` | chosen threshold, rule, out-of-fold table and holdout table per task |
| `selection.json` | the selection trace and the keyword-baseline comparison |
| `dataset_info.json` | dataset, split and class counts |
| `reproducibility.json` | command, versions, seeds, checksums, git commit, run time |
| `setfit_pilot.json` | the SetFit feasibility gate result |

## Limitations

- The data is synthetic (AI-generated seeds and paraphrases). Results describe the
  method on controlled data, not performance on real campus complaints.
- 120 holdout records: a difference of one record is 0.8 percentage points. Small
  differences between candidates are not meaningful; the SDs in the CV results show
  how much results vary.
- Paraphrases of one seed are similar to each other; grouping prevents them from
  leaking between training and evaluation, but the dataset still has limited variety.
