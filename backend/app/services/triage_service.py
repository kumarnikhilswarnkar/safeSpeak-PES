"""AI triage: category, priority and confidence for a complaint text.

The backend loads exactly the models named in ml/artifacts/<version>/deployed.json,
which ml/scripts/run_experiments.py writes after evaluating all candidates. There is
no other (hidden, fallback or hard-coded) model: if the deployed artifacts are missing
or any file fails its SHA-256 check, the model is not loaded (submissions then go to
human review handling in the API layer). Inference only - the backend never trains.

Per task: scores = classifier scores for the complaint -> calibrated probabilities
(the same formulas as ml/safespeak_ml/evaluation/calibration.py) -> label = most
probable class, confidence = its probability.
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
from scipy.sparse import csr_matrix
from scipy.special import expit, softmax

from app.core.config import Settings
from app.core.taxonomy import CATEGORIES, HIGH_SEVERITY_PRIORITIES, PRIORITIES
from app.services.keyword_features import keyword_category, keyword_priority

logger = logging.getLogger("safespeak.triage")

LOW_CATEGORY_CONFIDENCE = "LOW_CATEGORY_CONFIDENCE"
LOW_PRIORITY_CONFIDENCE = "LOW_PRIORITY_CONFIDENCE"
HIGH_SEVERITY = "HIGH_SEVERITY"
TASK_LABELS = {"category": CATEGORIES, "priority": PRIORITIES}


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
    # Evidence for the reviewer (words for linear models, similar training complaints
    # for embedding models) and what the frozen keyword baseline would have said.
    explanation: dict = field(default_factory=dict)

    @property
    def confidence(self) -> float:
        """Overall confidence: the weaker of the two predictions."""
        return min(self.category_confidence, self.priority_confidence)


class TriageModel(Protocol):
    name: str
    version: str
    recommended_threshold: float | None
    recommended_priority_threshold: float | None

    def predict(self, text: str) -> TriageResult: ...


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def calibrate(method: str, params: dict, scores: np.ndarray) -> np.ndarray:
    """Same formulas as ml/safespeak_ml/evaluation/calibration.apply."""
    if method == "raw":
        return softmax(scores, axis=-1)
    if method == "temperature":
        return softmax(scores / params["temperature"], axis=-1)
    if method == "sigmoid":
        p = expit(scores * np.asarray(params["a"]) + np.asarray(params["b"]))
        return p / p.sum(axis=-1, keepdims=True)
    raise TriageModelError(f"Unknown calibration method: {method}")


class TaskModel:
    """One task's deployed model: features + classifier + calibration + threshold."""

    def __init__(self, task: str, directory: Path, encoder_dir: Path):
        self.task = task
        meta = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        if tuple(meta["classes"]) != TASK_LABELS[task]:
            raise TriageModelError(f"{task} model classes do not match the application's labels")
        self.metadata = meta
        self.name = meta["model_name"]
        self.kind = meta["kind"]
        calibration = json.loads((directory / "calibration.json").read_text(encoding="utf-8"))
        self.calibration_method, self.calibration_params = calibration["method"], calibration["params"]
        self.threshold = float(json.loads((directory / "thresholds.json").read_text(encoding="utf-8"))["threshold"])
        self.classifier = joblib.load(directory / "classifier.joblib")
        self.labels = list(TASK_LABELS[task])
        self._order = [list(map(str, self.classifier.classes_)).index(lbl) for lbl in self.labels]
        if self.kind == "linear-text":
            self.vectorizer = joblib.load(directory / "vectorizer.joblib")
        elif self.kind == "embedding-lr":
            from sentence_transformers import SentenceTransformer  # only needed for embedding models

            self.encoder = SentenceTransformer(str(encoder_dir), device="cpu", local_files_only=True)
            self.reference = np.load(directory / "reference_embeddings.npy")
            self.reference_labels = json.loads((directory / "reference_labels.json").read_text(encoding="utf-8"))
        else:
            raise TriageModelError(f"Unsupported deployed model kind: {self.kind}")

    def _features(self, text: str):
        if self.kind == "linear-text":
            return self.vectorizer.transform([text])
        return self.encoder.encode([text], normalize_embeddings=True, show_progress_bar=False)

    def probabilities(self, text: str) -> np.ndarray:
        scores = np.asarray(self.classifier.decision_function(self._features(text)))[0][self._order]
        return calibrate(self.calibration_method, self.calibration_params, scores)

    def evidence(self, text: str, label: str, limit: int = 6) -> dict:
        if self.kind == "linear-text":
            return {"terms": _top_terms(self.vectorizer, self.classifier, text, label, limit)}
        vector = self._features(text)[0]
        similarity = self.reference @ vector
        top = np.argsort(-similarity)[:3]
        return {"similar_training": [
            {"label": self.reference_labels[i], "similarity": round(float(similarity[i]), 3)} for i in top
        ]}


def _top_terms(vectorizer, classifier, text: str, label: str, limit: int) -> list[dict]:
    """Words (and keyword-list hits) that pushed the linear score towards `label`:
    contribution = feature value x the classifier's weight for that class. Exact for
    linear models; character n-gram features are left out because fragments are not
    readable."""
    x = csr_matrix(vectorizer.transform([text]))
    names = vectorizer.get_feature_names_out()
    weights = classifier.coef_[list(map(str, classifier.classes_)).index(label)]
    terms = []
    for idx, value in zip(x.indices, x.data):
        name = str(names[idx])
        if name.startswith("char__"):
            continue
        contribution = float(value * weights[idx])
        if contribution > 0:
            terms.append({"term": name.split("__", 1)[-1], "weight": round(contribution, 4)})
    terms.sort(key=lambda t: t["weight"], reverse=True)
    return terms[:limit]


class DeployedTriageModel:
    """The category and priority models listed in deployed.json."""

    def __init__(self, artifacts_dir: Path):
        deployed_path = artifacts_dir / "deployed.json"
        try:
            deployed = json.loads(deployed_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise TriageModelError(f"Cannot read {deployed_path}") from exc
        # joblib files can execute code: only load files whose checksums match deployed.json.
        for task in TASK_LABELS:
            entry = deployed[task]
            for filename, expected in entry["files"].items():
                path = artifacts_dir / entry["path"] / filename
                if not path.exists() or _sha256(path) != expected:
                    raise TriageModelError(f"Deployed file {entry['path']}/{filename} is missing or does not match deployed.json")
        encoder_dir = artifacts_dir / "encoders" / "all-MiniLM-L6-v2"
        self.tasks = {task: TaskModel(task, artifacts_dir / deployed[task]["path"], encoder_dir) for task in TASK_LABELS}
        self.version = deployed["version"]
        self.name = f"{self.tasks['category'].name}+{self.tasks['priority'].name}"
        self.recommended_threshold = self.tasks["category"].threshold
        self.recommended_priority_threshold = self.tasks["priority"].threshold
        self.probe_predictions = deployed.get("probe_predictions", [])
        try:  # fail at startup, not on the first complaint
            self.predict("model self-test")
        except Exception as exc:
            raise TriageModelError(f"Deployed model cannot predict: {type(exc).__name__}: {exc}") from exc

    def predict(self, text: str) -> TriageResult:
        out, explanation = {}, {}
        for task, model in self.tasks.items():
            probs = model.probabilities(text)
            best = int(np.argmax(probs))
            out[task] = (model.labels[best], float(probs[best]), dict(zip(model.labels, probs)))
            explanation[f"{task}_model"] = {"model": model.name, "kind": model.kind,
                                             "calibration": model.calibration_method,
                                             **model.evidence(text, model.labels[best])}
        explanation["keyword_baseline"] = {"category": keyword_category(text), "priority": keyword_priority(text)}
        # Backwards-compatible keys used by the UI for linear models.
        explanation["category_terms"] = explanation["category_model"].get("terms", [])
        explanation["priority_terms"] = explanation["priority_model"].get("terms", [])
        return TriageResult(
            model_name=self.name,
            model_version=self.version,
            category=out["category"][0],
            category_confidence=round(out["category"][1], 4),
            priority=out["priority"][0],
            priority_confidence=round(out["priority"][1], 4),
            probabilities={task: {k: round(float(v), 4) for k, v in out[task][2].items()} for task in out},
            explanation=explanation,
        )


@lru_cache(maxsize=4)
def _load_cached(artifacts_dir: str) -> DeployedTriageModel:
    return DeployedTriageModel(Path(artifacts_dir))


def load_triage_model(settings: Settings) -> DeployedTriageModel:
    # Read-only models, shared by every app instance in the process.
    return _load_cached(str(Path(settings.model_dir).resolve()))


def effective_threshold(settings: Settings, model: TriageModel) -> tuple[float, str]:
    """Category threshold: CONFIDENCE_THRESHOLD wins; otherwise the threshold selected
    on development cross-validation and stored with the deployed model."""
    if settings.confidence_threshold is not None:
        return settings.confidence_threshold, "CONFIG"
    if model.recommended_threshold is not None:
        return float(model.recommended_threshold), f"MODEL_METADATA:{model.version}"
    raise TriageModelError("No confidence threshold configured and none recorded with the model")


def effective_priority_threshold(settings: Settings, model: TriageModel) -> tuple[float, str]:
    """Priority threshold, selected independently of the category threshold."""
    if settings.priority_confidence_threshold is not None:
        return settings.priority_confidence_threshold, "CONFIG"
    value = getattr(model, "recommended_priority_threshold", None)
    if value is not None:
        return float(value), f"MODEL_METADATA:{model.version}"
    return effective_threshold(settings, model)


def review_reasons(
    result: TriageResult, threshold: float, settings: Settings, priority_threshold: float | None = None
) -> list[str]:
    """Why a complaint needs a human: low category confidence, low priority confidence
    (each against its own threshold), or a High/Critical priority."""
    priority_threshold = threshold if priority_threshold is None else priority_threshold
    reasons = []
    if result.category_confidence < threshold:
        reasons.append(LOW_CATEGORY_CONFIDENCE)
    if result.priority_confidence < priority_threshold:
        reasons.append(LOW_PRIORITY_CONFIDENCE)
    if settings.review_high_severity and result.priority in HIGH_SEVERITY_PRIORITIES:
        reasons.append(HIGH_SEVERITY)
    return reasons
