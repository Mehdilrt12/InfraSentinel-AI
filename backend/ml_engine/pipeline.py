import json
import os
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
from monitoring.models import Anomaly
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
MODEL_DIR = Path(settings.BASE_DIR) / "model_store"


def dataset_for(customer, *, days=30):
    cutoff = timezone.now() - timedelta(days=days)
    rows = list(
        NormalizedMetric.objects.filter(
            customer=customer,
            metric_name__in=FEATURES,
            timestamp__gte=cutoff,
            metric_value__isnull=False,
        ).values("machine_id", "timestamp", "metric_name", "metric_value")
    )
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


def train_customer_model(customer_id, *, days=30):
    customer = Customer.objects.get(pk=customer_id)
    data = dataset_for(customer, days=days)
    if len(data) < 20:
        raise ValueError("Au moins 20 fenêtres de métriques réelles sont requises.")
    pipeline = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", RobustScaler()),
            ("model", IsolationForest(**PARAMETERS)),
        ]
    )
    pipeline.fit(data)
    scores = -pipeline.decision_function(data)
    threshold = float(np.quantile(scores, 1 - PARAMETERS["contamination"]))
    version_name = timezone.now().strftime("iforest-%Y%m%dT%H%M%SZ")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    target = MODEL_DIR / f"{customer.pk}-{version_name}.joblib"
    temporary = target.with_suffix(".tmp")
    joblib.dump(pipeline, temporary)
    os.replace(temporary, target)
    metadata = {
        "rows": len(data),
        "from": data.index.get_level_values("bucket").min().isoformat(),
        "to": data.index.get_level_values("bucket").max().isoformat(),
        "source": "NormalizedMetric",
        "synthetic": False,
    }
    evaluation = {
        "anomaly_rate": float((scores >= threshold).mean()),
        "mean_anomaly_score": float(scores.mean()),
        "score_std": float(scores.std()),
    }
    with transaction.atomic():
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
            },
            parameters=PARAMETERS,
            dataset=metadata,
            evaluation_metrics=evaluation,
            decision_threshold=threshold,
            artifact_path=str(target),
            trained_at=timezone.now(),
            status=MLModelVersion.Status.READY,
            active=True,
        )
    return {
        "model_id": str(model.pk),
        "version": version_name,
        "samples": len(data),
        "threshold": threshold,
    }


def infer_customer(customer_id, *, days=1):
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
    data = dataset_for(customer, days=days)
    if data.empty:
        return {"anomalies": 0, "reason": "no_recent_data"}
    pipeline = joblib.load(model_version.artifact_path)
    scores = -pipeline.decision_function(data)
    created = 0
    for (machine_id, bucket), score in zip(data.index, scores, strict=True):
        if float(score) < model_version.decision_threshold:
            continue
        if Anomaly.objects.filter(
            machine_id=machine_id,
            model_version=model_version.version,
            detected_at__gte=bucket,
        ).exists():
            continue
        explanation = {
            "features": {
                key: (None if pd.isna(value) else float(value))
                for key, value in data.loc[(machine_id, bucket)].to_dict().items()
            },
            "method": "Isolation Forest decision_function",
            "synthetic": False,
        }
        anomaly = Anomaly.objects.create(
            customer=customer,
            machine_id=machine_id,
            score=float(score),
            threshold=model_version.decision_threshold,
            model_version=model_version.version,
            explanation=explanation,
        )
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
