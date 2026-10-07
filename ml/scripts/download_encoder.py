"""Download the sentence encoder for candidates 8/9 ONCE, at a pinned revision, and
verify every file by SHA-256. After this the encoder runs fully offline.

    ml/.venv-ml/Scripts/python ml/scripts/download_encoder.py

- Source: Hugging Face model sentence-transformers/all-MiniLM-L6-v2 (Apache-2.0),
  revision pinned in safespeak_ml/config.py.
- Weights go to ml/artifacts/v3/encoders/all-MiniLM-L6-v2/ (git-ignored, ~91 MB).
- ml/encoders.lock.json (committed) records the SHA-256 of every file. If the lock
  exists, the download must match it exactly; otherwise the lock is created, with the
  weights file checked against the SHA-256 that Hugging Face publishes for it.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from huggingface_hub import HfApi, snapshot_download  # noqa: E402

from safespeak_ml import config  # noqa: E402

# Only what sentence-transformers needs for PyTorch inference/fine-tuning (no ONNX/TF/OpenVINO copies).
ALLOW = [
    "config.json", "config_sentence_transformers.json", "modules.json", "sentence_bert_config.json",
    "special_tokens_map.json", "tokenizer.json", "tokenizer_config.json", "vocab.txt",
    "model.safetensors", "1_Pooling/config.json", "README.md",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    target = config.ENCODER_DIR
    snapshot_download(
        repo_id=config.ENCODER_REPO, revision=config.ENCODER_REVISION,
        local_dir=str(target), allow_patterns=ALLOW,
    )
    files = {p.relative_to(target).as_posix(): sha256(p) for p in sorted(target.rglob("*"))
             if p.is_file() and ".cache" not in p.parts}
    if config.ENCODER_LOCK.exists():
        lock = json.loads(config.ENCODER_LOCK.read_text(encoding="utf-8"))
        bad = [f for f, digest in lock["files"].items() if files.get(f) != digest]
        if bad or lock["revision"] != config.ENCODER_REVISION:
            print(f"Checksum mismatch against {config.ENCODER_LOCK.name}: {bad}", file=sys.stderr)
            return 1
        print(f"Encoder verified against {config.ENCODER_LOCK.name}: {len(files)} files OK")
        return 0
    # First pinned download: check the weights against the hash Hugging Face publishes.
    info = HfApi().model_info(config.ENCODER_REPO, revision=config.ENCODER_REVISION, files_metadata=True)
    published = {s.rfilename: s.lfs.sha256 for s in info.siblings if s.lfs}
    for name, digest in published.items():
        if name in files and files[name] != digest:
            print(f"{name}: SHA-256 differs from the value published by Hugging Face", file=sys.stderr)
            return 1
    lock = {
        "repo": config.ENCODER_REPO,
        "revision": config.ENCODER_REVISION,
        "license": config.ENCODER_LICENSE,
        "source": f"https://huggingface.co/{config.ENCODER_REPO}/tree/{config.ENCODER_REVISION}",
        "files": files,
        "verified_against_published_lfs_sha256": sorted(n for n in published if n in files),
    }
    config.ENCODER_LOCK.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    print(f"Downloaded {len(files)} files; weights match the published SHA-256; wrote {config.ENCODER_LOCK.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
