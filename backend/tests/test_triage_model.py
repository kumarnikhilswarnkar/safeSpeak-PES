"""The real trained model artifact and the threshold rules."""
import json
import shutil

import pytest

from app.core.config import Settings
from app.core.taxonomy import CATEGORIES, PRIORITIES
from app.services.triage_service import (
    SklearnTriageModel,
    TriageModelError,
    TriageResult,
    effective_threshold,
    load_triage_model,
    review_reasons,
)


@pytest.fixture
def real_model(settings: Settings) -> SklearnTriageModel:
    return load_triage_model(settings)


def test_real_model_predicts_valid_labels_and_confidences(real_model):
    result = real_model.predict("The hostel mess food has been cold for a week and nobody is responding.")

    assert result.category in CATEGORIES
    assert result.priority in PRIORITIES
    assert 0 < result.category_confidence <= 1
    assert 0 < result.priority_confidence <= 1
    assert result.confidence == min(result.category_confidence, result.priority_confidence)
    assert set(result.probabilities["category"]) == set(CATEGORIES)


def test_real_model_records_validation_threshold(real_model):
    assert 0 < real_model.recommended_threshold <= 1


def test_tampered_model_file_is_refused(settings, tmp_path):
    copy = tmp_path / "model"
    shutil.copytree(settings.model_dir, copy)
    with (copy / "priority.joblib").open("ab") as f:
        f.write(b"tampered")

    with pytest.raises(TriageModelError):
        SklearnTriageModel(copy)


def test_label_mismatch_is_refused(settings, tmp_path):
    copy = tmp_path / "model"
    shutil.copytree(settings.model_dir, copy)
    metadata = json.loads((copy / "metadata.json").read_text())
    metadata["labels"]["category"] = metadata["labels"]["category"][:-1]
    (copy / "metadata.json").write_text(json.dumps(metadata))

    with pytest.raises(TriageModelError):
        SklearnTriageModel(copy)


def test_configured_threshold_wins_over_model_metadata(settings, real_model):
    assert effective_threshold(settings, real_model) == (0.5, "CONFIG")
    unset = settings.model_copy(update={"confidence_threshold": None})
    value, source = effective_threshold(unset, real_model)
    assert value == real_model.recommended_threshold
    assert source == f"MODEL_METADATA:{real_model.version}"


def _result(cat_conf, pri_conf, priority="Medium"):
    return TriageResult("m", "v", "Hostel", cat_conf, priority, pri_conf)


@pytest.mark.parametrize(
    ("cat_conf", "pri_conf", "priority", "expected"),
    [
        (0.5, 0.5, "Medium", []),  # exactly at the threshold is not low
        (0.49, 0.9, "Medium", ["LOW_CATEGORY_CONFIDENCE"]),
        (0.9, 0.49, "Low", ["LOW_PRIORITY_CONFIDENCE"]),
        (0.9, 0.9, "Critical", ["HIGH_SEVERITY"]),
        (0.1, 0.1, "High", ["LOW_CATEGORY_CONFIDENCE", "LOW_PRIORITY_CONFIDENCE", "HIGH_SEVERITY"]),
    ],
)
def test_review_reasons(settings, cat_conf, pri_conf, priority, expected):
    assert review_reasons(_result(cat_conf, pri_conf, priority), 0.5, settings) == expected


def test_high_severity_rule_can_be_disabled(settings):
    relaxed = settings.model_copy(update={"review_high_severity": False})
    assert review_reasons(_result(0.9, 0.9, "Critical"), 0.5, relaxed) == []


def test_demo_mode_cannot_be_enabled_in_production():
    with pytest.raises(ValueError):
        Settings(_env_file=None, environment="production", demo_mode=True, jwt_secret_key="z" * 40)
