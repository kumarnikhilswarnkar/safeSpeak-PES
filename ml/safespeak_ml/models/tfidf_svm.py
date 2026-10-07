"""Candidate 3 - TF-IDF (single words) + Linear SVM.

Same features as candidate 2. A Linear SVM also learns word weights, but places the
boundary between classes as far as possible from the training examples (maximum
margin). It outputs margins, not probabilities; confidence = softmax of the margins,
then calibration.
"""
from safespeak_ml.features.text_features import word_tfidf
from safespeak_ml.models.base import LinearTextCandidate


class TfidfSvm(LinearTextCandidate):
    number, name, title = 3, "tfidf_svm", "TF-IDF words + Linear SVM"
    classifier_type = "svm"

    def build_features(self):
        return word_tfidf(1)
