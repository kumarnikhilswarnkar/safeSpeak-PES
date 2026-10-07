"""How the dataset enters the pipeline.

1. load_dataset()  reads the approved CSV and refuses it unless its SHA-256 matches
   config.DATASET_SHA256; checks labels, group sizes, parent links and label
   consistency inside each paraphrase group.
2. make_holdout()  (run ONCE by scripts/make_split.py) assigns 40 whole paraphrase
   groups (120 records) to the holdout; writes data/splits/v3_split.csv.
3. load_split()    reads that file and re-checks that no group spans both partitions.
4. cv_folds()      repeated StratifiedGroupKFold on the development partition only.

Leakage rule: a complaint and its paraphrases (same group_id) are always in the same
partition and the same CV fold, so a model is never tested on a paraphrase of a
complaint it was trained on.
"""
import csv
import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass

from sklearn.model_selection import StratifiedGroupKFold

from safespeak_ml import config


@dataclass(frozen=True)
class Record:
    id: str
    text: str
    category: str
    priority: str
    group_id: str
    parent_id: str
    style: str
    source: str


def sha256(path) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def load_dataset() -> list[Record]:
    digest = sha256(config.DATASET_FILE)
    if digest != config.DATASET_SHA256:
        raise ValueError(f"Dataset checksum mismatch: {digest} != {config.DATASET_SHA256}")
    with open(config.DATASET_FILE, encoding="utf-8-sig", newline="") as f:
        rows = [
            Record(r["id"], r["text"], r["category"], r["priority"], r["group_id"], r["parent_id"], r["style"], r["source"])
            for r in csv.DictReader(f)
        ]
    check_integrity(rows)
    return rows


def check_integrity(rows: list[Record]) -> None:
    ids = [r.id for r in rows]
    assert len(ids) == len(set(ids)) == 600, "expected 600 unique records"
    assert {r.category for r in rows} == set(config.CATEGORIES), "unexpected category labels"
    assert {r.priority for r in rows} == set(config.PRIORITIES), "unexpected priority labels"
    by_id = {r.id: r for r in rows}
    groups = defaultdict(list)
    for r in rows:
        groups[r.group_id].append(r)
        if r.parent_id:
            assert by_id[r.parent_id].group_id == r.group_id, f"{r.id}: parent in another group"
    for gid, members in groups.items():
        assert len({m.category for m in members}) == 1, f"group {gid} mixes categories"
        assert len({m.priority for m in members}) == 1, f"group {gid} mixes priorities"


def make_holdout(rows: list[Record]) -> dict[str, str]:
    """Return {record id: 'dev' | 'holdout'}: one stratified group fold of 40 groups."""
    splitter = StratifiedGroupKFold(n_splits=config.HOLDOUT_FOLDS, shuffle=True, random_state=config.SEED)
    _, holdout_idx = next(splitter.split(rows, [r.category for r in rows], [r.group_id for r in rows]))
    holdout = {rows[i].id for i in holdout_idx}
    return {r.id: ("holdout" if r.id in holdout else "dev") for r in rows}


def write_split(rows: list[Record], partition: dict[str, str]) -> None:
    config.SPLIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(config.SPLIT_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "group_id", "partition"])
        for r in rows:
            writer.writerow([r.id, r.group_id, partition[r.id]])


def load_split(rows: list[Record]) -> tuple[list[Record], list[Record]]:
    with open(config.SPLIT_FILE, encoding="utf-8", newline="") as f:
        partition = {r["id"]: r["partition"] for r in csv.DictReader(f)}
    assert set(partition) == {r.id for r in rows}, "split file does not match the dataset"
    dev = [r for r in rows if partition[r.id] == "dev"]
    holdout = [r for r in rows if partition[r.id] == "holdout"]
    shared = {r.group_id for r in dev} & {r.group_id for r in holdout}
    assert not shared, f"groups in both partitions: {sorted(shared)[:5]}"
    return dev, holdout


def cv_folds(dev: list[Record], repeat: int) -> list[tuple[list[int], list[int]]]:
    """Grouped, category-stratified folds of the development set for one repeat."""
    splitter = StratifiedGroupKFold(n_splits=config.CV_FOLDS, shuffle=True, random_state=config.CV_SEEDS[repeat])
    folds = []
    for train_idx, val_idx in splitter.split(dev, [r.category for r in dev], [r.group_id for r in dev]):
        train_groups = {dev[i].group_id for i in train_idx}
        assert not train_groups & {dev[i].group_id for i in val_idx}, "group leakage in CV fold"
        folds.append((list(train_idx), list(val_idx)))
    return folds


def describe(rows: list[Record], dev: list[Record], holdout: list[Record]) -> dict:
    def counts(part, field):
        return dict(Counter(getattr(r, field) for r in part))

    return {
        "file": config.DATASET_FILE.name,
        "version": config.DATASET_VERSION,
        "sha256": config.DATASET_SHA256,
        "nature": "Synthetic/controlled dataset: 200 AI-generated seed complaints + 400 AI paraphrases "
        "(group_id links a seed and its paraphrases). Not real student complaints.",
        "records": len(rows),
        "groups": len({r.group_id for r in rows}),
        "source_counts": counts(rows, "source"),
        "partitions": {
            name: {
                "records": len(part),
                "groups": len({r.group_id for r in part}),
                "category": counts(part, "category"),
                "priority": counts(part, "priority"),
            }
            for name, part in (("development", dev), ("holdout", holdout))
        },
        "split_file": str(config.SPLIT_FILE.relative_to(config.REPO_DIR)).replace("\\", "/"),
        "split_sha256": sha256(config.SPLIT_FILE),
        "leakage_rule": "whole paraphrase groups per partition and per CV fold",
    }
