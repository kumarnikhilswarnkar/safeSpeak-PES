"""Export the trained models as inspectable, checksummed artifacts.

Every evaluated candidate (refitted on the 480 development records) is saved under
ml/artifacts/v3/<task>/<model>/ so it can be inspected or re-evaluated. The SELECTED
model of each task additionally gets calibration.json, thresholds.json, metadata.json,
selection.json, dataset_info.json and reproducibility.json, and is listed in
ml/artifacts/v3/deployed.json - the only file the backend reads to find its model.
The deployed model is exactly the evaluated one (same object, same checksums).
"""
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from safespeak_ml import config

PROBE_TEXTS = [
    "The projector in classroom 052 has not been working for two weeks.",
    "There is some issue, please check.",
    "Fee receipt for the second semester has not been issued even after payment two weeks ago.",
    "Someone has been following me near the hostel gate at night and I feel unsafe.",
    "The library closes too early during exam week.",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def file_checksums(directory: Path) -> dict[str, str]:
    return {p.relative_to(directory).as_posix(): sha256(p) for p in sorted(directory.rglob("*")) if p.is_file()}


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")


def export(results: dict, dataset_info: dict, reproducibility: dict) -> dict:
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    root = config.ARTIFACTS_DIR
    for task, res in results.items():
        task_dir = root / task
        if task_dir.exists():
            shutil.rmtree(task_dir)
        for name, model in res["fitted"].items():
            if model.has_scores:
                model.save(task_dir / name)

    deployed = {
        "name": "safespeak-triage",
        "version": config.ARTIFACT_VERSION,
        "created": created,
        "dataset": {"version": config.DATASET_VERSION, "sha256": config.DATASET_SHA256},
        "note": "The backend loads exactly these two models; nothing else.",
    }
    for task, res in results.items():
        selected = res["selection"]["selected"]
        model = res["fitted"][selected]
        directory = root / task / selected
        calib = res["calibration"][selected]
        cv_summary = res["cv"][selected]["summary"]
        holdout = res["holdout"][selected]
        write_json(directory / "calibration.json", {
            "task": task, "classes": res["labels"], "method": calib["selected_method"], "params": calib["params"],
            "comparison_cross_fitted": calib["methods"], "improves_over_raw": calib["improves_over_raw"],
            "rule": calib["rule"],
            "formula": {"raw": "softmax(s)", "temperature": "softmax(s / T)",
                        "sigmoid": "p_k = sigmoid(a_k*s_k + b_k); p /= sum(p)"},
        })
        write_json(directory / "thresholds.json", {
            "task": task, "threshold": res["thresholds"]["threshold"], "rule": res["thresholds"]["rule"],
            "target_automatic_accuracy": config.THRESHOLD_TARGET, "min_automatic_rate": config.THRESHOLD_MIN_COVERAGE,
            "met": res["thresholds"]["met"], "at_threshold_development": res["thresholds"]["at_threshold"],
            "calibration_method": res["thresholds"]["calibration_method"],
        })
        write_json(directory / "selection.json", res["selection"])
        write_json(directory / "dataset_info.json", dataset_info)
        write_json(directory / "reproducibility.json", reproducibility)
        metadata = {
            "model_name": selected,
            "model_title": model.title,
            "model_version": config.ARTIFACT_VERSION,
            "kind": model.kind,
            "task": task,
            "classes": res["labels"],
            "dataset": {"version": config.DATASET_VERSION, "sha256": config.DATASET_SHA256,
                        "trained_on": "development partition (480 records, 160 groups)"},
            "description": model.describe(),
            "seed": config.SEED,
            "cv": {"design": f"{config.CV_REPEATS} x {config.CV_FOLDS}-fold StratifiedGroupKFold", **cv_summary},
            "holdout": {k: holdout[k] for k in ("n", "accuracy", "macro_precision", "macro_recall", "macro_f1", "weighted_f1")},
            "threshold": res["thresholds"]["threshold"],
            "calibration": {"method": calib["selected_method"], "params": calib["params"]},
            "keyword_lexicon_sha256": config.KEYWORD_LEXICON_SHA256 if selected == "hybrid_classifier" else None,
            "training_date": created,
            "explanation": ("top contributing words (feature value x class weight)" if model.kind == "linear-text"
                            else "most similar training complaints (no word-level explanation)"),
        }
        metadata["artifact_files"] = {f: sha256(directory / f) for f in sorted(file_checksums(directory))
                                      if f != "metadata.json"}
        write_json(directory / "metadata.json", metadata)
        deployed[task] = {
            "model": selected,
            "kind": model.kind,
            "path": f"{task}/{selected}",
            "threshold": res["thresholds"]["threshold"],
            "calibration": calib["selected_method"],
            "files": file_checksums(directory),
        }

    # Probe predictions computed by the pipeline; the backend must reproduce them exactly.
    probes = []
    for text in PROBE_TEXTS:
        entry = {"text": text}
        for task, res in results.items():
            model = res["fitted"][res["selection"]["selected"]]
            calib = res["calibration"][res["selection"]["selected"]]
            from safespeak_ml.evaluation.calibration import apply
            s = model.scores([text])[:, [model.classes_.index(lbl) for lbl in res["labels"]]]
            p = apply(calib["selected_method"], calib["params"], s)[0]
            entry[task] = {"label": res["labels"][int(np.argmax(p))], "confidence": round(float(p.max()), 6),
                           "probabilities": {lbl: round(float(v), 6) for lbl, v in zip(res["labels"], p)}}
        probes.append(entry)
    deployed["probe_predictions"] = probes
    write_json(root / "deployed.json", deployed)
    return deployed
