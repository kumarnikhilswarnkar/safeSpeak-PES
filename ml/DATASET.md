# SafeSpeak training dataset (`safespeak-600-v1`)

| | |
|---|---|
| File | `ml/data/SafeSpeak_dataset_split_600.csv` |
| SHA-256 | `66483ef778c0af0ae2e4e7656478e651f6d9f76eea1d54822be3c1f607fbd776` (checked on every load) |
| Records | 600 = 200 paraphrase groups × 3 |
| Nature | **Synthetic / controlled.** 200 AI-generated seed complaints (`ai_generated_batch1_v2`, `ai_generated_batch2`) and 2 AI paraphrases of each (`ai_paraphrase_of_batch1/2`) |
| Labels | `category` (8 classes), `priority` (4 classes), assigned per seed; all 3 members of a group share both labels (asserted) |
| Human annotation | none (the `annotator*` columns are empty) |
| Median length | 16 words |

**Category counts:** Hostel 78 · Exam 75 · Academic / Department 75 · Infrastructure and
facilities 75 · Safety and welfare 75 · Administrative / Fees 72 · Library / Transport 72 · Other 78.

**Priority counts:** Low 159 · Medium 210 · High 147 · Critical 84.

**Writing styles (`style`):** detailed 160 · short 128 · formal 112 · casual 79 · polite 46 ·
typos 24 · angry 19 · vague 18 · tricky 14.

## Split used by v3

`ml/data/splits/v3_split.csv` (SHA-256 `c6c6819f…74a4`), created once by
`ml/scripts/make_split.py` and verifiable with `make_split.py --check`:

- **development:** 480 records / 160 groups (cross-validation, selection, calibration, thresholds);
- **holdout:** 120 records / 40 groups (reported once; never used for any decision).

The `split` column inside the CSV (train 420 / val 90 / test 90) belongs to the legacy
v1/v2 scripts and is **not** used by v3.

## What it can and cannot show

It shows how the method behaves on controlled, balanced text: whether ML beats the
frozen keyword rules, how confident the models are, and how much would go to human
review. It cannot show performance on real campus complaints (different vocabulary,
spelling, length, class balance). Real-world evaluation needs real, consented,
anonymised complaints, which this project does not use. The model is never trained on
live complaints from the application database.

The externally researched alaminxpro dataset is **not** used for training or evaluation
(it is documented separately as research only).
