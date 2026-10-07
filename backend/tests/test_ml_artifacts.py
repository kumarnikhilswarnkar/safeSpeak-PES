"""ML/data integrity for the deployed v3 models (ml/artifacts/v3/deployed.json).

Run on every CI build (no training): the deployed models are exactly the evaluated
ones (file checksums), metadata is complete, the dataset checksum matches, the
thresholds load, and the backend's own loader reproduces the predictions the
pipeline computed when it exported the models.
"""
import hashlib
import json
from pathlib import Path

import pytest

from app.core.config import REPO_DIR, Settings
from app.core.taxonomy import CATEGORIES, PRIORITIES
from app.services.triage_service import effective_priority_threshold, effective_threshold, load_triage_model

pytestmark = pytest.mark.ml_integrity

TASKS = {"category": CATEGORIES, "priority": PRIORITIES}
REQUIRED_METADATA = (
    "model_name", "model_version", "kind", "task", "classes", "dataset", "description", "seed",
    "cv", "holdout", "threshold", "calibration", "training_date", "artifact_files",
)
REQUIRED_FILES = ("metadata.json", "calibration.json", "thresholds.json", "selection.json",
                  "dataset_info.json", "reproducibility.json", "classifier.joblib")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def settings() -> Settings:
    return Settings(_env_file=None, jwt_secret_key="x" * 40)


@pytest.fixture(scope="module")
def model_dir(settings) -> Path:
    return Path(settings.model_dir).resolve()


@pytest.fixture(scope="module")
def deployed(model_dir) -> dict:
    return json.loads((model_dir / "deployed.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def model(settings):
    return load_triage_model(settings)


def test_backend_is_configured_for_v3(model_dir, deployed):
    assert model_dir.name == "v3" and deployed["version"] == "v3"


@pytest.mark.parametrize("task", TASKS)
def test_deployed_files_match_checksums(model_dir, deployed, task):
    entry = deployed[task]
    assert set(REQUIRED_FILES) <= set(entry["files"])
    for filename, expected in entry["files"].items():
        assert sha256(model_dir / entry["path"] / filename) == expected, filename


@pytest.mark.parametrize("task", TASKS)
def test_deployed_model_is_the_evaluated_and_selected_model(model_dir, deployed, task):
    entry = deployed[task]
    directory = model_dir / entry["path"]
    selection = json.loads((directory / "selection.json").read_text(encoding="utf-8"))
    report = json.loads((REPO_DIR / "ml" / "reports" / "v3" / "selection.json").read_text(encoding="utf-8"))
    assert entry["model"] == selection["selected"] == report[task]["selected"]
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    for filename, expected in metadata["artifact_files"].items():
        assert sha256(directory / filename) == expected, filename


@pytest.mark.parametrize("task", TASKS)
def test_metadata_is_complete(model_dir, deployed, task):
    metadata = json.loads((model_dir / deployed[task]["path"] / "metadata.json").read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED_METADATA if k not in metadata]
    assert not missing, missing
    assert metadata["task"] == task and tuple(metadata["classes"]) == TASKS[task]
    assert metadata["model_name"] == deployed[task]["model"]
    assert {"mean", "sd"} <= set(metadata["cv"]["macro_f1"])


@pytest.mark.parametrize("task", TASKS)
def test_training_dataset_matches_recorded_checksum(model_dir, deployed, task):
    metadata = json.loads((model_dir / deployed[task]["path"] / "metadata.json").read_text(encoding="utf-8"))
    assert sha256(REPO_DIR / "ml" / "data" / "SafeSpeak_dataset_split_600.csv") == metadata["dataset"]["sha256"]
    assert deployed["dataset"]["sha256"] == metadata["dataset"]["sha256"]


@pytest.mark.parametrize("task", TASKS)
def test_thresholds_load_per_task(model_dir, deployed, model, task):
    thresholds = json.loads((model_dir / deployed[task]["path"] / "thresholds.json").read_text(encoding="utf-8"))
    assert 0 < thresholds["threshold"] <= 1 and thresholds["task"] == task
    assert thresholds["threshold"] == deployed[task]["threshold"]
    loaded = model.recommended_threshold if task == "category" else model.recommended_priority_threshold
    assert loaded == thresholds["threshold"]


def test_effective_thresholds_come_from_the_model_when_not_configured(settings, model):
    assert effective_threshold(settings, model) == (model.recommended_threshold, "MODEL_METADATA:v3")
    assert effective_priority_threshold(settings, model) == (model.recommended_priority_threshold, "MODEL_METADATA:v3")


def test_backend_reproduces_pipeline_predictions(deployed, model):
    """Same text -> same labels and probabilities as the pipeline computed at export."""
    assert len(deployed["probe_predictions"]) >= 5
    for probe in deployed["probe_predictions"]:
        result = model.predict(probe["text"])
        for task in TASKS:
            assert getattr(result, task) == probe[task]["label"], (task, probe["text"])
            for label, p in probe[task]["probabilities"].items():
                assert result.probabilities[task][label] == pytest.approx(p, abs=1e-4)


def test_backend_records_the_deployed_model_name_and_version(deployed, model):
    result = model.predict("The projector in classroom 052 has not been working for two weeks.")
    assert result.model_name == f"{deployed['category']['model']}+{deployed['priority']['model']}"
    assert result.model_version == "v3"
    assert result.category in CATEGORIES and result.priority in PRIORITIES
    assert abs(sum(result.probabilities["category"].values()) - 1) < 0.01
    assert abs(sum(result.probabilities["priority"].values()) - 1) < 0.01
