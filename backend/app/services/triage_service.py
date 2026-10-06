"""AI triage: category, priority and confidence for a complaint text.

The application depends only on the TriageModel protocol, so the TF-IDF model
can later be replaced (for example by a semantic model) without touching the
workflow. Models are produced by ml/train_triage.py.
"""
import hashlib
import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import joblib
import numpy as np
import sklearn
from scipy.sparse import csr_matrix
from scipy.special import softmax

from app.core.config import Settings
from app.core.taxonomy import CATEGORIES, HIGH_SEVERITY_PRIORITIES, PRIORITIES
from app.services.keyword_features import keyword_category, keyword_priority

logger = logging.getLogger("safespeak.triage")

LOW_CATEGORY_CONFIDENCE = "LOW_CATEGORY_CONFIDENCE"
LOW_PRIORITY_CONFIDENCE = "LOW_PRIORITY_CONFIDENCE"
HIGH_SEVERITY = "HIGH_SEVERITY"


class TriageModelError(RuntimeError):
    pass


@dataclass(frozen=True)
class TriageResult:
    model_name: str
    model_version: str
    category: str
    category_confidence: float
    priority: str
    priority_confidence: float
    probabilities: dict[str, dict[str, float]] = field(default_factory=dict)
    # Evidence for the reviewer: contributing words per task and what the
    # keyword baseline would have said. Empty when the model cannot provide it.
    explanation: dict = field(default_factory=dict)

    @property
    def confidence(self) -> float:
        """Overall confidence: the weaker of the two predictions."""
        return min(self.category_confidence, self.priority_confidence)


class TriageModel(Protocol):
    name: str
    version: str
    recommended_threshold: float | None

    def predict(self, text: str) -> TriageResult: ...


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SklearnTriageModel:
    """TF-IDF + Logistic Regression pipelines saved by ml/train_triage.py."""

    def __init__(self, model_dir: Path):
        metadata_path = model_dir / "metadata.json"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise TriageModelError(f"Cannot read model metadata at {metadata_path}") from exc

        # Only load files whose checksums match the training run's record:
        # joblib files can execute code, so a swapped file must be refused.
        for filename, expected in metadata.get("files", {}).items():
            path = model_dir / filename
            if not path.exists() or _sha256(path) != expected:
                raise TriageModelError(f"Model file {filename} is missing or does not match metadata.json")

        labels = metadata.get("labels", {})
        if tuple(labels.get("category", ())) != CATEGORIES or tuple(labels.get("priority", ())) != PRIORITIES:
            raise TriageModelError("Model labels do not match the application's categories and priorities")

        if metadata.get("sklearn_version") != sklearn.__version__:
            logger.warning(
                "Model trained with scikit-learn %s but %s is installed; retrain to be safe",
                metadata.get("sklearn_version"),
                sklearn.__version__,
            )

        self._category = joblib.load(model_dir / "category.joblib")
        self._priority = joblib.load(model_dir / "priority.joblib")
        if set(self._category.classes_) != set(CATEGORIES) or set(self._priority.classes_) != set(PRIORITIES):
            raise TriageModelError("Loaded model classes do not match the configured labels")

        self.name = metadata["model_name"]
        self.version = metadata["model_version"]
        self.recommended_threshold = metadata.get("confidence", {}).get("recommended_threshold")
        # Temperature scaling per task (v2+); absent for v1, which uses predict_proba.
        self._temperatures = {
            task: float(cfg["temperature"])
            for task, cfg in metadata.get("calibration", {}).items()
            if cfg.get("method") == "temperature"
        }
        self.calibrated = bool(self._temperatures)

        # An older scikit-learn can unpickle the model but then fail on the first
        # prediction; test once here so that shows up at startup, not as a 500.
        try:
            self.predict("model self-test")
        except Exception as exc:
            raise TriageModelError(
                f"Model cannot predict with scikit-learn {sklearn.__version__} "
                f"(trained with {metadata.get('sklearn_version')}); start the API with the project's .venv"
            ) from exc

    def _probabilities(self, pipeline, task: str, text: str) -> dict[str, float]:
        temperature = self._temperatures.get(task)
        if temperature is None:  # v1 artifacts: the classifier's own probabilities
            probs = pipeline.predict_proba([text])[0]
        else:  # v2+: temperature-scaled softmax of the decision scores
            probs = softmax(np.asarray(pipeline.decision_function([text]))[0] / temperature)
        return dict(zip(pipeline.classes_, probs))

    def predict(self, text: str) -> TriageResult:
        category_probs = self._probabilities(self._category, "category", text)
        priority_probs = self._probabilities(self._priority, "priority", text)
        category = max(category_probs, key=category_probs.get)
        priority = max(priority_probs, key=priority_probs.get)
        return TriageResult(
            model_name=self.name,
            model_version=self.version,
            category=str(category),
            category_confidence=round(float(category_probs[category]), 4),
            priority=str(priority),
            priority_confidence=round(float(priority_probs[priority]), 4),
            probabilities={
                "category": {str(k): round(float(v), 4) for k, v in category_probs.items()},
                "priority": {str(k): round(float(v), 4) for k, v in priority_probs.items()},
            },
            explanation={
                "category_terms": _top_terms(self._category, text, str(category)),
                "priority_terms": _top_terms(self._priority, text, str(priority)),
                "keyword_baseline": {"category": keyword_category(text), "priority": keyword_priority(text)},
            },
        )


def _top_terms(pipeline, text: str, label: str, limit: int = 6) -> list[dict]:
    """Words (and keyword-list hits) that pushed the linear score towards `label`:
    contribution = feature value × the classifier's weight for that class. Exact for
    linear models; character n-gram features are left out because fragments are
    not readable. Returns [] if the pipeline is not a linear text model."""
    try:
        # Apply the fitted feature steps directly (a sliced Pipeline counts as unfitted).
        x, names = [text], None
        for _name, step in pipeline.steps[:-1]:
            names = step.get_feature_names_out(names)
            x = step.transform(x)
        x = csr_matrix(x)
        clf = pipeline.steps[-1][1]
        weights = clf.coef_[list(clf.classes_).index(label)]
    except (AttributeError, ValueError, IndexError):
        return []
    terms = []
    for idx, value in zip(x.indices, x.data):
        name = str(names[idx])
        if "char__" in name:
            continue
        contribution = float(value * weights[idx])
        if contribution > 0:
            terms.append({"term": name.split("__", 1)[-1], "weight": round(contribution, 4)})
    terms.sort(key=lambda t: t["weight"], reverse=True)
    return terms[:limit]


@lru_cache(maxsize=4)
def _load_cached(model_dir: str) -> SklearnTriageModel:
    return SklearnTriageModel(Path(model_dir))


def load_triage_model(settings: Settings) -> SklearnTriageModel:
    # The loaded pipelines are only used for prediction (read-only), so one
    # instance per directory can be shared by every app instance.
    return _load_cached(str(Path(settings.model_dir).resolve()))


def effective_threshold(settings: Settings, model: TriageModel) -> tuple[float, str]:
    """CONFIDENCE_THRESHOLD from configuration wins; otherwise the threshold
    selected on validation data and recorded with the model."""
    if settings.confidence_threshold is not None:
        return settings.confidence_threshold, "CONFIG"
    if model.recommended_threshold is not None:
        return float(model.recommended_threshold), f"MODEL_METADATA:{model.version}"
    raise TriageModelError("No confidence threshold configured and none recorded with the model")


def review_reasons(result: TriageResult, threshold: float, settings: Settings) -> list[str]:
    reasons = []
    if result.category_confidence < threshold:
        reasons.append(LOW_CATEGORY_CONFIDENCE)
    if result.priority_confidence < threshold:
        reasons.append(LOW_PRIORITY_CONFIDENCE)
    if settings.review_high_severity and result.priority in HIGH_SEVERITY_PRIORITIES:
        reasons.append(HIGH_SEVERITY)
    return reasons
