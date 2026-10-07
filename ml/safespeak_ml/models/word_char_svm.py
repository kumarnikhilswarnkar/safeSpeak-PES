"""Candidate 6 - Word (1-2) + character (2-5) n-grams + Linear SVM."""
from safespeak_ml.features.text_features import word_char_union
from safespeak_ml.models.base import LinearTextCandidate


class WordCharSvm(LinearTextCandidate):
    number, name, title = 6, "word_char_svm", "Word + character n-grams + Linear SVM"
    classifier_type = "svm"

    def build_features(self):
        return word_char_union()
