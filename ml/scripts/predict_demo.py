"""Predict with the DEPLOYED v3 models through the backend's own loader.

    backend/.venv/Scripts/python ml/scripts/predict_demo.py "The hostel water cooler is broken"
    backend/.venv/Scripts/python ml/scripts/predict_demo.py            # the probe texts

Uses app.services.triage_service exactly as the API does (deployed.json, checksum
verification, calibration, per-task thresholds), so what is printed here is what a
complaint submission would record. Nothing is trained or written.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from app.core.config import Settings  # noqa: E402
from app.services.triage_service import (  # noqa: E402
    effective_priority_threshold,
    effective_threshold,
    load_triage_model,
    review_reasons,
)


def main() -> int:
    # Only the model settings matter here; the secret is a throwaway to satisfy validation.
    settings = Settings(_env_file=None, jwt_secret_key="predict-demo-" + "x" * 32)
    model = load_triage_model(settings)
    threshold, source = effective_threshold(settings, model)
    p_threshold, p_source = effective_priority_threshold(settings, model)
    print(f"Model {model.name}:{model.version}  category threshold {threshold} [{source}]  "
          f"priority threshold {p_threshold} [{p_source}]\n")
    texts = sys.argv[1:] or [p["text"] for p in model.probe_predictions]
    for text in texts:
        r = model.predict(text)
        reasons = review_reasons(r, threshold, settings, p_threshold)
        print(f"“{text}”")
        print(f"  category {r.category} ({r.category_confidence:.3f})   priority {r.priority} ({r.priority_confidence:.3f})")
        print(f"  keyword baseline: {r.explanation['keyword_baseline']}")
        for task in ("category", "priority"):
            ev = r.explanation[f"{task}_model"]
            detail = ev.get("terms") or ev.get("similar_training")
            print(f"  {task} evidence ({ev['model']}): {json.dumps(detail)}")
        print(f"  -> {'HUMAN REVIEW ' + str(reasons) if reasons else 'automatic'}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
