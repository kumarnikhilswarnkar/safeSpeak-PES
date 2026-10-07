"""Phase-2 ML pipeline integrity: dataset checksum, leakage-free holdout and CV folds,
calibration formulas shared with the backend, and the Docker build inputs.

These read only committed files (dataset, split, ml/safespeak_ml); no training.
"""
import re
import sys
from pathlib import Path

import numpy as np
import pytest

from app.core.config import REPO_DIR
from app.services.triage_service import calibrate

sys.path.insert(0, str(REPO_DIR / "ml"))

from safespeak_ml import config, data  # noqa: E402
from safespeak_ml.evaluation import calibration as pipeline_calibration  # noqa: E402

pytestmark = pytest.mark.ml_integrity


@pytest.fixture(scope="module")
def rows():
    return data.load_dataset()


@pytest.fixture(scope="module")
def split(rows):
    return data.load_split(rows)


def test_dataset_checksum_matches_the_pinned_version(rows):
    assert data.sha256(config.DATASET_FILE) == config.DATASET_SHA256
    assert len(rows) == 600 and len({r.group_id for r in rows}) == 200


def test_holdout_is_40_whole_groups(split):
    dev, holdout = split
    assert (len(dev), len(holdout)) == (480, 120)
    assert len({r.group_id for r in holdout}) == 40
    assert not {r.group_id for r in dev} & {r.group_id for r in holdout}
    assert {r.category for r in holdout} == set(config.CATEGORIES)
    assert {r.priority for r in holdout} == set(config.PRIORITIES)


def test_split_file_is_reproducible_from_the_seed(rows, split):
    dev, holdout = split
    recomputed = data.make_holdout(rows)
    assert {r.id for r in holdout} == {i for i, p in recomputed.items() if p == "holdout"}


@pytest.mark.parametrize("repeat", range(config.CV_REPEATS))
def test_cv_folds_never_split_a_paraphrase_group(split, repeat):
    dev, holdout = split
    holdout_ids = {r.id for r in holdout}
    folds = data.cv_folds(dev, repeat)
    assert len(folds) == config.CV_FOLDS
    seen = []
    for train_idx, val_idx in folds:
        assert not {dev[i].group_id for i in train_idx} & {dev[i].group_id for i in val_idx}
        assert not {dev[i].id for i in val_idx} & holdout_ids
        seen.extend(val_idx)
    assert sorted(seen) == list(range(len(dev)))  # every development record validated exactly once


@pytest.mark.parametrize("method,params", [
    ("raw", {}),
    ("temperature", {"temperature": 1.7}),
    ("sigmoid", {"a": [1.2, 0.8, 1.0, 0.5], "b": [-0.1, 0.2, 0.0, 0.3]}),
])
def test_backend_calibration_equals_pipeline_calibration(method, params):
    scores = np.random.default_rng(0).normal(size=(6, 4))
    np.testing.assert_allclose(calibrate(method, params, scores), pipeline_calibration.apply(method, params, scores), atol=1e-12)


def test_docker_image_ships_the_configured_model_version():
    dockerfile = (REPO_DIR / "backend" / "Dockerfile").read_text(encoding="utf-8")
    default = re.search(r"ARG MODEL_VERSION=(\S+)", dockerfile).group(1)
    assert default == config.ARTIFACT_VERSION
    assert "COPY ml/artifacts/${MODEL_VERSION}" in dockerfile
    # Each ENV entry on its own continuation line (the backend reads MODEL_DIR and REPORTS_DIR).
    assert re.search(r"^\s+MODEL_DIR=/app/ml/artifacts/\$\{MODEL_VERSION\} \\$", dockerfile, re.M)
    assert re.search(r"^\s+REPORTS_DIR=/app/ml/reports/\$\{MODEL_VERSION\}$", dockerfile, re.M)
    compose = (REPO_DIR / "docker-compose.yml").read_text(encoding="utf-8")
    assert f"${{MODEL_VERSION:-{config.ARTIFACT_VERSION}}}" in compose
    # The deployed artifact must not be excluded from the build context.
    ignored = (REPO_DIR / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert "ml/artifacts" not in ignored and f"ml/artifacts/{config.ARTIFACT_VERSION}" not in ignored
