"""LEGACY (kept for the record; not used by the application). The current pipeline is
ml/scripts/run_experiments.py -> ml/artifacts/v3. See ml/legacy/README.md.

SafeSpeak triage model v2: model comparison, calibration, threshold analysis
and final training.

Usage (from the repository root, with the backend virtual environment):

    backend/.venv/Scripts/python ml/train_triage_v2.py

Inputs:  ml/data/SafeSpeak_dataset_split_600.csv (synthetic/controlled dataset;
         paraphrases of one seed share a group_id and a split)
Outputs: ml/artifacts/v2/{category,priority}.joblib + metadata.json
         ml/reports/evaluation.json (read by the API's research page)
         ml/reports/evaluation.md   (human-readable summary)

Protocol (fixed before running; see docs/ml_evaluation.md):
- The original TEST split (90 records, 30 paraphrase groups) is held out and used
  once, at the end, for every model, so all numbers are on the same records.
- Model selection uses 5-fold StratifiedGroupKFold cross-validation on
  train+val (510 records, 170 groups); folds never split a paraphrase group.
  The candidate with the best mean macro-F1 is chosen per task.
- Calibration: one temperature per task, fitted on the out-of-fold scores
  (minimum negative log-likelihood). Reported before/after as ECE on the test split.
- Threshold: one value applied to both calibrated confidences. Chosen as the
  lowest value at which, out of fold, the category AND the priority are each
  correct at least 75% of the time among complaints at or above it (coverage
  >= 10% each). The v1 rule (both labels jointly correct >= 70%) is not reachable
  on 510 out-of-fold records because priority is the weaker task; the joint curve
  is still reported. Reported on out-of-fold data and on the test split.
- The keyword baseline (backend/app/services/keyword_features.py) is a frozen,
  hand-written lexicon; it is never fitted to data.
"""
import csv
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
import sklearn
from scipy.optimize import minimize_scalar
from scipy.special import log_softmax, softmax
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC

ML_DIR = Path(__file__).resolve().parent
REPO_DIR = ML_DIR.parent
sys.path.insert(0, str(REPO_DIR / "backend"))  # shared keyword lexicon

from app.services.keyword_features import KeywordCounts, keyword_category, keyword_priority  # noqa: E402

DATASET = ML_DIR / "data" / "SafeSpeak_dataset_split_600.csv"
V1_DIR = ML_DIR / "artifacts" / "v1"
OUT_DIR = ML_DIR / "artifacts" / "v2"
REPORT_DIR = ML_DIR / "reports"

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
KEYWORD_RULE = {"category": keyword_category, "priority": keyword_priority}

SEED = 42
N_FOLDS = 5
TARGET_SELECTIVE_ACCURACY = 0.75  # per decision (category and priority separately)
MIN_COVERAGE = 0.10
REPORT_THRESHOLDS = [0.20, 0.24, 0.30, 0.40, 0.50]

# Author-written probe texts (NOT data, not labelled for accuracy): used only to
# check that vague, off-topic or mixed-language inputs are sent to a human.
PROBES = [
    ("vague", "There is some issue, please check."),
    ("vague", "something is wrong, kindly look into it"),
    ("vague", "please help, problem not solved yet"),
    ("vague", "not happy with things here"),
    ("irrelevant", "What is the date of the cultural fest this year?"),
    ("irrelevant", "hello, testing the portal"),
    ("irrelevant", "Can you recommend a good laptop for coding?"),
    ("mixed_language", "hostel ka paani bahut ganda aa raha hai, please check"),
    ("mixed_language", "bus aaj phir late aayi, class miss ho gayi"),
    ("mixed_language", "exam ka result abhi tak nahi aaya"),
    ("misspelled", "projecter in clasroom not wrking for 2 weks"),
    ("misspelled", "fee reciept not genrated after paymnt"),
]


# --- data ---------------------------------------------------------------------------

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_rows() -> list[dict]:
    with DATASET.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    groups: dict[str, set[str]] = {}
    for row in rows:
        groups.setdefault(row["group_id"], set()).add(row["split"])
    leaking = [g for g, splits in groups.items() if len(splits) > 1]
    assert not leaking, f"paraphrase groups span several splits: {leaking[:5]}"
    return rows


def add_typos(text: str, rng: random.Random, rate: float = 0.08) -> str:
    """Deterministic spelling noise: drop, swap or duplicate letters in ~rate of words."""
    words = text.split()
    for i, w in enumerate(words):
        if len(w) > 3 and rng.random() < rate * 3:
            j = rng.randrange(1, len(w) - 1)
            op = rng.choice(("drop", "swap", "double"))
            if op == "drop":
                w = w[:j] + w[j + 1:]
            elif op == "swap":
                w = w[:j] + w[j + 1] + w[j] + w[j + 2:]
            else:
                w = w[:j] + w[j] + w[j:]
            words[i] = w
    return " ".join(words)


# --- candidate models --------------------------------------------------------------------

def word_tfidf():
    return TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1)


def char_tfidf():
    return TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, min_df=2)


def lr(c=1.0):
    return LogisticRegression(max_iter=5000, class_weight="balanced", C=c, random_state=SEED)


def candidates(task: str) -> dict:
    """name -> factory. 'word_lr' is exactly the v1 configuration."""
    return {
        "word_lr": lambda: Pipeline([("features", FeatureUnion([("word", word_tfidf())])), ("clf", lr())]),
        "word_char_lr_C1": lambda: Pipeline(
            [("features", FeatureUnion([("word", word_tfidf()), ("char", char_tfidf())])), ("clf", lr(1.0))]
        ),
        "word_char_lr_C5": lambda: Pipeline(
            [("features", FeatureUnion([("word", word_tfidf()), ("char", char_tfidf())])), ("clf", lr(5.0))]
        ),
        "word_char_svm": lambda: Pipeline(
            [
                ("features", FeatureUnion([("word", word_tfidf()), ("char", char_tfidf())])),
                ("clf", LinearSVC(C=0.5, class_weight="balanced", random_state=SEED)),
            ]
        ),
        "hybrid_kw_lr_C5": lambda: Pipeline(
            [
                (
                    "features",
                    FeatureUnion([("word", word_tfidf()), ("char", char_tfidf()), ("kw", KeywordCounts(task))]),
                ),
                ("clf", lr(5.0)),
            ]
        ),
    }


DESCRIPTIONS = {
    "keyword_baseline": "Hand-written keyword lexicon, most hits wins (no training)",
    "word_lr": "TF-IDF word 1-2 grams + Logistic Regression (v1 configuration)",
    "word_char_lr_C1": "TF-IDF word 1-2 + char 2-5 grams + Logistic Regression (C=1)",
    "word_char_lr_C5": "TF-IDF word 1-2 + char 2-5 grams + Logistic Regression (C=5)",
    "word_char_svm": "TF-IDF word 1-2 + char 2-5 grams + Linear SVM",
    "hybrid_kw_lr_C5": "TF-IDF word + char + keyword-count features + Logistic Regression (C=5)",
}


def scores(model, texts) -> np.ndarray:
    """Per-class decision scores (logits for LR, margins for SVM), columns in classes_ order."""
    return np.asarray(model.decision_function(texts))


def proba(model, texts, temperature: float = 1.0) -> np.ndarray:
    return softmax(scores(model, texts) / temperature, axis=1)


# --- metrics -------------------------------------------------------------------------------

def metrics(y_true, y_pred, labels) -> dict:
    p, r, f, s = precision_recall_fscore_support(y_true, y_pred, labels=labels, zero_division=0)
    mp, mr, mf, _ = precision_recall_fscore_support(y_true, y_pred, labels=labels, average="macro", zero_division=0)
    wp, wr, wf, _ = precision_recall_fscore_support(y_true, y_pred, labels=labels, average="weighted", zero_division=0)
    out = {
        "n": len(y_true),
        "accuracy": round(accuracy_score(y_true, y_pred), 4),
        "macro_precision": round(mp, 4),
        "macro_recall": round(mr, 4),
        "macro_f1": round(mf, 4),
        "weighted_f1": round(wf, 4),
        "per_class": {
            label: {"precision": round(p[i], 4), "recall": round(r[i], 4), "f1": round(f[i], 4), "support": int(s[i])}
            for i, label in enumerate(labels)
        },
        "confusion_matrix": {"labels": labels, "matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist()},
    }
    if labels == PRIORITIES:
        yt, yp = np.array(y_true), np.array(y_pred)
        serious_t, serious_p = np.isin(yt, ["High", "Critical"]), np.isin(yp, ["High", "Critical"])
        out["critical_recall"] = round(float((yp[yt == "Critical"] == "Critical").mean()), 4) if (yt == "Critical").any() else None
        out["high_or_critical_recall"] = round(float(serious_p[serious_t].mean()), 4) if serious_t.any() else None
    return out


def ece(probs: np.ndarray, y_true, classes, bins: int = 10) -> float:
    """Expected calibration error of the top-class confidence."""
    conf = probs.max(axis=1)
    correct = np.array(classes)[probs.argmax(axis=1)] == np.array(y_true)
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (conf > lo) & (conf <= hi)
        if mask.any():
            total += mask.mean() * abs(correct[mask].mean() - conf[mask].mean())
    return round(float(total), 4)


def nll(probs: np.ndarray, y_true, classes) -> float:
    idx = [list(classes).index(y) for y in y_true]
    return round(float(-np.mean(np.log(np.clip(probs[np.arange(len(idx)), idx], 1e-12, 1)))), 4)


def fit_temperature(logits: np.ndarray, y_true, classes) -> float:
    idx = np.array([list(classes).index(y) for y in y_true])

    def loss(t):
        return -log_softmax(logits / t, axis=1)[np.arange(len(idx)), idx].mean()

    return round(float(minimize_scalar(loss, bounds=(0.05, 20), method="bounded").x), 4)


def threshold_rows(cat_probs, pri_probs, cat_classes, pri_classes, y_cat, y_pri, thresholds, severity_rule=False):
    cat_pred = np.array(cat_classes)[cat_probs.argmax(axis=1)]
    pri_pred = np.array(pri_classes)[pri_probs.argmax(axis=1)]
    overall = np.minimum(cat_probs.max(axis=1), pri_probs.max(axis=1))
    both_correct = (cat_pred == np.array(y_cat)) & (pri_pred == np.array(y_pri))
    severe = np.isin(pri_pred, ["High", "Critical"])
    rows = []
    for t in thresholds:
        auto = overall >= t
        if severity_rule:
            auto = auto & ~severe
        n_auto = int(auto.sum())
        rows.append(
            {
                "threshold": round(float(t), 2),
                "auto_handled": n_auto,
                "human_review": int(len(overall) - n_auto),
                "coverage": round(n_auto / len(overall), 4),
                "auto_errors": int((auto & ~both_correct).sum()),
                "selective_accuracy": round(float(both_correct[auto].mean()), 4) if n_auto else None,
                "errors_caught_by_review": int((~auto & ~both_correct).sum()),
            }
        )
    return rows


def task_curve(probs, labels, y_true, thresholds) -> list[dict]:
    """Per task: share of complaints at or above each threshold, and how often
    the AI label is correct among them."""
    conf = probs.max(axis=1)
    correct = np.array(labels)[probs.argmax(axis=1)] == np.array(y_true)
    out = []
    for t in thresholds:
        keep = conf >= t
        out.append(
            {
                "coverage": round(float(keep.mean()), 4),
                "selective_accuracy": round(float(correct[keep].mean()), 4) if keep.any() else None,
            }
        )
    return out


# --- main ------------------------------------------------------------------------------

def main() -> None:
    rows = load_rows()
    dev = [r for r in rows if r["split"] in ("train", "val")]
    test = [r for r in rows if r["split"] == "test"]
    dev_x = [r["text"] for r in dev]
    test_x = [r["text"] for r in test]
    groups = [r["group_id"] for r in dev]
    y = {t: [r[t] for r in dev] for t in LABELS}
    y_test = {t: [r[t] for r in test] for t in LABELS}

    report = {
        "dataset": {
            "file": DATASET.name,
            "sha256": sha256(DATASET),
            "rows": len(rows),
            "groups": len({r["group_id"] for r in rows}),
            "dev_rows": len(dev),
            "test_rows": len(test),
            "source_counts": dict(Counter(r["source"] for r in rows)),
            "style_counts": dict(Counter(r["style"] for r in rows)),
            "test_category_counts": dict(Counter(y_test["category"])),
            "test_priority_counts": dict(Counter(y_test["priority"])),
            "note": "Synthetic/controlled dataset used for model development and evaluation: "
            "200 AI-generated seed complaints and 400 AI paraphrases. No real student complaints.",
        },
        "protocol": {
            "selection": f"{N_FOLDS}-fold StratifiedGroupKFold on train+val (paraphrase groups never split)",
            "test": "original held-out test split, used once for every model",
            "calibration": "temperature scaling fitted on out-of-fold scores",
            "threshold_rule": f"lowest threshold at which category and priority are each correct >= "
            f"{TARGET_SELECTIVE_ACCURACY:.0%} out of fold among complaints at or above it (coverage >= {MIN_COVERAGE:.0%})",
        },
        "models": DESCRIPTIONS,
        "cv": {},
        "test": {},
    }

    folds = list(
        StratifiedGroupKFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED).split(dev_x, y["category"], groups)
    )

    selected, oof_logits, final = {}, {}, {}
    for task, labels in LABELS.items():
        cv = {}
        # keyword baseline: no fitting, evaluate per fold for comparable mean/sd
        kw_pred = [KEYWORD_RULE[task](t) for t in dev_x]
        fold_f1 = [f1_score([y[task][i] for i in va], [kw_pred[i] for i in va], labels=labels, average="macro", zero_division=0) for _, va in folds]
        fold_acc = [accuracy_score([y[task][i] for i in va], [kw_pred[i] for i in va]) for _, va in folds]
        cv["keyword_baseline"] = {
            "macro_f1_mean": round(float(np.mean(fold_f1)), 4), "macro_f1_sd": round(float(np.std(fold_f1)), 4),
            "accuracy_mean": round(float(np.mean(fold_acc)), 4), "accuracy_sd": round(float(np.std(fold_acc)), 4),
        }
        logits_by_model = {}
        for name, factory in candidates(task).items():
            f1s, accs = [], []
            oof = np.zeros((len(dev_x), len(labels)))
            for tr, va in folds:
                m = factory().fit([dev_x[i] for i in tr], [y[task][i] for i in tr])
                classes = list(m.classes_)
                s = scores(m, [dev_x[i] for i in va])
                oof[va] = s[:, [classes.index(lbl) for lbl in labels]]
                pred = [classes[k] for k in s.argmax(axis=1)]
                truth = [y[task][i] for i in va]
                f1s.append(f1_score(truth, pred, labels=labels, average="macro", zero_division=0))
                accs.append(accuracy_score(truth, pred))
            logits_by_model[name] = oof
            cv[name] = {
                "macro_f1_mean": round(float(np.mean(f1s)), 4), "macro_f1_sd": round(float(np.std(f1s)), 4),
                "accuracy_mean": round(float(np.mean(accs)), 4), "accuracy_sd": round(float(np.std(accs)), 4),
            }
            print(f"[cv] {task:8s} {name:18s} macro-F1 {cv[name]['macro_f1_mean']:.3f} ± {cv[name]['macro_f1_sd']:.3f}")
        print(f"[cv] {task:8s} {'keyword_baseline':18s} macro-F1 {cv['keyword_baseline']['macro_f1_mean']:.3f}")
        best = max(candidates(task), key=lambda n: cv[n]["macro_f1_mean"])
        selected[task] = best
        oof_logits[task] = logits_by_model[best]
        report["cv"][task] = cv

        # Final fit of every candidate on all dev data; one evaluation on test.
        test_results = {"keyword_baseline": metrics(y_test[task], [KEYWORD_RULE[task](t) for t in test_x], labels)}
        v1 = joblib.load(V1_DIR / f"{task}.joblib")
        test_results["v1_deployed"] = metrics(y_test[task], list(v1.predict(test_x)), labels)
        for name, factory in candidates(task).items():
            m = factory().fit(dev_x, y[task])
            if name == best:
                final[task] = m
            test_results[name] = metrics(y_test[task], list(m.predict(test_x)), labels)
        report["test"][task] = test_results

    # --- calibration (temperature per task, fitted on out-of-fold scores) ---
    calibration = {}
    for task, labels in LABELS.items():
        t = fit_temperature(oof_logits[task], y[task], labels)
        m = final[task]
        classes = list(m.classes_)
        raw = proba(m, test_x)
        cal = proba(m, test_x, t)
        calibration[task] = {
            "method": "temperature",
            "temperature": t,
            "oof": {
                "ece_before": ece(softmax(oof_logits[task], axis=1), y[task], labels),
                "ece_after": ece(softmax(oof_logits[task] / t, axis=1), y[task], labels),
            },
            "test": {
                "ece_before": ece(raw, y_test[task], classes),
                "ece_after": ece(cal, y_test[task], classes),
                "nll_before": nll(raw, y_test[task], classes),
                "nll_after": nll(cal, y_test[task], classes),
                "mean_confidence_after": round(float(cal.max(axis=1).mean()), 4),
                "accuracy": report["test"][task][selected[task]]["accuracy"],
            },
        }
        print(f"[cal] {task}: T={t} test ECE {calibration[task]['test']['ece_before']} -> {calibration[task]['test']['ece_after']}")
    report["calibration"] = calibration

    # --- threshold selection on calibrated out-of-fold probabilities ---
    oof_cat = softmax(oof_logits["category"] / calibration["category"]["temperature"], axis=1)
    oof_pri = softmax(oof_logits["priority"] / calibration["priority"]["temperature"], axis=1)
    grid = np.round(np.arange(0.05, 0.96, 0.01), 2)
    oof_table = threshold_rows(oof_cat, oof_pri, CATEGORIES, PRIORITIES, y["category"], y["priority"], grid)
    task_curves = {
        task: task_curve(p, LABELS[task], y[task], grid) for task, p in (("category", oof_cat), ("priority", oof_pri))
    }
    recommended = None
    for i, t in enumerate(grid):
        rows_t = {task: task_curves[task][i] for task in LABELS}
        if all(
            r["coverage"] >= MIN_COVERAGE and r["selective_accuracy"] is not None
            and r["selective_accuracy"] >= TARGET_SELECTIVE_ACCURACY
            for r in rows_t.values()
        ):
            recommended = {"threshold": float(t), **{f"{task}_oof": r for task, r in rows_t.items()}}
            break
    threshold = recommended["threshold"] if recommended else 1.0

    def ordered(task):
        m = final[task]
        classes = list(m.classes_)
        p = proba(m, test_x, calibration[task]["temperature"])
        return p[:, [classes.index(lbl) for lbl in LABELS[task]]]

    test_cat, test_pri = ordered("category"), ordered("priority")
    shown = sorted(set(REPORT_THRESHOLDS) | {threshold})
    report["threshold"] = {
        "recommended": threshold,
        "rule": report["protocol"]["threshold_rule"],
        "recommendation_row_oof": recommended,
        "oof_table": threshold_rows(oof_cat, oof_pri, CATEGORIES, PRIORITIES, y["category"], y["priority"], shown),
        "test_table": threshold_rows(test_cat, test_pri, CATEGORIES, PRIORITIES, y_test["category"], y_test["priority"], shown),
        "test_table_with_severity_rule": threshold_rows(
            test_cat, test_pri, CATEGORIES, PRIORITIES, y_test["category"], y_test["priority"], shown, severity_rule=True
        ),
        "oof_curve": [
            {
                "threshold": float(t),
                "category_coverage": task_curves["category"][i]["coverage"],
                "category_selective_accuracy": task_curves["category"][i]["selective_accuracy"],
                "priority_coverage": task_curves["priority"][i]["coverage"],
                "priority_selective_accuracy": task_curves["priority"][i]["selective_accuracy"],
                "joint_coverage": oof_table[i]["coverage"],
                "joint_selective_accuracy": oof_table[i]["selective_accuracy"],
            }
            for i, t in enumerate(grid)
        ],
    }
    print(f"[threshold] recommended {threshold}: {recommended}")

    # --- robustness: per-style accuracy (out-of-fold), typo noise (test), probes ---
    oof_cat_pred = np.array(CATEGORIES)[oof_cat.argmax(axis=1)]
    kw_dev = np.array([keyword_category(t) for t in dev_x])
    styles = sorted({r["style"] for r in dev})
    report["robustness"] = {
        "by_style_oof": [
            {
                "style": s,
                "n": int(sum(1 for r in dev if r["style"] == s)),
                "ml_category_accuracy": round(float((oof_cat_pred[mask] == np.array(y["category"])[mask]).mean()), 4),
                "keyword_category_accuracy": round(float((kw_dev[mask] == np.array(y["category"])[mask]).mean()), 4),
                "review_rate": round(float((np.minimum(oof_cat.max(axis=1), oof_pri.max(axis=1))[mask] < threshold).mean()), 4),
            }
            for s in styles
            for mask in [np.array([r["style"] == s for r in dev])]
        ],
    }
    rng = random.Random(SEED)
    noisy = [add_typos(t, rng) for t in test_x]
    report["robustness"]["typo_noise_test"] = {
        "description": "Same 90 test texts with deterministic spelling noise (dropped/swapped/doubled letters)",
        "ml_category_accuracy_clean": report["test"]["category"][selected["category"]]["accuracy"],
        "ml_category_accuracy_noisy": round(accuracy_score(y_test["category"], final["category"].predict(noisy)), 4),
        "keyword_category_accuracy_clean": report["test"]["category"]["keyword_baseline"]["accuracy"],
        "keyword_category_accuracy_noisy": round(accuracy_score(y_test["category"], [keyword_category(t) for t in noisy]), 4),
    }
    probe_rows = []
    for kind, text in PROBES:
        pc = proba(final["category"], [text], calibration["category"]["temperature"])[0]
        pp = proba(final["priority"], [text], calibration["priority"]["temperature"])[0]
        conf = float(min(pc.max(), pp.max()))
        probe_rows.append(
            {
                "kind": kind,
                "text": text,
                "category": final["category"].classes_[pc.argmax()],
                "category_confidence": round(float(pc.max()), 4),
                "priority": final["priority"].classes_[pp.argmax()],
                "confidence": round(conf, 4),
                "sent_to_review": conf < threshold or final["priority"].classes_[pp.argmax()] in ("High", "Critical"),
            }
        )
    report["robustness"]["probes"] = {
        "description": "Author-written probe texts (not dataset records, not used for accuracy). "
        "Desired behaviour: sent to human review.",
        "rows": probe_rows,
        "sent_to_review": sum(r["sent_to_review"] for r in probe_rows),
        "total": len(probe_rows),
    }

    # --- save artifacts ---
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    for task in LABELS:
        joblib.dump(final[task], OUT_DIR / f"{task}.joblib")
    report["selected"] = {t: {"model": selected[t], "description": DESCRIPTIONS[selected[t]]} for t in LABELS}
    metadata = {
        "model_name": "hybrid-tfidf-lr",
        "model_version": "v2",
        "sklearn_version": sklearn.__version__,
        "trained_on": "train+val (510 records)",
        "dataset": {k: report["dataset"][k] for k in ("file", "sha256", "rows", "source_counts", "note")},
        "labels": {"category": CATEGORIES, "priority": PRIORITIES},
        "calibration": {t: {"method": "temperature", "temperature": calibration[t]["temperature"]} for t in LABELS},
        "confidence": {
            "definition": "temperature-scaled softmax of decision scores; overall = min(category, priority)",
            "recommended_threshold": threshold,
            "rule": report["threshold"]["rule"],
        },
        "selected": report["selected"],
        "metrics": {"test": {t: report["test"][t][selected[t]] for t in LABELS}},
        "files": {f"{t}.joblib": sha256(OUT_DIR / f"{t}.joblib") for t in LABELS},
    }
    (OUT_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (REPORT_DIR / "evaluation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report)
    print(f"Saved {OUT_DIR} and {REPORT_DIR}")


def write_markdown(report: dict) -> None:
    def pct(v):
        return "—" if v is None else f"{100 * v:.1f}%"

    lines = ["# SafeSpeak triage model evaluation (generated by ml/train_triage_v2.py)", ""]
    lines += [f"Dataset: {report['dataset']['note']}", ""]
    for task in LABELS:
        lines += [f"## {task.title()}: held-out test split ({report['dataset']['test_rows']} records)", ""]
        lines += ["| Model | Accuracy | Macro-P | Macro-R | Macro-F1 | CV macro-F1 (dev, mean ± sd) |", "|---|---|---|---|---|---|"]
        for name, m in report["test"][task].items():
            cv = report["cv"][task].get(name)
            cvs = f"{cv['macro_f1_mean']:.3f} ± {cv['macro_f1_sd']:.3f}" if cv else "— (v1 was trained on train only)"
            mark = " **(selected)**" if name == report["selected"][task]["model"] else ""
            lines.append(
                f"| {name}{mark} | {pct(m['accuracy'])} | {pct(m['macro_precision'])} | {pct(m['macro_recall'])} "
                f"| {pct(m['macro_f1'])} | {cvs} |"
            )
        lines.append("")
    cal = report["calibration"]
    lines += ["## Calibration (test ECE, lower is better)", ""]
    for task in LABELS:
        c = cal[task]
        lines.append(f"- {task}: T = {c['temperature']}, ECE {c['test']['ece_before']} → {c['test']['ece_after']}, NLL {c['test']['nll_before']} → {c['test']['nll_after']}")
    th = report["threshold"]
    lines += ["", f"## Threshold (recommended {th['recommended']})", "", "| Threshold | Auto-handled | Human review | Errors in auto | Selective acc. |", "|---|---|---|---|---|"]
    for r in th["test_table"]:
        lines.append(f"| {r['threshold']} | {r['auto_handled']} | {r['human_review']} | {r['auto_errors']} | {pct(r['selective_accuracy'])} |")
    (REPORT_DIR / "evaluation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
