"""Sentence embeddings with the locally stored MiniLM encoder (candidate 8).

all-MiniLM-L6-v2 maps a complaint to a 384-number vector that captures its meaning,
so paraphrases land close together even without shared words. The encoder is a
pretrained public model (Apache-2.0) loaded from local files only (HF_HUB_OFFLINE):
no network call, no external API. Vectors are L2-normalised (the model's own
Normalize module) and cached per text to avoid recomputing them in every CV fold.
"""
import os

import numpy as np

from safespeak_ml import config

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

_model = None
_cache: dict[str, np.ndarray] = {}


def encoder():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        if not (config.ENCODER_DIR / "model.safetensors").exists():
            raise FileNotFoundError("Encoder missing: run ml/scripts/download_encoder.py")
        _model = SentenceTransformer(str(config.ENCODER_DIR), device="cpu")
    return _model


def embed(texts: list[str]) -> np.ndarray:
    missing = [t for t in dict.fromkeys(texts) if t not in _cache]
    if missing:
        vectors = encoder().encode(missing, batch_size=64, normalize_embeddings=True, show_progress_bar=False)
        _cache.update(zip(missing, vectors))
    return np.vstack([_cache[t] for t in texts])
