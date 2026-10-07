"""Repeated grouped cross-validation on the development set (480 records, 160 groups).

For every repeat (5 seeds) and fold (5), the candidate is trained on 4 folds and
evaluated on the held-out fold; whole paraphrase groups stay together. Outputs:
  - fold-level metrics (25 values per metric -> mean and standard deviation)
  - out-of-fold predictions and scores per repeat (every development record predicted
    once per repeat by a model that never saw it), used for calibration and thresholds.
The holdout set is not touched here.
"""
import time

import numpy as np

from safespeak_ml import config, data
from safespeak_ml.evaluation.metrics import classification_metrics, mean_sd


def run(candidate_cls, task: str, dev: list) -> dict:
    labels = config.LABELS[task]
    texts = [r.text for r in dev]
    y = [getattr(r, task) for r in dev]
    fold_metrics, oof = [], []
    start = time.perf_counter()
    for repeat in range(config.CV_REPEATS):
        predictions = [None] * len(dev)
        scores = np.zeros((len(dev), len(labels))) if candidate_cls.has_scores else None
        fold_ids = np.zeros(len(dev), dtype=int)
        for fold, (train_idx, val_idx) in enumerate(data.cv_folds(dev, repeat)):
            model = candidate_cls(task, seed=config.CV_SEEDS[repeat]).fit(
                [texts[i] for i in train_idx], [y[i] for i in train_idx])
            val_texts = [texts[i] for i in val_idx]
            pred = model.predict(val_texts)
            for i, p in zip(val_idx, pred):
                predictions[i] = p
                fold_ids[i] = fold
            if scores is not None:
                s = model.scores(val_texts)
                order = [model.classes_.index(lbl) for lbl in labels]
                scores[val_idx] = s[:, order]
            m = classification_metrics([y[i] for i in val_idx], pred, labels)
            fold_metrics.append({"repeat": repeat, "fold": fold,
                                 **{k: m[k] for k in ("accuracy", "macro_precision", "macro_recall", "macro_f1", "weighted_f1")}})
        oof.append({
            "predictions": predictions,
            "scores": scores,
            "y_idx": np.array([labels.index(v) for v in y]),
            "fold_ids": fold_ids,
        })
    summary = {k: mean_sd([f[k] for f in fold_metrics])
               for k in ("accuracy", "macro_precision", "macro_recall", "macro_f1", "weighted_f1")}
    pooled = classification_metrics(y * config.CV_REPEATS, [p for r in oof for p in r["predictions"]], labels)
    return {"summary": summary, "folds": fold_metrics, "pooled_oof": pooled, "oof": oof,
            "seconds": round(time.perf_counter() - start, 1)}
