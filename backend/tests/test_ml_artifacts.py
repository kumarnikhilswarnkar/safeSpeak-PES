"""ML/data integrity for the model the backend is configured to load.

Run on every CI build (no training): the training dataset matches the checksum
recorded with the model, every model file matches its recorded checksum, the
metadata is complete, the backend can load the model, and inference returns
valid labels and confidences. Phase 2 adds checks for ml/artifacts/<v>/deployed.json.
"""
import hashlib
import json
from pathlib import Path

import pytest

from app.core.config import REPO_DIR, Settings
from app.core.taxonomy import CATEGORIES, PRIORITIES
from app.services.triage_service import load_triage_model

pytestmark = pytest.mark.ml_integrity

REQUIRED_METADATA = ("model_name", "model_version", "sklearn_version", "dataset", "labels", "confidence", "files")


@pytest.fixture(scope="module")
def model_dir() -> Path:
    return Path(Settings(_env_file=None, jwt_secret_key="x" * 40).model_dir).resolve()


@pytest.fixture(scope="module")
def metadata(model_dir) -> dict:
    return json.loads((model_dir / "metadata.json").read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_metadata_is_complete(metadata):
    missing = [k for k in REQUIRED_METADATA if k not in metadata]
    assert not missing, missing
    assert tuple(metadata["labels"]["category"]) == CATEGORIES
    assert tuple(metadata["labels"]["priority"]) == PRIORITIES
    threshold = metadata["confidence"].get("recommended_threshold")
    assert threshold is None or 0 < threshold <= 1


def test_model_files_match_recorded_checksums(model_dir, metadata):
    assert metadata["files"], "no model files recorded"
    for filename, expected in metadata["files"].items():
        assert sha256(model_dir / filename) == expected, filename


def test_training_dataset_matches_recorded_checksum(metadata):
    dataset = REPO_DIR / "ml" / "data" / metadata["dataset"]["file"]
    assert dataset.exists(), dataset
    assert sha256(dataset) == metadata["dataset"]["sha256"]


def test_backend_loads_model_and_inference_is_valid(model_dir):
    settings = Settings(_env_file=None, jwt_secret_key="x" * 40, model_dir=model_dir)
    model = load_triage_model(settings)
    for text in (
        "The projector in classroom 052 has not been working for two weeks.",
        "There is some issue, please check.",
    ):
        result = model.predict(text)
        assert result.category in CATEGORIES and result.priority in PRIORITIES
        assert 0 < result.category_confidence <= 1 and 0 < result.priority_confidence <= 1
        assert abs(sum(result.probabilities["category"].values()) - 1) < 0.01
