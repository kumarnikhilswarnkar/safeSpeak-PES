"""The frozen keyword lexicon, shared with the backend.

The lexicon lives in backend/app/services/keyword_features.py so that the keyword
features of the hybrid model unpickle in the backend under the same module path.
It was written before any v2/v3 experiment and is frozen: its SHA-256 is checked here
and the pipeline refuses to run if it was edited (no tuning after seeing results).
"""
import hashlib
import sys

from safespeak_ml import config

if str(config.BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(config.BACKEND_DIR))

from app.services.keyword_features import (  # noqa: E402,F401
    CATEGORY_KEYWORDS,
    PRIORITY_KEYWORDS,
    KeywordCounts,
    keyword_category,
    keyword_priority,
)


def verify_frozen() -> str:
    digest = hashlib.sha256(config.KEYWORD_LEXICON_FILE.read_bytes()).hexdigest()
    if digest != config.KEYWORD_LEXICON_SHA256:
        raise RuntimeError("The keyword lexicon changed after it was frozen; refusing to run the comparison.")
    return digest
