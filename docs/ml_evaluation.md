# AI triage: evaluation and model choice (model v2)

All numbers below are produced by `ml/train_triage_v2.py` and saved in `ml/reports/evaluation.json`
(the API serves this file on the **AI evaluation** page) and `ml/reports/evaluation.md`. Re-run from
the repository root with:

```
backend/.venv/Scripts/python ml/train_triage_v2.py
```

## Dataset (synthetic / controlled)

"Synthetic/controlled dataset used for model development and evaluation." 600 records: 200 AI-generated
seed complaints and 400 AI paraphrases (`ml/data/SafeSpeak_dataset_split_600.csv`). **No real student
complaints.** Each seed and its paraphrases share a `group_id` (200 groups of 3); a group never crosses
splits. The original split is kept: 420 train / 90 validation / 90 test.

## Protocol (fixed before running)

| Step | What | Data used |
|---|---|---|
| Keyword baseline | Hand-written lexicon per category/priority (`backend/app/services/keyword_features.py`), most hits wins. Written from the category definitions and never fitted to data. | — |
| Model selection | 5 candidates per task, 5-fold `StratifiedGroupKFold` (paraphrase groups never split); best mean macro-F1 wins | train + val (510) |
| Calibration | One temperature per task, fitted on out-of-fold scores (minimum NLL) | train + val, out of fold |
| Threshold | Lowest threshold at which category **and** priority are each correct ≥ 75% among complaints at or above it, coverage ≥ 10% | train + val, out of fold |
| Final model | Selected configuration refitted on train + val | train + val |
| Final report | Every model (keyword baseline, the deployed v1 model, all candidates) evaluated **once** on the same held-out test split | test (90) |

The v1 threshold rule (both labels jointly correct ≥ 70%) cannot be reached on 510 out-of-fold records:
priority is the weaker task, so joint accuracy stays below 65% at any useful coverage (the v1 value 0.24
was chosen on only 17 validation records). The rule was therefore changed to the per-decision rule above;
the joint curve is still reported.

## Category: keyword baseline vs ML (held-out test, 90 records)

| Model | Accuracy | Macro-P | Macro-R | Macro-F1 | CV macro-F1 (mean ± sd) |
|---|---|---|---|---|---|
| Keyword baseline | 51.1% | 45.2% | 45.2% | 42.8% | 62.4% ± 7.1 |
| v1 model (Review-II, train only) | 51.1% | 50.2% | 51.1% | 47.4% | — |
| TF-IDF words + LR (v1 configuration) | 54.4% | 53.9% | 56.3% | 51.4% | 50.3% ± 7.6 |
| Words + chars + LR (C=1) | 65.6% | 63.2% | 66.2% | 61.6% | 57.9% ± 7.4 |
| Words + chars + LR (C=5) | 65.6% | 63.5% | 67.0% | 62.5% | 58.0% ± 7.1 |
| Words + chars + Linear SVM | 67.8% | 66.0% | 68.3% | 63.8% | 57.1% ± 6.3 |
| **Hybrid: words + chars + keyword counts + LR (selected)** | **65.6%** | 61.2% | 61.6% | **57.8%** | **65.1% ± 6.2** |

Per-class F1 on test (keyword → selected): Hostel 0.42 → 0.67, Exam 0.77 → 0.82, Academic 0.15 → 0.15,
Infrastructure 0.75 → 0.71, Safety 0.00 → 0.38, Administrative 0.67 → 0.80, Library/Transport 0.67 → 0.86,
Other 0.00 → 0.25. Confusion matrices are in `evaluation.json` and on the AI evaluation page.

## Priority (held-out test, 90 records)

| Model | Accuracy | Macro-F1 | CV macro-F1 |
|---|---|---|---|
| Keyword baseline | 40.0% | 25.2% | 25.9% ± 10.7 |
| v1 model (Review-II) | 53.3% | 55.6% | — |
| **TF-IDF words + LR (selected, refitted on train + val)** | 50.0% | 52.2% | **59.6% ± 7.0** |
| Words + chars + Linear SVM | 53.3% | 56.4% | 59.3% ± 6.8 |

Selected priority model on test: Critical recall 83.3% (10 of 12), High+Critical recall 52.4%. The v1
model had 91.7% (11 of 12) and 61.9% on the same records. With 12 Critical test records the difference
is one complaint; it is reported, not hidden. This is why **High and Critical predictions always go to a
human**, regardless of confidence.

## Calibration (temperature scaling)

| Task | T | Test ECE before → after | Out-of-fold ECE before → after |
|---|---|---|---|
| Category | 1.18 | 0.148 → **0.112** (better) | 0.074 → 0.064 |
| Priority | 0.30 | 0.142 → 0.176 (**worse**) | 0.232 → 0.055 |

Category calibration transferred to the test split; priority did not (the test split has a very different
priority mix: 30 High / 12 Critical of 90). Both temperatures are applied as specified by the protocol.

## Threshold analysis (held-out test)

Chosen threshold **0.65** (out of fold: category 84.9% correct on 52% coverage, priority 76.9% correct on
40% coverage). "Errors" = automatically handled complaints with a wrong category or priority.

| Threshold | Auto (confidence only) | Human review | Errors in auto | Auto with High/Critical rule (deployed) | Errors in auto (deployed) |
|---|---|---|---|---|---|
| 0.20 | 90 | 0 | 58 | 57 | 38 |
| 0.24 | 89 | 1 | 57 | 56 | 37 |
| 0.30 | 84 | 6 | 52 | 51 | 32 |
| 0.40 | 70 | 20 | 40 | 44 | 25 |
| 0.50 | 50 | 40 | 24 | 32 | 14 |
| **0.65** | **30** | **60** | **14** | **19** | **9** |

With the deployed policy, 19 of 90 test complaints (21%) would be routed automatically and 71 reviewed by a
person; 9 of the 19 automatic ones have at least one wrong label (a reviewer can still override them). The
threshold is configurable (`CONFIDENCE_THRESHOLD`). We do not claim it is optimal: it is the lowest value
that meets the stated policy on out-of-fold data.

## Robustness

- **Writing style** (out-of-fold category accuracy, ML vs keyword): formal 71.9 / 71.9, polite 69.8 / 53.5,
  detailed 63.1 / 59.6, casual 58.0 / 62.3, vague 66.7 / 72.2, tricky 54.5 / 63.6, typos 81.0 / 81.0. Vague
  texts go to human review 94% of the time.
- **Spelling noise** (same test texts with injected typos): ML 65.6% → 63.3%, keyword 51.1% → 46.7%.
- **Difficult probes** (12 author-written texts, not data): vague, irrelevant, mixed Hindi–English and
  misspelled inputs. 11 of 12 were sent to human review; the one automatic case ("fee reciept not genrated
  after paymnt") was classified correctly as Administrative / Fees.

## Findings to state

1. The faculty observation was correct: the Review-II model (TF-IDF words + LR) was weaker than the keyword
   baseline in cross-validation (50.3% vs 62.4% macro-F1).
2. Character n-grams improved pure ML (58.0%) but it still did not beat the keyword lexicon in CV.
3. The hybrid model (ML + keyword-count features) was best in CV (65.1%) and was selected. On the
   held-out test set it beats the keyword baseline by 14.4 points accuracy and 15.0 points macro-F1.
   Its explanations show the keyword features carry most of the weight: the gain comes largely from
   combining the lexicon with learned weights.
4. On the test set a pure ML variant (Linear SVM) scored higher than the selected hybrid. We kept the
   CV-selected model; choosing by test score would be tuning on the test set.
5. Priority remains the weaker task; humans review every High/Critical prediction.
6. At this model quality most complaints still need a human. That is the intended human-in-the-loop
   behaviour, and the reason the confidence check exists.
7. All results are on synthetic data; real-world performance is unknown.

## Model evidence shown to reviewers

For every complaint the API stores (in `ai_predictions.explanation`) the words with the largest positive
contribution to the predicted class: feature value × the linear model's weight. This is exact for linear
models; character n-gram features are omitted because fragments are not readable. Keyword-list features
appear as "Keyword list: <category>". The keyword baseline's own labels are stored alongside, so a
reviewer sees whether the rules and the model agree. No LLM or external service is used.
