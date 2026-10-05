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
import sklearn

from app.core.config import Settings
from app.core.taxonomy import CATEGORIES, HIGH_SEVERITY_PRIORITIES, PRIORITIES

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

    def predict(self, text: str) -> TriageResult:
        category_probs = dict(zip(self._category.classes_, self._category.predict_proba([text])[0]))
        priority_probs = dict(zip(self._priority.classes_, self._priority.predict_proba([text])[0]))
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
        )


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
