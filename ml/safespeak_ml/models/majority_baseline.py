"""Candidate 0 - Majority-class floor.

Always predicts the most frequent label in the training data. It learns nothing about
the text, so any useful model must beat it. Not selectable; no confidence.
"""
from collections import Counter

from safespeak_ml.models.base import Candidate


class MajorityBaseline(Candidate):
    number, name, title, kind = 0, "majority_baseline", "Majority-class floor", "rule"
    has_scores = False

    def fit(self, texts, labels):
        self.majority = Counter(labels).most_common(1)[0][0]
        self.classes_ = sorted(set(labels))
        return self

    def predict(self, texts):
        return [self.majority] * len(texts)
