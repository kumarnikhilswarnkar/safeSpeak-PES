"""Train and evaluate all candidates for the PRIORITY task (Low / Medium / High / Critical).

Priority is a separate prediction task with its own model, calibration and threshold;
it is never derived from the category.

    ml/.venv-ml/Scripts/python -m safespeak_ml.training.train_priority_models   (from ml/)
"""
from safespeak_ml import data
from safespeak_ml.training.experiment import run_task


def run(candidates, log=print) -> dict:
    dev, holdout = data.load_split(data.load_dataset())
    return run_task("priority", dev, holdout, candidates, log)


if __name__ == "__main__":
    from safespeak_ml.models.registry import CANDIDATES

    result = run([c for c in CANDIDATES if c.name != "setfit_classifier"])
    print("selected:", result["selection"]["selected"])
