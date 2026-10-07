"""Classification metrics used for every candidate and task."""
import numpy as np
from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support


def classification_metrics(y_true: list[str], y_pred: list[str], labels: list[str]) -> dict:
    p, r, f, s = precision_recall_fscore_support(y_true, y_pred, labels=labels, zero_division=0)
    mp, mr, mf, _ = precision_recall_fscore_support(y_true, y_pred, labels=labels, average="macro", zero_division=0)
    _, _, wf, _ = precision_recall_fscore_support(y_true, y_pred, labels=labels, average="weighted", zero_division=0)
    out = {
        "n": len(y_true),
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "macro_precision": round(float(mp), 4),
        "macro_recall": round(float(mr), 4),
        "macro_f1": round(float(mf), 4),
        "weighted_f1": round(float(wf), 4),
        "per_class": {
            label: {"precision": round(float(p[i]), 4), "recall": round(float(r[i]), 4),
                    "f1": round(float(f[i]), 4), "support": int(s[i])}
            for i, label in enumerate(labels)
        },
        "confusion_matrix": {"labels": labels, "matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist()},
    }
    if "Critical" in labels:  # priority: missing a serious case is the costly error
        yt, yp = np.array(y_true), np.array(y_pred)
        serious_true, serious_pred = np.isin(yt, ["High", "Critical"]), np.isin(yp, ["High", "Critical"])
        out["critical_recall"] = round(float((yp[yt == "Critical"] == "Critical").mean()), 4)
        out["high_or_critical_recall"] = round(float(serious_pred[serious_true].mean()), 4)
        out["serious_cases_missed"] = int((serious_true & ~serious_pred).sum())
    return out


def mean_sd(values: list[float]) -> dict:
    arr = np.asarray(values, dtype=float)
    return {"mean": round(float(arr.mean()), 4), "sd": round(float(arr.std(ddof=1)) if len(arr) > 1 else 0.0, 4)}
