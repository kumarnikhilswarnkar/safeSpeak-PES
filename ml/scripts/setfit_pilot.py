"""SetFit feasibility gate (decided before SetFit is evaluated).

    ml/.venv-ml/Scripts/python ml/scripts/setfit_pilot.py

Fits candidate 9 on ONE development CV fold (repeat 0, fold 0, category task) through
the same fold code every candidate uses. SetFit is evaluated only if:
  (a) one fit finishes within config.SETFIT_MAX_SECONDS_PER_FIT seconds,
  (b) a second fit with the same seed gives identical validation predictions,
  (c) it runs inside the standard grouped-CV code without special data handling.
Each fit runs in a child process that is stopped when the time limit is reached, so a
slow machine fails the gate after 10 minutes instead of running for hours; the measured
training speed is recorded. Result: ml/reports/v3/setfit_pilot.json -> EVALUATED or NOT EVALUATED.
"""
import json
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from safespeak_ml import config, data  # noqa: E402

LOG = config.ML_DIR / ".cache" / "setfit_pilot_child.log"
PROGRESS = re.compile(r"(\d+)/(\d+) \[(\d+):(\d+)(?::(\d+))?<")


def child(out_path: str) -> int:
    """Run one fit on the pilot fold and write predictions/scores to out_path."""
    from safespeak_ml.models.setfit_classifier import SetFitClassifier

    dev, _ = data.load_split(data.load_dataset())
    train_idx, val_idx = data.cv_folds(dev, 0)[0]
    train, val = [dev[i] for i in train_idx], [dev[i] for i in val_idx]
    start = time.perf_counter()
    model = SetFitClassifier("category", seed=config.CV_SEEDS[0]).fit([r.text for r in train], [r.category for r in train])
    seconds = time.perf_counter() - start
    texts = [r.text for r in val]
    Path(out_path).write_text(json.dumps({
        "seconds": round(seconds, 1), "train_records": len(train), "validation_records": len(val),
        "predictions": model.predict(texts), "scores": model.scores(texts).round(6).tolist(),
        "accuracy": sum(p == r.category for p, r in zip(model.predict(texts), val)) / len(val),
    }), encoding="utf-8")
    return 0


def run_fit(attempt: int) -> dict:
    out = config.ML_DIR / ".cache" / f"setfit_pilot_fit{attempt}.json"
    out.unlink(missing_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    limit = config.SETFIT_MAX_SECONDS_PER_FIT
    started = time.perf_counter()
    with open(LOG, "w", encoding="utf-8") as log:
        proc = subprocess.Popen([sys.executable, __file__, "--child", str(out)], stdout=log, stderr=subprocess.STDOUT)
        try:
            proc.wait(timeout=limit + 120)  # + model-loading margin; the fit itself is timed in the child
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    wall = time.perf_counter() - started
    if out.exists():
        return {"finished": True, "wall_seconds": round(wall, 1), **json.loads(out.read_text(encoding="utf-8"))}
    text = LOG.read_text(encoding="utf-8", errors="replace").replace("\r", "\n")
    steps = PROGRESS.findall(text)
    progress = None
    if steps:
        done, total = int(steps[-1][0]), int(steps[-1][1])
        progress = {"steps_done": done, "steps_total": total,
                    "projected_fit_seconds": round(wall / max(done, 1) * total) if done else None}
    return {"finished": False, "wall_seconds": round(wall, 1), "stopped_at_limit": True, "progress": progress,
            "log_tail": [line for line in text.splitlines() if line.strip()][-3:]}


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--child":
        return child(sys.argv[2])
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    result = {"candidate": "setfit_classifier", "settings": config.SETFIT,
              "max_seconds_per_fit": config.SETFIT_MAX_SECONDS_PER_FIT,
              "fold": "development repeat 0 / fold 0 (category)",
              "machine": {"platform": platform.platform(), "processor": platform.processor()},
              "gate_c_standard_cv_code": True}
    first = run_fit(1)
    result["fit_1"] = {k: v for k, v in first.items() if k not in ("predictions", "scores")}
    fast = first["finished"] and first["seconds"] <= config.SETFIT_MAX_SECONDS_PER_FIT
    result["gate_a_time"] = fast
    reproducible = False
    if fast:
        second = run_fit(2)
        result["fit_2"] = {k: v for k, v in second.items() if k not in ("predictions", "scores")}
        reproducible = second["finished"] and second["predictions"] == first["predictions"]
    result["gate_b_reproducible"] = reproducible if fast else "not checked (gate a failed)"
    result["passed"] = bool(fast and reproducible)
    result["status"] = "EVALUATED" if result["passed"] else "NOT EVALUATED"
    if not fast:
        p = first.get("progress") or {}
        result["error"] = (f"one fit exceeded the {config.SETFIT_MAX_SECONDS_PER_FIT} s limit on this machine"
                           + (f" ({p['steps_done']}/{p['steps_total']} training steps after {first['wall_seconds']} s; "
                              f"projected {p['projected_fit_seconds']} s per fit)" if p.get("steps_done") else ""))
    (config.REPORTS_DIR / "setfit_pilot.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
