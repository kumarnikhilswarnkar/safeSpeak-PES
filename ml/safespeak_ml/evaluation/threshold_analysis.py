"""Confidence threshold selection (per task, development data only).

For a threshold t, complaints whose confidence is >= t would be handled automatically;
the rest go to human review. For each t we count automatic, human-review, correct and
incorrect automatic decisions. Rule (config): the lowest t whose automatic decisions are
correct at least THRESHOLD_TARGET of the time with coverage >= THRESHOLD_MIN_COVERAGE.
If no t qualifies, t = 1.0 (everything goes to human review) and that is reported.
"""
import numpy as np

from safespeak_ml import config


def table(confidence: np.ndarray, correct: np.ndarray, thresholds: list[float]) -> list[dict]:
    rows = []
    n = len(confidence)
    for t in thresholds:
        auto = confidence >= t
        n_auto = int(auto.sum())
        n_correct = int((auto & correct).sum())
        rows.append({
            "threshold": round(float(t), 2),
            "automatic": n_auto,
            "human_review": n - n_auto,
            "automatic_rate": round(n_auto / n, 4),
            "correct_automatic": n_correct,
            "incorrect_automatic": n_auto - n_correct,
            "automatic_accuracy": round(n_correct / n_auto, 4) if n_auto else None,
        })
    return rows


def select(confidence: np.ndarray, correct: np.ndarray) -> dict:
    grid = table(confidence, correct, config.THRESHOLD_GRID)
    chosen = next(
        (r for r in grid
         if r["automatic_rate"] >= config.THRESHOLD_MIN_COVERAGE
         and r["automatic_accuracy"] is not None and r["automatic_accuracy"] >= config.THRESHOLD_TARGET),
        None,
    )
    return {
        "threshold": chosen["threshold"] if chosen else 1.0,
        "rule": f"lowest threshold with automatic-decision accuracy >= {config.THRESHOLD_TARGET:.0%} "
                f"and automatic rate >= {config.THRESHOLD_MIN_COVERAGE:.0%} (development out-of-fold, calibrated)",
        "met": chosen is not None,
        "at_threshold": chosen,
        "report_table": table(confidence, correct, sorted(set(config.REPORT_THRESHOLDS) |
                                                          ({chosen["threshold"]} if chosen else set()))),
        "curve": grid,
    }
