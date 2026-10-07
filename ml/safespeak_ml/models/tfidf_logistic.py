"""Candidate 2 - TF-IDF (single words) + Logistic Regression.

Features: TF-IDF weight of every single word. Algorithm: multinomial Logistic
Regression learns one weight per word per class; a complaint's score for a class is
the sum of its word weights, turned into probabilities with softmax.
"""
from safespeak_ml.features.text_features import word_tfidf
from safespeak_ml.models.base import LinearTextCandidate


class TfidfLogistic(LinearTextCandidate):
    number, name, title = 2, "tfidf_logistic", "TF-IDF words + Logistic Regression"
    classifier_type = "logistic"

    def build_features(self):
        return word_tfidf(1)
