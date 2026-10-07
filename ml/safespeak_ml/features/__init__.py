"""Feature extractors: TF-IDF text features, frozen keyword-lexicon features, and
sentence embeddings (MiniLM). Only scikit-learn classes and the backend's
KeywordCounts transformer are ever pickled, so saved artifacts load in the backend
without importing this package."""
