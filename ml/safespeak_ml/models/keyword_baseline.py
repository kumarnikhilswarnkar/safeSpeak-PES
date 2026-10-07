"""Candidate 1 - Frozen keyword baseline (no machine learning).

Category: count how many words from each category's keyword list appear in the
complaint; the category with the most hits wins (no hit -> "Other").
Priority: the most severe priority whose keyword list matches (no hit -> "Medium").
The lexicon (backend/app/services/keyword_features.py) was written before any
experiment and is frozen (checksum-verified); it is never adjusted after seeing results.
Not selectable; no confidence.
"""
from safespeak_ml import config
from safespeak_ml.features.keyword_features import keyword_category, keyword_priority, verify_frozen
from safespeak_ml.models.base import Candidate


class KeywordBaseline(Candidate):
    number, name, title, kind = 1, "keyword_baseline", "Frozen keyword baseline", "rule"
    has_scores = False

    def fit(self, texts, labels):  # nothing is learned
        verify_frozen()
        self.classes_ = list(config.LABELS[self.task])
        return self

    def predict(self, texts):
        rule = keyword_category if self.task == "category" else keyword_priority
        return [rule(t) for t in texts]
