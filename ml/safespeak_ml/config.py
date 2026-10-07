"""Experiment protocol for model v3. Everything here is fixed BEFORE any model is
trained or evaluated; changing it after seeing results would invalidate the comparison.
"""
from pathlib import Path

ML_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = ML_DIR.parent
BACKEND_DIR = REPO_DIR / "backend"

# --- data -------------------------------------------------------------------------------
DATASET_FILE = ML_DIR / "data" / "SafeSpeak_dataset_split_600.csv"
DATASET_VERSION = "safespeak-600-v1"
# SHA-256 of the approved dataset file; the pipeline refuses to run on any other file.
DATASET_SHA256 = "66483ef778c0af0ae2e4e7656478e651f6d9f76eea1d54822be3c1f607fbd776"
SPLIT_FILE = ML_DIR / "data" / "splits" / "v3_split.csv"

CATEGORIES = [
    "Hostel",
    "Exam",
    "Academic / Department",
    "Infrastructure and facilities",
    "Safety and welfare",
    "Administrative / Fees",
    "Library / Transport",
    "Other",
]
PRIORITIES = ["Low", "Medium", "High", "Critical"]
LABELS = {"category": CATEGORIES, "priority": PRIORITIES}
TASKS = ("category", "priority")

# --- split and cross-validation -----------------------------------------------------------
SEED = 42
# Holdout: one fold of a 5-fold StratifiedGroupKFold over all 200 paraphrase groups
# (stratified by category) = 40 groups / 120 records. Created once, never used for any choice.
HOLDOUT_FOLDS = 5
# Development set (160 groups / 480 records): repeated grouped CV.
CV_FOLDS = 5
CV_REPEATS = 5
CV_SEEDS = [SEED + r for r in range(CV_REPEATS)]

# --- confidence ---------------------------------------------------------------------------
CALIBRATION_METHODS = ("raw", "temperature", "sigmoid")
# Threshold rule (per task, on calibrated out-of-fold confidences of the selected model):
# lowest threshold t at which automatically handled cases (confidence >= t) are correct at
# least THRESHOLD_TARGET of the time while at least THRESHOLD_MIN_COVERAGE are still automatic.
# The 80% value is the target for automatic-decision correctness, NOT the threshold itself.
THRESHOLD_TARGET = 0.80
THRESHOLD_MIN_COVERAGE = 0.10
THRESHOLD_GRID = [round(0.05 + 0.01 * i, 2) for i in range(91)]  # 0.05 .. 0.95
REPORT_THRESHOLDS = [0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90]
ECE_BINS = 10

# --- model selection ------------------------------------------------------------------------
# 1. highest mean grouped-CV macro-F1; 2. models within one SD of the best are tied ->
# prefer the more stable (lower SD; SDs within STABILITY_TIE count as equal);
# 3. if still tied, prefer the simpler model (COMPLEXITY order); 4. compare with the
# keyword baseline; 5. the holdout is never used to choose.
STABILITY_TIE = 0.005
SELECTABLE = [
    "tfidf_logistic",
    "tfidf_svm",
    "word_ngram_logistic",
    "word_char_logistic",
    "word_char_svm",
    "hybrid_classifier",
    "minilm_logistic",
    "setfit_classifier",
]
COMPLEXITY = {name: i for i, name in enumerate(SELECTABLE)}  # lower = simpler

# Deployment constraint (DISCLOSED: added on 2026-10-07 AFTER the first full run, by the
# project owner's decision). The first run's rule selected MiniLM+LR (#8) for category;
# deploying it would put PyTorch in the backend (+~530 MB image, +~370 MB RAM, ~30 s
# startup on the development laptop). The backend must run without PyTorch, so only
# candidates of kind "linear-text" are deployable. The SAME rule is applied to this pool;
# the unconstrained result is still computed and reported next to it.
DEPLOYMENT_CONSTRAINT = {
    "rule": "the backend must run without PyTorch: only linear-text candidates (2-7) are deployable",
    "added": "2026-10-07, after the first full run (decision recorded and disclosed; not pre-declared)",
    "reason": "the unconstrained winner (MiniLM+LR) would add PyTorch to the backend: about +530 MB image, "
              "+370 MB RAM and +30 s startup measured on the development laptop",
}
DEPLOYABLE = [
    "tfidf_logistic",
    "tfidf_svm",
    "word_ngram_logistic",
    "word_char_logistic",
    "word_char_svm",
    "hybrid_classifier",
]

# --- fixed hyperparameters (no search: 480 development records do not support honest tuning) --
LOGISTIC = {"C": 1.0, "class_weight": "balanced", "max_iter": 5000}
LINEAR_SVM = {"C": 1.0, "class_weight": "balanced", "max_iter": 10000}
WORD_TFIDF = {"lowercase": True, "strip_accents": "unicode", "sublinear_tf": True, "min_df": 1}
CHAR_TFIDF = {"analyzer": "char_wb", "ngram_range": (2, 5), "lowercase": True, "strip_accents": "unicode",
              "sublinear_tf": True, "min_df": 2}

# --- sentence encoder for candidates 8 and 9 (local after one pinned download) --------------
ENCODER_REPO = "sentence-transformers/all-MiniLM-L6-v2"
ENCODER_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
ENCODER_LICENSE = "apache-2.0"
ARTIFACT_VERSION = "v3"
ARTIFACTS_DIR = ML_DIR / "artifacts" / ARTIFACT_VERSION
ENCODER_DIR = ARTIFACTS_DIR / "encoders" / "all-MiniLM-L6-v2"
ENCODER_LOCK = ML_DIR / "encoders.lock.json"
CACHE_DIR = ML_DIR / ".cache"

# --- SetFit feasibility gate (decided before it runs) -----------------------------------------
SETFIT = {"num_iterations": 20, "num_epochs": 1, "batch_size": 16}
SETFIT_MAX_SECONDS_PER_FIT = 600

REPORTS_DIR = ML_DIR / "reports" / ARTIFACT_VERSION
KEYWORD_LEXICON_FILE = BACKEND_DIR / "app" / "services" / "keyword_features.py"
# Frozen before the v2 exploratory run; any edit changes this checksum and fails the pipeline.
KEYWORD_LEXICON_SHA256 = "361a2c35abbf7823528cb5f38f687560aec61b29b49c3ad4b9cac7368ff8d944"
