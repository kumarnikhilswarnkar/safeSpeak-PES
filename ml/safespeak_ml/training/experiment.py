"""The experiment for ONE task (category or priority), in this order:

1. grouped CV of every candidate on the development set
2. model selection with the pre-declared rule (CV results only), applied to all
   selectable candidates (reported) and to the deployable pool (config.DEPLOYABLE,
   a disclosed constraint added after the first run) - the latter is deployed
3. calibration comparison (cross-fitted, development out-of-fold scores)
4. threshold selection for the selected model (calibrated out-of-fold confidences)
5. every candidate refitted on the whole development set and evaluated ONCE on the
   holdout - reported only, never used for any choice above
"""
import numpy as np

from safespeak_ml import config
from safespeak_ml.evaluation import calibration, compare_models, cross_validation, threshold_analysis
from safespeak_ml.evaluation.metrics import classification_metrics


def run_task(task: str, dev: list, holdout: list, candidates: list, log=print) -> dict:
    labels = config.LABELS[task]
    cv, fitted = {}, {}
    for cls in candidates:
        log(f"[{task}] CV {cls.number} {cls.name} ...")
        cv[cls.name] = cross_validation.run(cls, task, dev)
        s = cv[cls.name]["summary"]["macro_f1"]
        log(f"[{task}]    macro-F1 {s['mean']:.3f} ± {s['sd']:.3f}  ({cv[cls.name]['seconds']} s)")

    unconstrained = compare_models.select(cv)
    selection = compare_models.select(cv, config.DEPLOYABLE)
    selection["deployment_constraint"] = config.DEPLOYMENT_CONSTRAINT
    selection["unconstrained"] = {k: unconstrained[k] for k in ("selected", "pool", "trace", "winner_cv_macro_f1",
                                                                 "beats_keyword_baseline", "margin_over_keyword_in_sd")}
    selection["constraint_changed_selection"] = unconstrained["selected"] != selection["selected"]
    selected = selection["selected"]
    log(f"[{task}] unconstrained winner: {unconstrained['selected']}")
    log(f"[{task}] selected: {selected}")

    calib = {name: calibration.compare(r["oof"], labels) for name, r in cv.items() if r["oof"][0]["scores"] is not None}
    chosen = calib[selected]
    probs = np.vstack([calibration.crossfit(chosen["selected_method"], r["scores"], r["y_idx"], r["fold_ids"])
                       for r in cv[selected]["oof"]])
    y_all = np.concatenate([r["y_idx"] for r in cv[selected]["oof"]])
    thresholds = threshold_analysis.select(probs.max(axis=1), probs.argmax(axis=1) == y_all)
    thresholds["calibration_method"] = chosen["selected_method"]

    holdout_texts = [r.text for r in holdout]
    holdout_y = [getattr(r, task) for r in holdout]
    holdout_results = {}
    for cls in candidates:
        model = cls(task).fit([r.text for r in dev], [getattr(r, task) for r in dev])
        fitted[cls.name] = model
        holdout_results[cls.name] = classification_metrics(holdout_y, model.predict(holdout_texts), labels)

    # Selected model on the holdout: calibration and threshold behaviour (reporting only).
    model = fitted[selected]
    s = model.scores(holdout_texts)[:, [model.classes_.index(lbl) for lbl in labels]]
    y_idx = np.array([labels.index(v) for v in holdout_y])
    raw = calibration.apply("raw", {}, s)
    cal = calibration.apply(chosen["selected_method"], chosen["params"], s)
    holdout_selected = {
        "calibration": {"raw": calibration.quality(raw, y_idx), chosen["selected_method"]: calibration.quality(cal, y_idx)},
        "threshold_table": threshold_analysis.table(cal.max(axis=1), cal.argmax(axis=1) == y_idx,
                                                    sorted(set(config.REPORT_THRESHOLDS) | {thresholds["threshold"]})),
    }
    return {
        "task": task,
        "labels": labels,
        "cv": cv,
        "selection": selection,
        "calibration": calib,
        "thresholds": thresholds,
        "holdout": holdout_results,
        "holdout_selected": holdout_selected,
        "fitted": fitted,
    }
