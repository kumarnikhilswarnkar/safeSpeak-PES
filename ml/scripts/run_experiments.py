"""Run the complete v3 experiment and write every report and artifact.

    ml/.venv-ml/Scripts/python ml/scripts/run_experiments.py

Steps: verify dataset/split/lexicon/encoder -> read the SetFit gate -> for CATEGORY and
PRIORITY: grouped CV of candidates 0-9, selection, calibration, thresholds, holdout
evaluation -> export artifacts (ml/artifacts/v3) -> reports (ml/reports/v3).
Every number in the reports is computed here; nothing is typed in by hand.
"""
import csv
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from safespeak_ml import config, data  # noqa: E402
from safespeak_ml.features.keyword_features import verify_frozen  # noqa: E402
from safespeak_ml.models.registry import CANDIDATES  # noqa: E402
from safespeak_ml.training import train_category_models, train_priority_models  # noqa: E402
from safespeak_ml.training.export_selected import export, sha256, write_json  # noqa: E402

R = config.REPORTS_DIR
METRICS = ("accuracy", "macro_precision", "macro_recall", "macro_f1", "weighted_f1")


def log(msg: str) -> None:
    print(f"{datetime.now().strftime('%H:%M:%S')} {msg}", flush=True)


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=config.REPO_DIR, capture_output=True, text=True).stdout.strip()
    except OSError:
        return "unknown"


def main() -> int:
    started = time.perf_counter()
    rows = data.load_dataset()
    dev, holdout = data.load_split(rows)
    verify_frozen()
    if not (config.ENCODER_DIR / "model.safetensors").exists():
        print("Encoder missing: run ml/scripts/download_encoder.py first", file=sys.stderr)
        return 1
    pilot_file = R / "setfit_pilot.json"
    pilot = json.loads(pilot_file.read_text(encoding="utf-8")) if pilot_file.exists() else {"status": "NOT EVALUATED", "error": "pilot not run"}
    candidates = [c for c in CANDIDATES if c.name != "setfit_classifier" or pilot.get("passed")]
    log(f"SetFit: {pilot['status']}; running {len(candidates)} candidates per task")

    results = {
        "category": train_category_models.run(candidates, log),
        "priority": train_priority_models.run(candidates, log),
    }

    R.mkdir(parents=True, exist_ok=True)
    (R / "per_class_metrics").mkdir(exist_ok=True)
    (R / "confusion_matrices").mkdir(exist_ok=True)
    dataset_info = data.describe(rows, dev, holdout)
    reproducibility = {
        "command": "ml/.venv-ml/Scripts/python ml/scripts/run_experiments.py",
        "prerequisites": ["ml/scripts/download_encoder.py", "ml/scripts/make_split.py", "ml/scripts/setfit_pilot.py"],
        "git_commit_at_run": git_commit(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": {p: version(p) for p in ("scikit-learn", "numpy", "scipy", "joblib", "torch",
                                             "sentence-transformers", "setfit", "transformers")},
        "seeds": {"global": config.SEED, "cv": config.CV_SEEDS},
        "checksums": {"dataset": config.DATASET_SHA256, "split": sha256(config.SPLIT_FILE),
                      "keyword_lexicon": config.KEYWORD_LEXICON_SHA256, "encoder_lock": sha256(config.ENCODER_LOCK)},
        "encoder": {"repo": config.ENCODER_REPO, "revision": config.ENCODER_REVISION},
        "run_seconds": None,
    }

    comparison, cross_val, holdout_out, calibration_out, thresholds_out, selection_out = {}, {}, {}, {}, {}, {}
    for task, res in results.items():
        comparison[task] = []
        for cls in CANDIDATES:
            name = cls.name
            if name not in res["cv"]:
                comparison[task].append({"number": cls.number, "model": name, "title": cls.title,
                                         "status": "NOT EVALUATED", "reason": pilot.get("error") or "failed the feasibility gate"})
                continue
            cvr, ho = res["cv"][name], res["holdout"][name]
            comparison[task].append({
                "number": cls.number, "model": name, "title": cls.title, "status": "EVALUATED",
                "selectable": name in config.SELECTABLE,
                "cv": {m: cvr["summary"][m] for m in METRICS},
                "holdout": {m: ho[m] for m in METRICS},
                "seconds": cvr["seconds"],
                "selected": name == res["selection"]["selected"],
                "deployable": name in config.DEPLOYABLE,
                "unconstrained_winner": name == res["selection"]["unconstrained"]["selected"],
            })
            labels = res["labels"]
            with open(R / "per_class_metrics" / f"{task}__{name}.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["class", "cv_precision", "cv_recall", "cv_f1", "cv_support", "holdout_precision",
                            "holdout_recall", "holdout_f1", "holdout_support"])
                for lbl in labels:
                    c, h = cvr["pooled_oof"]["per_class"][lbl], ho["per_class"][lbl]
                    w.writerow([lbl, c["precision"], c["recall"], c["f1"], c["support"],
                                h["precision"], h["recall"], h["f1"], h["support"]])
            for split, cm in (("cv", cvr["pooled_oof"]["confusion_matrix"]), ("holdout", ho["confusion_matrix"])):
                with open(R / "confusion_matrices" / f"{task}__{name}__{split}.csv", "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow(["true \\ predicted", *cm["labels"]])
                    for lbl, row in zip(cm["labels"], cm["matrix"]):
                        w.writerow([lbl, *row])
        cross_val[task] = {n: {"summary": r["summary"], "folds": r["folds"], "pooled_oof": r["pooled_oof"],
                               "seconds": r["seconds"]} for n, r in res["cv"].items()}
        holdout_out[task] = {"note": "Reported once after selection; never used to choose a model, threshold or calibration.",
                             "models": res["holdout"], "selected_model_details": res["holdout_selected"]}
        calibration_out[task] = {"selected_model": res["selection"]["selected"], "models": res["calibration"]}
        thresholds_out[task] = {"selected_model": res["selection"]["selected"], **res["thresholds"],
                                "holdout_table": res["holdout_selected"]["threshold_table"]}
        selection_out[task] = res["selection"]

    reproducibility["run_seconds"] = round(time.perf_counter() - started, 1)
    deployed = export(results, dataset_info, reproducibility)

    write_json(R / "model_comparison.json", {"setfit_pilot": pilot, "tasks": comparison})
    write_json(R / "cross_validation.json", cross_val)
    write_json(R / "holdout_results.json", holdout_out)
    write_json(R / "calibration.json", calibration_out)
    write_json(R / "thresholds.json", thresholds_out)
    write_json(R / "selection.json", selection_out)
    write_json(R / "dataset_info.json", dataset_info)
    write_json(R / "reproducibility.json", reproducibility)
    write_markdown(comparison, selection_out, calibration_out, thresholds_out, pilot, dataset_info)
    log(f"done in {reproducibility['run_seconds']} s; deployed: category={deployed['category']['model']} "
        f"priority={deployed['priority']['model']}")
    return 0


def pct(v):
    return "—" if v is None else f"{100 * v:.1f}%"


def write_markdown(comparison, selection, calibration, thresholds, pilot, dataset_info) -> None:
    lines = ["# SafeSpeak triage model comparison (v3)", "",
             "Generated by `ml/scripts/run_experiments.py` - do not edit by hand.", "",
             f"Dataset: {dataset_info['nature']} {dataset_info['records']} records, {dataset_info['groups']} groups; "
             f"development {dataset_info['partitions']['development']['records']}, holdout {dataset_info['partitions']['holdout']['records']}.",
             "", f"SetFit feasibility gate: **{pilot['status']}**" + (f" ({pilot.get('error')})" if pilot.get("error") else ""), "",
             f"**Deployment constraint (disclosed, added after the first full run):** {config.DEPLOYMENT_CONSTRAINT['rule']}. "
             f"Reason: {config.DEPLOYMENT_CONSTRAINT['reason']}. The same selection rule is applied to the deployable pool; "
             "the unconstrained winner is reported for every task.", ""]
    for task, rows in comparison.items():
        lines += [f"## {task.title()}", "",
                  "| # | Model | CV macro-F1 (mean ± SD) | CV accuracy | Holdout accuracy | Holdout macro-P | Holdout macro-R | Holdout macro-F1 | Holdout weighted-F1 |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for r in rows:
            if r["status"] != "EVALUATED":
                lines.append(f"| {r['number']} | {r['title']} | NOT EVALUATED | | | | | | |")
                continue
            mark = (" **(selected, deployed)**" if r["selected"] else "") +                 (" *(unconstrained winner)*" if r.get("unconstrained_winner") and not r["selected"] else "")
            cvf = r["cv"]["macro_f1"]
            lines.append(f"| {r['number']} | {r['title']}{mark} | {cvf['mean']:.3f} ± {cvf['sd']:.3f} | {r['cv']['accuracy']['mean']:.3f} "
                         f"| {pct(r['holdout']['accuracy'])} | {pct(r['holdout']['macro_precision'])} | {pct(r['holdout']['macro_recall'])} "
                         f"| {pct(r['holdout']['macro_f1'])} | {pct(r['holdout']['weighted_f1'])} |")
        s = selection[task]
        kw = s["keyword_baseline_cv_macro_f1"]
        u = s["unconstrained"]
        lines += ["", f"Unconstrained rule winner (all selectable, 2-9): **{u['selected']}** "
                  f"(beats keyword baseline in CV: {'yes' if u['beats_keyword_baseline'] else 'no'})."
                  + (" The deployment constraint changed the selection." if s["constraint_changed_selection"] else
                     " The deployment constraint did not change the selection."),
                  f"Selected: **{s['selected']}**. Beats frozen keyword baseline (CV macro-F1 "
                  f"{kw['mean']:.3f}): **{'yes' if s['beats_keyword_baseline'] else 'no'}**.",
                  f"Calibration: **{calibration[task]['models'][s['selected']]['selected_method']}**; "
                  f"threshold: **{thresholds[task]['threshold']}** ({'rule met' if thresholds[task]['met'] else 'rule NOT met: all to review'}).", ""]
    (R / "model_comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
