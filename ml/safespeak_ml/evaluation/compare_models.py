"""Pre-declared model selection rule (applied to grouped-CV results only).

1. Highest mean grouped-CV macro-F1 among selectable candidates (2-9).
2. Candidates within one standard deviation of the best mean are tied; among them
   prefer the most stable (lowest SD; SDs within config.STABILITY_TIE count as equal).
3. If still tied, prefer the simpler model (config.COMPLEXITY order).
4. Compare the winner with the frozen keyword baseline (reported, not a selection input).
5. The holdout is never used here.

`pool` restricts the candidates (used for the disclosed deployment constraint,
config.DEPLOYABLE); the rule itself is unchanged.
"""
from safespeak_ml import config


def select(cv: dict[str, dict], pool: list[str] | None = None) -> dict:
    pool = config.SELECTABLE if pool is None else pool
    eligible = {n: r["summary"]["macro_f1"] for n, r in cv.items() if n in pool}
    best_name = max(eligible, key=lambda n: eligible[n]["mean"])
    best = eligible[best_name]
    tied = {n: s for n, s in eligible.items() if s["mean"] >= best["mean"] - best["sd"]}
    min_sd = min(s["sd"] for s in tied.values())
    stable = {n: s for n, s in tied.items() if s["sd"] <= min_sd + config.STABILITY_TIE}
    winner = min(stable, key=lambda n: config.COMPLEXITY[n])
    keyword = cv.get("keyword_baseline", {}).get("summary", {}).get("macro_f1")
    w = eligible[winner]
    return {
        "selected": winner,
        "pool": sorted(eligible, key=lambda n: config.COMPLEXITY[n]),
        "rule": [
            "1. highest mean grouped-CV macro-F1",
            "2. within one SD of the best -> prefer lower SD (more stable)",
            f"3. SDs within {config.STABILITY_TIE} are equal -> prefer the simpler model",
            "4. compare with the frozen keyword baseline",
            "5. holdout never used for selection",
        ],
        "trace": {
            "best_mean": {"model": best_name, **best},
            "tied_within_one_sd": {n: s for n, s in sorted(tied.items(), key=lambda kv: -kv[1]["mean"])},
            "most_stable": sorted(stable),
            "simplest_among_stable": winner,
        },
        "winner_cv_macro_f1": w,
        "keyword_baseline_cv_macro_f1": keyword,
        "beats_keyword_baseline": keyword is not None and w["mean"] > keyword["mean"],
        "margin_over_keyword_in_sd": round((w["mean"] - keyword["mean"]) / w["sd"], 2) if keyword and w["sd"] else None,
    }
