"""SafeSpeak PES machine-learning pipeline (model v3).

Package layout:
    config.py        protocol constants fixed BEFORE any experiment (seeds, splits, rules)
    data.py          dataset loading, integrity checks, leakage-safe holdout and CV folds
    features/        text features (TF-IDF), frozen keyword lexicon features, sentence embeddings
    models/          one file per candidate model (0-9) with fit / predict / scores / save
    evaluation/      metrics, grouped cross-validation, calibration, thresholds, selection
    training/        the experiment per task (category, priority) and export of the selected models

Entry points live in ml/scripts/. See ml/README.md.
"""
