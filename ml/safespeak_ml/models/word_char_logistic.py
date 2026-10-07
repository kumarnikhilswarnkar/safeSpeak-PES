"""Candidate 5 - Word (1-2) + character (2-5) n-grams + Logistic Regression.

Character chunks inside words make the model robust to spelling mistakes:
"projecter" still shares most chunks with "projector".
"""
from safespeak_ml.features.text_features import word_char_union
from safespeak_ml.models.base import LinearTextCandidate


class WordCharLogistic(LinearTextCandidate):
    number, name, title = 5, "word_char_logistic", "Word + character n-grams + Logistic Regression"
    classifier_type = "logistic"

    def build_features(self):
        return word_char_union()
