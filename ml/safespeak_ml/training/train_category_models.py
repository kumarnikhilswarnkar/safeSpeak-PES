"""Train and evaluate all candidates for the CATEGORY task (8 SafeSpeak categories).

    ml/.venv-ml/Scripts/python -m safespeak_ml.training.train_category_models   (from ml/)
Usually run through ml/scripts/run_experiments.py, which runs both tasks and exports.
"""
from safespeak_ml import data
from safespeak_ml.training.experiment import run_task


def run(candidates, log=print) -> dict:
    dev, holdout = data.load_split(data.load_dataset())
    return run_task("category", dev, holdout, candidates, log)


if __name__ == "__main__":
    from safespeak_ml.models.registry import CANDIDATES

    result = run([c for c in CANDIDATES if c.name != "setfit_classifier"])
    print("selected:", result["selection"]["selected"])
