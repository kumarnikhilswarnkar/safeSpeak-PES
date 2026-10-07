"""Turning model scores into calibrated probabilities ("confidence").

Methods compared (on out-of-fold development scores only):
    raw          softmax(scores)                     - Logistic Regression's own probabilities
    temperature  softmax(scores / T), one number T   - softens (T > 1) or sharpens (T < 1)
    sigmoid      Platt scaling per class: sigmoid(a_k * s_k + b_k), then normalised to sum 1

Evaluation is CROSS-FITTED: for each CV fold, the calibrator is fitted on the other
folds' out-of-fold scores and applied to that fold, so no score is calibrated with a
calibrator that saw it. The method with the lowest cross-fitted log loss (NLL) is
chosen; if no method beats raw, raw is kept (calibration is never forced).
Reported: NLL, ECE (expected calibration error: gap between confidence and accuracy)
and the multi-class Brier score. The backend applies the stored parameters with the
same formulas (backend/app/services/triage_service.py).
"""
import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import expit, log_softmax, softmax
from sklearn.linear_model import LogisticRegression

from safespeak_ml import config


def fit(method: str, scores: np.ndarray, y_idx: np.ndarray) -> dict:
    if method == "raw":
        return {}
    if method == "temperature":
        def nll(t):
            return -log_softmax(scores / t, axis=1)[np.arange(len(y_idx)), y_idx].mean()
        return {"temperature": round(float(minimize_scalar(nll, bounds=(0.05, 20), method="bounded").x), 6)}
    if method == "sigmoid":
        a, b = [], []
        for k in range(scores.shape[1]):
            target = (y_idx == k).astype(int)
            if target.min() == target.max():  # class absent: identity-like mapping
                a.append(1.0), b.append(0.0)
                continue
            lr = LogisticRegression(C=1e6, max_iter=1000).fit(scores[:, [k]], target)
            a.append(float(lr.coef_[0, 0])), b.append(float(lr.intercept_[0]))
        return {"a": [round(v, 6) for v in a], "b": [round(v, 6) for v in b]}
    raise ValueError(method)


def apply(method: str, params: dict, scores: np.ndarray) -> np.ndarray:
    if method == "raw":
        return softmax(scores, axis=1)
    if method == "temperature":
        return softmax(scores / params["temperature"], axis=1)
    if method == "sigmoid":
        p = expit(scores * np.asarray(params["a"]) + np.asarray(params["b"]))
        return p / p.sum(axis=1, keepdims=True)
    raise ValueError(method)


def ece(probs: np.ndarray, y_idx: np.ndarray, bins: int = config.ECE_BINS) -> float:
    conf = probs.max(axis=1)
    correct = probs.argmax(axis=1) == y_idx
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (conf > lo) & (conf <= hi)
        if mask.any():
            total += mask.mean() * abs(correct[mask].mean() - conf[mask].mean())
    return float(total)


def nll(probs: np.ndarray, y_idx: np.ndarray) -> float:
    return float(-np.log(np.clip(probs[np.arange(len(y_idx)), y_idx], 1e-12, 1)).mean())


def brier(probs: np.ndarray, y_idx: np.ndarray) -> float:
    onehot = np.eye(probs.shape[1])[y_idx]
    return float(((probs - onehot) ** 2).sum(axis=1).mean())


def quality(probs: np.ndarray, y_idx: np.ndarray) -> dict:
    return {"nll": round(nll(probs, y_idx), 4), "ece": round(ece(probs, y_idx), 4), "brier": round(brier(probs, y_idx), 4),
            "mean_confidence": round(float(probs.max(axis=1).mean()), 4),
            "accuracy": round(float((probs.argmax(axis=1) == y_idx).mean()), 4)}


def crossfit(method: str, scores: np.ndarray, y_idx: np.ndarray, fold_ids: np.ndarray) -> np.ndarray:
    """Calibrated probabilities where each fold is calibrated by a calibrator fitted on the other folds."""
    out = np.zeros_like(scores, dtype=float)
    for f in np.unique(fold_ids):
        held = fold_ids == f
        params = fit(method, scores[~held], y_idx[~held])
        out[held] = apply(method, params, scores[held])
    return out


def compare(oof: list[dict], classes: list[str]) -> dict:
    """oof: one entry per CV repeat with 'scores', 'y_idx', 'fold_ids'. Returns per-method quality
    (cross-fitted, pooled over repeats), the chosen method and its final parameters."""
    results = {}
    for method in config.CALIBRATION_METHODS:
        probs = np.vstack([crossfit(method, r["scores"], r["y_idx"], r["fold_ids"]) for r in oof])
        y = np.concatenate([r["y_idx"] for r in oof])
        results[method] = quality(probs, y)
    best = min(results, key=lambda m: results[m]["nll"])
    if results[best]["nll"] >= results["raw"]["nll"]:
        best = "raw"
    all_scores = np.vstack([r["scores"] for r in oof])
    all_y = np.concatenate([r["y_idx"] for r in oof])
    return {
        "classes": classes,
        "methods": results,
        "selected_method": best,
        "improves_over_raw": best != "raw",
        "rule": "lowest cross-fitted log loss on development out-of-fold scores; raw kept if nothing improves",
        "params": fit(best, all_scores, all_y),
    }
