"""Candidate 7 - Hybrid: word + character n-grams + keyword-count features + Logistic Regression.

The frozen keyword lexicon is NOT used as a rule here: the number of hits per keyword
list becomes extra input features, and Logistic Regression learns how much to trust
each list alongside the words and character chunks.
"""
from safespeak_ml.features.keyword_features import KeywordCounts
from safespeak_ml.features.text_features import word_char_union
from safespeak_ml.models.base import LinearTextCandidate


class HybridClassifier(LinearTextCandidate):
    number, name, title = 7, "hybrid_classifier", "Hybrid: words + characters + keyword counts + Logistic Regression"
    classifier_type = "logistic"

    def build_features(self):
        return word_char_union([("keywords", KeywordCounts(self.task))])
