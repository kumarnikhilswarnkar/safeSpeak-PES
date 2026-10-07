"""LEGACY (kept for the record; not used by the application). The current pipeline is
ml/scripts/run_experiments.py -> ml/artifacts/v3. See ml/legacy/README.md.

Train the SafeSpeak triage models (category and priority) and pick the
confidence threshold from validation data.

Usage (from the repository root, with the backend virtual environment):

    backend/.venv/Scripts/python ml/train_triage.py

Inputs:  ml/data/SafeSpeak_dataset_split_600.csv  (synthetic research dataset with a
         group-aware train/val/test split: paraphrases of one seed share a split)
Outputs: ml/artifacts/<version>/category.joblib, priority.joblib, metadata.json

Method:
- TF-IDF (word 1-2 grams) + Logistic Regression (class_weight="balanced"), one model
  per task, fitted on the TRAIN split only.
- Confidence of a prediction = highest class probability. A complaint's overall
  confidence = min(category confidence, priority confidence).
- Threshold selection uses the VALIDATION split only: for each candidate threshold,
  coverage = share of complaints at or above it, and selective accuracy = share of
  those where BOTH category and priority are correct. The recommended threshold is
  the lowest one whose selective accuracy reaches TARGET_SELECTIVE_ACCURACY with at
  least MIN_COVERED complaints. Everything below it goes to human review.
- The TEST split is used once, for reporting only.
"""
import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, recall_score
from sklearn.pipeline import Pipeline

ML_DIR = Path(__file__).resolve().parent
DATASET = ML_DIR / "data" / "SafeSpeak_dataset_split_600.csv"

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

SEED = 42
TARGET_SELECTIVE_ACCURACY = 0.70
MIN_COVERED = 5


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
    assert {r["category"] for r in rows} == set(CATEGORIES), "unexpected category labels"
    assert {r["priority"] for r in rows} == set(PRIORITIES), "unexpected priority labels"
    return rows


def make_pipeline() -> Pipeline:
    return Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1)),
            ("clf", LogisticRegression(max_iter=5000, class_weight="balanced", random_state=SEED)),
        ]
    )


def evaluate(model: Pipeline, texts, labels, label_order) -> dict:
    predicted = model.predict(texts)
    result = {
        "n": len(labels),
        "accuracy": round(accuracy_score(labels, predicted), 4),
        "macro_f1": round(f1_score(labels, predicted, labels=label_order, average="macro", zero_division=0), 4),
        "per_class_f1": {
            label: round(score, 4)
            for label, score in zip(
                label_order, f1_score(labels, predicted, labels=label_order, average=None, zero_division=0)
            )
        },
        "confusion_matrix": {
            "labels": label_order,
            "matrix": confusion_matrix(labels, predicted, labels=label_order).tolist(),
        },
    }
    if label_order == PRIORITIES:
        result["critical_recall"] = round(
            recall_score(labels, predicted, labels=["Critical"], average="micro", zero_division=0), 4
        )
        serious_true = np.isin(labels, ["High", "Critical"])
        serious_pred = np.isin(predicted, ["High", "Critical"])
        result["high_or_critical_recall"] = round(float(serious_pred[serious_true].mean()), 4)
        result["high_or_critical_false_negatives"] = int((serious_true & ~serious_pred).sum())
        result["high_or_critical_false_positives"] = int((~serious_true & serious_pred).sum())
    return result


def threshold_table(cat_model, pri_model, texts, cats, pris) -> list[dict]:
    cat_conf = cat_model.predict_proba(texts).max(axis=1)
    pri_conf = pri_model.predict_proba(texts).max(axis=1)
    overall = np.minimum(cat_conf, pri_conf)
    both_correct = (cat_model.predict(texts) == np.array(cats)) & (pri_model.predict(texts) == np.array(pris))
    table = []
    for threshold in np.round(np.arange(0.05, 0.96, 0.01), 2):
        covered = overall >= threshold
        n_covered = int(covered.sum())
        table.append(
            {
                "threshold": float(threshold),
                "covered": n_covered,
                "coverage": round(n_covered / len(texts), 4),
                "selective_accuracy": round(float(both_correct[covered].mean()), 4) if n_covered else None,
            }
        )
    return table


def recommend(table: list[dict]) -> dict:
    for row in table:
        if (
            row["covered"] >= MIN_COVERED
            and row["selective_accuracy"] is not None
            and row["selective_accuracy"] >= TARGET_SELECTIVE_ACCURACY
        ):
            return {**row, "rule": "lowest threshold reaching the target selective accuracy"}
    # Target unreachable: be conservative and send everything to human review.
    return {
        "threshold": 1.0,
        "covered": 0,
        "coverage": 0.0,
        "selective_accuracy": None,
        "rule": "target not reachable on validation data; all complaints go to human review",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="v1")
    args = parser.parse_args()

    rows = load_rows()
    by_split = {s: [r for r in rows if r["split"] == s] for s in ("train", "val", "test")}

    def cols(split):
        part = by_split[split]
        return [r["text"] for r in part], [r["category"] for r in part], [r["priority"] for r in part]

    train_x, train_cat, train_pri = cols("train")
    val_x, val_cat, val_pri = cols("val")
    test_x, test_cat, test_pri = cols("test")

    cat_model = make_pipeline().fit(train_x, train_cat)
    pri_model = make_pipeline().fit(train_x, train_pri)
    assert list(cat_model.classes_) == sorted(CATEGORIES)
    assert list(pri_model.classes_) == sorted(PRIORITIES)

    table = threshold_table(cat_model, pri_model, val_x, val_cat, val_pri)
    recommended = recommend(table)
    test_table = threshold_table(cat_model, pri_model, test_x, test_cat, test_pri)
    at_threshold_on_test = next(
        (r for r in test_table if r["threshold"] == recommended["threshold"]),
        {"threshold": recommended["threshold"], "covered": 0, "coverage": 0.0, "selective_accuracy": None},
    )

    out_dir = ML_DIR / "artifacts" / args.version
    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(cat_model, out_dir / "category.joblib")
    joblib.dump(pri_model, out_dir / "priority.joblib")

    metadata = {
        "model_name": "tfidf-logreg",
        "model_version": args.version,
        "sklearn_version": sklearn.__version__,
        "dataset": {
            "file": DATASET.name,
            "sha256": sha256(DATASET),
            "rows": len(rows),
            "split_sizes": {s: len(v) for s, v in by_split.items()},
            "source_counts": dict(Counter(r["source"] for r in rows)),
            "note": "All 600 texts are synthetic (AI-generated seeds and AI paraphrases).",
        },
        "labels": {"category": CATEGORIES, "priority": PRIORITIES},
        "confidence": {
            "definition": "max class probability per task; overall = min(category, priority)",
            "selection_split": "val",
            "target_selective_accuracy": TARGET_SELECTIVE_ACCURACY,
            "min_covered": MIN_COVERED,
            "recommended_threshold": recommended["threshold"],
            "recommendation": recommended,
            "validation_table": table,
            "test_at_recommended_threshold": at_threshold_on_test,
        },
        "metrics": {
            "validation": {
                "category": evaluate(cat_model, val_x, val_cat, CATEGORIES),
                "priority": evaluate(pri_model, val_x, val_pri, PRIORITIES),
            },
            "test": {
                "category": evaluate(cat_model, test_x, test_cat, CATEGORIES),
                "priority": evaluate(pri_model, test_x, test_pri, PRIORITIES),
            },
        },
        "files": {
            "category.joblib": sha256(out_dir / "category.joblib"),
            "priority.joblib": sha256(out_dir / "priority.joblib"),
        },
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    test = metadata["metrics"]["test"]
    print(f"Saved {out_dir}")
    print(f"Test category: accuracy {test['category']['accuracy']}, macro-F1 {test['category']['macro_f1']}")
    print(
        f"Test priority: accuracy {test['priority']['accuracy']}, macro-F1 {test['priority']['macro_f1']}, "
        f"Critical recall {test['priority']['critical_recall']}, "
        f"High+Critical recall {test['priority']['high_or_critical_recall']}"
    )
    print(f"Recommended confidence threshold (validation): {recommended}")
    print(f"At that threshold on test: {at_threshold_on_test}")


if __name__ == "__main__":
    main()
