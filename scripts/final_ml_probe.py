"""Sonde ML/prédiction/recommandation en lecture seule pour la validation finale."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import django
import joblib


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings  # noqa: E402

from inventory.models import Machine  # noqa: E402
from ml_engine.evaluation import evaluate_detection_strategies  # noqa: E402
from ml_engine.models import MLModelVersion  # noqa: E402
from ml_engine.pipeline import dataset_for  # noqa: E402
from ml_engine.predictive import analyze_machine_trends  # noqa: E402
from monitoring.models import Alert  # noqa: E402
from monitoring.recommendations import build_recommendation  # noqa: E402


def model_artifact(model: MLModelVersion) -> Path:
    artifact = Path(model.artifact_path)
    if not artifact.is_absolute():
        artifact = Path(settings.ML_MODEL_DIR) / artifact.name
    return artifact


def main() -> int:
    model = (
        MLModelVersion.objects.filter(active=True, status=MLModelVersion.Status.READY)
        .select_related("customer")
        .order_by("-trained_at")
        .first()
    )
    if not model:
        raise RuntimeError("Aucun modèle ML actif READY dans PostgreSQL.")
    artifact = model_artifact(model)
    if not artifact.is_file():
        raise RuntimeError(f"Artefact ML absent: {artifact.name}")
    data = dataset_for(model.customer, days=30)
    if data.empty:
        raise RuntimeError("Dataset normalisé récent vide pour le modèle actif.")
    pipeline = joblib.load(artifact)
    scores = -pipeline.decision_function(data)
    threshold = float(model.decision_threshold)

    trends = []
    for machine in Machine.objects.filter(customer=model.customer).iterator():
        for trend in analyze_machine_trends(machine, hours=24):
            if trend["risk_score"] > 0:
                trends.append(
                    {
                        "machine_id": str(machine.pk),
                        "metric": trend["metric_name"],
                        "trend": trend["trend"],
                        "rate_per_hour": trend["rate_of_change_per_hour"],
                        "risk": trend["risk_score"],
                        "breach_at": trend["estimated_threshold_breach_at"],
                        "confidence": trend["confidence"],
                        "is_estimate": trend["is_estimate"],
                        "disclaimer": trend["disclaimer"],
                    }
                )

    recommendation_checks = []
    active_alerts = Alert.objects.filter(customer=model.customer).exclude(
        status=Alert.Status.RESOLVED
    )
    for alert in active_alerts[:20]:
        context = {
            **(alert.context or {}),
            "source_type": alert.source,
            "severity": alert.severity,
        }
        recommendation = build_recommendation(
            context.get("metric_name") or alert.type, context
        )
        recommendation_checks.append(
            {
                "alert_type": alert.type,
                "source": alert.source,
                "actions": len(recommendation["actions"]),
                "diagnosis_hints": len(recommendation["diagnosis_hints"]),
                "destructive": recommendation["destructive"],
            }
        )

    result = {
        "model": {
            "version": model.version,
            "algorithm": model.algorithm,
            "trained_at": model.trained_at.isoformat(),
            "artifact_exists": True,
            "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            "features": model.features,
            "parameters": model.parameters,
            "preprocessing": model.preprocessing,
            "dataset": model.dataset,
            "evaluation": model.evaluation_metrics,
            "threshold": threshold,
        },
        "inference_read_only": {
            "windows": len(data),
            "normal_windows": int((scores < threshold).sum()),
            "anomalous_windows": int((scores >= threshold).sum()),
            "score_min": float(scores.min()),
            "score_max": float(scores.max()),
        },
        "detection_evaluation": evaluate_detection_strategies(model.customer_id),
        "predictive": {
            "risk_items": len(trends),
            "all_marked_as_estimates": bool(trends)
            and all(item["is_estimate"] for item in trends),
            "sample": trends[:3],
        },
        "recommendations": {
            "checked": len(recommendation_checks),
            "all_non_destructive": bool(recommendation_checks)
            and all(not item["destructive"] for item in recommendation_checks),
            "all_actionable": bool(recommendation_checks)
            and all(
                item["actions"] > 0 and item["diagnosis_hints"] > 0
                for item in recommendation_checks
            ),
            "sample": recommendation_checks[:6],
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
