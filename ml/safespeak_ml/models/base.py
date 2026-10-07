"""Common interface for every candidate model.

    model = SomeCandidate(task="category")     # or "priority"
    model.fit(texts, labels)                   # training
    model.predict(texts)                       # predicted labels
    model.scores(texts)                        # per-class scores (logits / margins), columns = model.classes_
    model.save(directory)                      # writes the inspectable artifact files

How confidence is calculated (all probabilistic candidates):
    raw probability = softmax(scores)  (for Logistic Regression this equals predict_proba;
                                        for a Linear SVM it is a softmax over its margins)
    calibrated probability = calibration method applied to the scores (evaluation/calibration.py)
    confidence = the highest calibrated probability.
"""
from abc import ABC, abstractmethod
from pathlib import Path

import joblib
import numpy as np

from safespeak_ml import config


class Candidate(ABC):
    number: int
    name: str
    title: str
    kind: str  # "rule", "linear-text", "embedding-lr", "setfit"
    has_scores = True

    def __init__(self, task: str, seed: int = config.SEED):
        assert task in config.TASKS
        self.task = task
        self.seed = seed
        self.classes_: list[str] = []

    @abstractmethod
    def fit(self, texts: list[str], labels: list[str]) -> "Candidate": ...

    @abstractmethod
    def predict(self, texts: list[str]) -> list[str]: ...

    def scores(self, texts: list[str]) -> np.ndarray:
        raise NotImplementedError(f"{self.name} produces no scores")

    def describe(self) -> dict:
        return {"number": self.number, "name": self.name, "title": self.title, "kind": self.kind}

    def save(self, directory: Path) -> list[str]:
        raise NotImplementedError(f"{self.name} has no exportable artifact")


class LinearTextCandidate(Candidate):
    """TF-IDF style features + a linear classifier (Logistic Regression or Linear SVM)."""

    kind = "linear-text"
    classifier_type = "logistic"  # or "svm"

    @abstractmethod
    def build_features(self):
        """Return an unfitted scikit-learn transformer that turns texts into a feature matrix."""

    def build_classifier(self):
        from sklearn.linear_model import LogisticRegression
        from sklearn.svm import LinearSVC

        if self.classifier_type == "logistic":
            return LogisticRegression(random_state=self.seed, **config.LOGISTIC)
        return LinearSVC(random_state=self.seed, **config.LINEAR_SVM)

    def fit(self, texts, labels):
        self.vectorizer = self.build_features()
        features = self.vectorizer.fit_transform(texts)
        self.classifier = self.build_classifier().fit(features, labels)
        self.classes_ = [str(c) for c in self.classifier.classes_]
        return self

    def scores(self, texts):
        return np.asarray(self.classifier.decision_function(self.vectorizer.transform(texts)))

    def predict(self, texts):
        return [str(c) for c in self.classifier.predict(self.vectorizer.transform(texts))]

    def describe(self):
        return {
            **super().describe(),
            "features": repr(self.build_features()),
            "algorithm": "LogisticRegression" if self.classifier_type == "logistic" else "LinearSVC",
            "hyperparameters": config.LOGISTIC if self.classifier_type == "logistic" else config.LINEAR_SVM,
            "seed": self.seed,
        }

    def save(self, directory):
        directory.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.vectorizer, directory / "vectorizer.joblib")
        joblib.dump(self.classifier, directory / "classifier.joblib")
        return ["vectorizer.joblib", "classifier.joblib"]
