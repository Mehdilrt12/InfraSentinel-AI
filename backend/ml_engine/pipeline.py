import json
import os
import uuid
from datetime import timedelta
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler
from accounts.models import Customer
from metrics.models import NormalizedMetric
from monitoring.alert_service import create_or_update_alert
from monitoring.audit import record_audit
from monitoring.models import Anomaly, AuditLog
from .models import MLModelVersion

FEATURES = [
    "system.cpu.utilization",
    "system.memory.utilization",
    "system.disk.utilization",
    "system.network.in",
    "system.network.out",
    "system.network.latency",
]
PARAMETERS = {
    "n_estimators": 200,
    "contamination": 0.02,
    "random_state": 42,
    "n_jobs": -1,
}
MODEL_DIR = Path(settings.ML_MODEL_DIR)


def dataset_for(customer, *, days=30, machine_ids=None):
    cutoff = timezone.now() - timedelta(days=days)
    metrics = NormalizedMetric.objects.filter(
        customer=customer,
        metric_name__in=FEATURES,
        timestamp__gte=cutoff,
        metric_value__isnull=False,
    )
    if machine_ids is not None:
        metrics = metrics.filter(machine_id__in=machine_ids)
    rows = list(metrics.values("machine_id", "timestamp", "metric_name", "metric_value"))
    if not rows:
        return pd.DataFrame(columns=FEATURES)
    frame = pd.DataFrame(rows)
    frame["bucket"] = pd.to_datetime(frame["timestamp"], utc=True).dt.floor("5min")
    pivot = frame.pivot_table(
        index=["machine_id", "bucket"],
        columns="metric_name",
        values="metric_value",
        aggfunc="mean",
    )
    return pivot.reindex(columns=FEATURES).sort_index()


def train_customer_model(customer_id, *, days=30, dataset_metadata=None):
    customer = Customer.objects.get(pk=customer_id)
    data = dataset_for(customer, days=days)
    if len(data) < 20:
        raise ValueError("Au moins 20 fenêtres de métriques réelles sont requises.")
    split = max(1, min(len(data) - 1, int(len(data) * 0.8)))
    training_data = data.iloc[:split]
    validation_data = data.iloc[split:]
    pipeline = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", RobustScaler()),
            ("model", IsolationForest(**PARAMETERS)),
        ]
    )
    pipeline.fit(training_data)
    training_scores = -pipeline.decision_function(training_data)
    validation_scores = -pipeline.decision_function(validation_data)
    threshold = float(np.quantile(training_scores, 1 - PARAMETERS["contamination"]))
    version_name = (
        timezone.now().strftime("iforest-%Y%m%dT%H%M%S") + f"-{uuid.uuid4().hex[:8]}"
    )
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    target = MODEL_DIR / f"{customer.pk}-{version_name}.joblib"
    temporary = target.with_suffix(".tmp")
    joblib.dump(pipeline, temporary)
    os.replace(temporary, target)
    dataset_metadata = dataset_metadata or {}
    metadata = {
        "rows": len(data),
        "training_rows": len(training_data),
        "validation_rows": len(validation_data),
        "from": data.index.get_level_values("bucket").min().isoformat(),
        "to": data.index.get_level_values("bucket").max().isoformat(),
        "source": "NormalizedMetric",
        "synthetic": bool(dataset_metadata.get("synthetic", False)),
        **dataset_metadata,
    }
    evaluation = {
        "method": "chronological_holdout",
        "ground_truth_available": False,
        "precision": None,
        "recall": None,
        "training_anomaly_rate": float((training_scores >= threshold).mean()),
        "validation_anomaly_rate": float((validation_scores >= threshold).mean()),
        "validation_score_mean": float(validation_scores.mean()),
        "validation_score_std": float(validation_scores.std()),
        "validation_score_p95": float(np.quantile(validation_scores, 0.95)),
    }
    try:
        with transaction.atomic():
            customer = Customer.objects.select_for_update().get(pk=customer_id)
            MLModelVersion.objects.filter(customer=customer, active=True).update(
                active=False
            )
            model = MLModelVersion.objects.create(
                customer=customer,
                version=version_name,
                features=FEATURES,
                preprocessing={
                    "imputer": "median",
                    "scaler": "RobustScaler",
                    "window": "5min",
                    "split": "chronological_80_20",
                },
                parameters=PARAMETERS,
                dataset=metadata,
                evaluation_metrics=evaluation,
                decision_threshold=threshold,
                artifact_path=target.name,
                trained_at=timezone.now(),
                status=MLModelVersion.Status.READY,
                active=True,
            )
            record_audit(
                AuditLog.Action.MODEL_TRAINED,
                customer=customer,
                target=model,
                metadata={
                    "version": version_name,
                    "algorithm": model.algorithm,
                    "samples": len(data),
                    "training_rows": len(training_data),
                    "validation_rows": len(validation_data),
                    "decision_threshold": threshold,
                    "synthetic": metadata["synthetic"],
                },
            )
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return {
        "model_id": str(model.pk),
        "version": version_name,
        "samples": len(data),
        "threshold": threshold,
    }


def infer_customer(customer_id, *, days=1, machine_ids=None):
    customer = Customer.objects.get(pk=customer_id)
    model_version = (
        MLModelVersion.objects.filter(
            customer=customer, active=True, status=MLModelVersion.Status.READY
        )
        .order_by("-trained_at")
        .first()
    )
    if not model_version:
        return {"anomalies": 0, "reason": "no_active_model"}
    data = dataset_for(customer, days=days, machine_ids=machine_ids)
    if data.empty:
        return {"anomalies": 0, "reason": "no_recent_data"}
    artifact = Path(model_version.artifact_path)
    if not artifact.is_absolute():
        artifact = MODEL_DIR / artifact.name
    if not artifact.is_file():
        return {
            "anomalies": 0,
            "reason": "model_artifact_missing",
            "model_version": model_version.version,
        }
    pipeline = joblib.load(artifact)
    scores = -pipeline.decision_function(data)
    created = 0
    for (machine_id, bucket), score in zip(data.index, scores, strict=True):
        if float(score) < model_version.decision_threshold:
            continue
        explanation = {
            "features": {
                key: (None if pd.isna(value) else float(value))
                for key, value in data.loc[(machine_id, bucket)].to_dict().items()
            },
            "method": "Isolation Forest decision_function",
            "synthetic": bool(model_version.dataset.get("synthetic", False)),
        }
        anomaly, anomaly_created = Anomaly.objects.get_or_create(
            customer=customer,
            machine_id=machine_id,
            model_version=model_version.version,
            window_start=bucket.to_pydatetime(),
            defaults={
                "score": float(score),
                "threshold": model_version.decision_threshold,
                "explanation": explanation,
            },
        )
        if not anomaly_created:
            continue
        create_or_update_alert(
            machine=anomaly.machine,
            alert_type="ML_ANOMALY",
            severity="HIGH",
            source=anomaly.machine.source_type,
            message=f"Comportement anormal détecté (score {score:.3f})",
            context={
                "metric_name": "ml.multivariate.anomaly",
                "model_version": model_version.version,
                "features": explanation["features"],
                "source_type": anomaly.machine.source_type,
            },
            anomaly_score=float(score),
            source_key=f"ml:{model_version.version}",
        )
        from realtime.publisher import publish

        publish(
            customer,
            "anomaly.detected",
            {
                "id": str(anomaly.pk),
                "machine_id": str(machine_id),
                "score": float(score),
            },
            anomaly.pk,
        )
        created += 1
    return {
        "anomalies": created,
        "model_version": model_version.version,
        "evaluated": len(data),
    }


def metadata_json(model):
    return json.dumps(
        {
            "version": model.version,
            "features": model.features,
            "parameters": model.parameters,
            "dataset": model.dataset,
            "evaluation": model.evaluation_metrics,
        },
        indent=2,
    )
