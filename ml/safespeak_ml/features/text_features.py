"""TF-IDF feature builders.

Preprocessing happens inside the scikit-learn vectorizers, so training and the
backend apply exactly the same steps: lowercasing, Unicode accent stripping, and
tokenisation (word features: runs of 2+ letters/digits; character features:
2-5-character chunks inside word boundaries, which tolerate spelling mistakes).
TF-IDF weighs each term by how informative it is across all complaints;
sublinear_tf dampens repeated words.
"""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import FeatureUnion

from safespeak_ml import config


def word_tfidf(ngram_max: int) -> TfidfVectorizer:
    """Word unigrams (ngram_max=1) or word n-grams up to ngram_max."""
    return TfidfVectorizer(ngram_range=(1, ngram_max), **config.WORD_TFIDF)


def char_tfidf() -> TfidfVectorizer:
    return TfidfVectorizer(**config.CHAR_TFIDF)


def word_char_union(extra: list | None = None) -> FeatureUnion:
    """Word 1-2-grams + character 2-5-grams (+ optional extra transformers)."""
    parts = [("word", word_tfidf(2)), ("char", char_tfidf())]
    return FeatureUnion(parts + (extra or []))
