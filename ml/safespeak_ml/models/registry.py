"""Ordered list of the candidates 0-9 compared in the v3 experiment."""
from safespeak_ml.models.hybrid_classifier import HybridClassifier
from safespeak_ml.models.keyword_baseline import KeywordBaseline
from safespeak_ml.models.majority_baseline import MajorityBaseline
from safespeak_ml.models.minilm_logistic import MiniLMLogistic
from safespeak_ml.models.setfit_classifier import SetFitClassifier
from safespeak_ml.models.tfidf_logistic import TfidfLogistic
from safespeak_ml.models.tfidf_svm import TfidfSvm
from safespeak_ml.models.word_char_logistic import WordCharLogistic
from safespeak_ml.models.word_char_svm import WordCharSvm
from safespeak_ml.models.word_ngram_logistic import WordNgramLogistic

CANDIDATES = [
    MajorityBaseline,
    KeywordBaseline,
    TfidfLogistic,
    TfidfSvm,
    WordNgramLogistic,
    WordCharLogistic,
    WordCharSvm,
    HybridClassifier,
    MiniLMLogistic,
    SetFitClassifier,
]
BY_NAME = {c.name: c for c in CANDIDATES}
