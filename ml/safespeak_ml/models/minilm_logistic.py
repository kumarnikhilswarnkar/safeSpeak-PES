"""Candidate 8 - MiniLM sentence embeddings + Logistic Regression.

Features: the pretrained all-MiniLM-L6-v2 encoder (frozen, local files) turns each
complaint into a 384-number "meaning vector". Algorithm: Logistic Regression learns
the categories from those vectors.

Explanation limit: there are no word weights. As evidence the model can show the most
similar training complaints (cosine similarity of the vectors) - that is supporting
context, not an exact explanation of the decision.
"""
import json

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression

from safespeak_ml import config
from safespeak_ml.features.embeddings import embed
from safespeak_ml.models.base import Candidate


class MiniLMLogistic(Candidate):
    number, name, title, kind = 8, "minilm_logistic", "MiniLM sentence embeddings + Logistic Regression", "embedding-lr"

    def fit(self, texts, labels):
        self.reference_vectors = embed(texts)
        self.reference_labels = list(labels)
        self.classifier = LogisticRegression(random_state=self.seed, **config.LOGISTIC).fit(self.reference_vectors, labels)
        self.classes_ = [str(c) for c in self.classifier.classes_]
        return self

    def scores(self, texts):
        return np.asarray(self.classifier.decision_function(embed(texts)))

    def predict(self, texts):
        return [str(c) for c in self.classifier.predict(embed(texts))]

    def describe(self):
        return {
            **super().describe(),
            "features": f"{config.ENCODER_REPO}@{config.ENCODER_REVISION} (384-d, L2-normalised, frozen)",
            "algorithm": "LogisticRegression",
            "hyperparameters": config.LOGISTIC,
            "seed": self.seed,
        }

    def save(self, directory):
        directory.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.classifier, directory / "classifier.joblib")
        np.save(directory / "reference_embeddings.npy", self.reference_vectors.astype(np.float32))
        lock = json.loads(config.ENCODER_LOCK.read_text(encoding="utf-8"))
        (directory / "encoder.json").write_text(json.dumps({
            "repo": config.ENCODER_REPO, "revision": config.ENCODER_REVISION, "license": config.ENCODER_LICENSE,
            "files": lock["files"], "normalize_embeddings": True,
        }, indent=2), encoding="utf-8")
        (directory / "reference_labels.json").write_text(json.dumps(self.reference_labels), encoding="utf-8")
        return ["classifier.joblib", "reference_embeddings.npy", "encoder.json", "reference_labels.json"]
