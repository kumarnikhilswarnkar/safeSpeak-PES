"""Candidate 4 - Word n-grams (1-3) + Logistic Regression.

Adds word pairs and triples ("not working", "hot water not") so short phrases count as
evidence, not only single words.
"""
from safespeak_ml.features.text_features import word_tfidf
from safespeak_ml.models.base import LinearTextCandidate


class WordNgramLogistic(LinearTextCandidate):
    number, name, title = 4, "word_ngram_logistic", "Word 1-3-grams + Logistic Regression"
    classifier_type = "logistic"

    def build_features(self):
        return word_tfidf(3)
