"""Create the leakage-safe holdout ONCE: 40 whole paraphrase groups (120 records).

    ml/.venv-ml/Scripts/python ml/scripts/make_split.py           # refuses to overwrite
    ml/.venv-ml/Scripts/python ml/scripts/make_split.py --check   # recompute and compare
Writes ml/data/splits/v3_split.csv (id, group_id, partition). The holdout is never
used for model selection, threshold selection, calibration or feature decisions.
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from safespeak_ml import config, data  # noqa: E402


def check() -> int:
    """Recompute the holdout from the dataset and seed; it must equal the committed file."""
    rows = data.load_dataset()
    expected = data.make_holdout(rows)
    dev, holdout = data.load_split(rows)
    actual = {r.id: "holdout" for r in holdout} | {r.id: "dev" for r in dev}
    if actual != expected:
        print("Split file does NOT match the split recomputed from the dataset and seed", file=sys.stderr)
        return 1
    print(f"Split verified: {len(dev)} development / {len(holdout)} holdout; sha256 {data.sha256(config.SPLIT_FILE)}")
    return 0


def main() -> int:
    if sys.argv[1:] == ["--check"]:
        return check()
    if config.SPLIT_FILE.exists():
        print(f"{config.SPLIT_FILE} already exists; the holdout is fixed and is not regenerated.")
        return 0
    rows = data.load_dataset()
    partition = data.make_holdout(rows)
    data.write_split(rows, partition)
    dev, holdout = data.load_split(rows)
    print(f"development: {len(dev)} records / {len({r.group_id for r in dev})} groups")
    print(f"holdout:     {len(holdout)} records / {len({r.group_id for r in holdout})} groups")
    print("holdout category:", dict(Counter(r.category for r in holdout)))
    print("holdout priority:", dict(Counter(r.priority for r in holdout)))
    print("split sha256:", data.sha256(config.SPLIT_FILE))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
