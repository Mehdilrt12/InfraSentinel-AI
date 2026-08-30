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
from django.db.models import Max, Q
from django.utils import timezone
from sklearn.ensemble import IsolationForest
from sklearn.compose import ColumnTransformer
from sklearn.impute import MissingIndicator, SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler
from accounts.models import Customer
from inventory.models import Machine
from metrics.models import NormalizedMetric
from monitoring.alert_service import create_or_update_alert, resolve_machine_alerts
from monitoring.audit import record_audit
from monitoring.models import Anomaly, AuditLog
from .models import MLModelVersion

BASE_FEATURES = [
    "system.cpu.utilization",
    "system.memory.utilization",
    "system.disk.utilization",
    "system.network.in",
    "system.network.out",
    "system.network.latency",
]
OPTIONAL_GPU_FEATURES = [
    "system.gpu.utilization",
    "system.gpu.memory.used",
    "system.gpu.memory.utilization",
    "system.gpu.temperature",
]
FEATURES = BASE_FEATURES + OPTIONAL_GPU_FEATURES
FEATURE_SCHEMA_VERSION = "2.0"
WINDOW_FREQUENCY = "1min"
MIN_TRAINING_WINDOWS = 200
MIN_OPTIONAL_FEATURE_WINDOWS = 200
MIN_FEATURE_COVERAGE = 0.5
TARGET_WINDOW_FLAG_RATE = 0.01
ANOMALY_REQUIRED_WINDOWS = 3
ANOMALY_LOOKBACK_WINDOWS = 5
RECOVERY_REQUIRED_WINDOWS = 3
PARAMETERS = {
    "n_estimators": 200,
    "contamination": 0.02,
    "random_state": 42,
    "n_jobs": -1,
}
MODEL_DIR = Path(settings.ML_MODEL_DIR)


def dataset_for(
    customer, *, days=30, machine_ids=None, features=None, include_controlled=False
):
    features = list(features or FEATURES)
    cutoff = timezone.now() - timedelta(days=days)
    metrics = NormalizedMetric.objects.filter(
        customer=customer,
        metric_name__in=features,
        timestamp__gte=cutoff,
        metric_value__isnull=False,
    )
    if not include_controlled:
        metrics = metrics.filter(
            Q(metadata__test_marker__isnull=True),
            Q(metadata__synthetic__isnull=True),
            Q(metadata__demo__isnull=True),
        )
    if machine_ids is not None:
        metrics = metrics.filter(machine_id__in=machine_ids)
    rows = list(metrics.values("machine_id", "timestamp", "metric_name", "metric_value"))
    if not rows:
        return pd.DataFrame(columns=features)
    frame = pd.DataFrame(rows)
    frame["bucket"] = pd.to_datetime(frame["timestamp"], utc=True).dt.floor(
        WINDOW_FREQUENCY
    )
    pivot = frame.pivot_table(
        index=["machine_id", "bucket"],
        columns="metric_name",
        values="metric_value",
        aggfunc="mean",
    )
    for metric_name in {
        "system.disk.utilization",
        "system.gpu.utilization",
        "system.gpu.memory.utilization",
        "system.gpu.temperature",
    }:
        metric_rows = frame[frame["metric_name"] == metric_name]
        if not metric_rows.empty:
            pivot[metric_name] = metric_rows.pivot_table(
                index=["machine_id", "bucket"],
                values="metric_value",
                aggfunc="max",
            )["metric_value"]
    gpu_memory = frame[frame["metric_name"] == "system.gpu.memory.used"]
    if not gpu_memory.empty:
        pivot["system.gpu.memory.used"] = gpu_memory.pivot_table(
            index=["machine_id", "bucket"],
            values="metric_value",
            aggfunc="max",
        )["metric_value"]
    pivot = pivot.reindex(columns=features)
    current_bucket = pd.Timestamp(timezone.now()).floor(WINDOW_FREQUENCY)
    pivot = pivot[pivot.index.get_level_values("bucket") < current_bucket]
    return (
        pivot.reset_index()
        .sort_values(["bucket", "machine_id"])
        .set_index(["machine_id", "bucket"])
    )


def _select_training_features(data):
    required_values = max(1, int(np.ceil(len(data) * MIN_FEATURE_COVERAGE)))
    coverage = data.notna().sum()
    insufficient_base = [
        feature for feature in BASE_FEATURES if coverage.get(feature, 0) < required_values
    ]
    if insufficient_base:
        raise ValueError(
            "Couverture insuffisante pour les métriques obligatoires: "
            + ", ".join(insufficient_base)
        )
    selected_optional = []
    for feature in OPTIONAL_GPU_FEATURES:
        if isinstance(data.index, pd.MultiIndex) and "machine_id" in data.index.names:
            machine_coverage = data[feature].notna().groupby(level="machine_id").agg(
                ["sum", "count"]
            )
            sufficiently_observed = (
                (machine_coverage["sum"] >= MIN_OPTIONAL_FEATURE_WINDOWS)
                & (machine_coverage["sum"] / machine_coverage["count"] >= MIN_FEATURE_COVERAGE)
            ).any()
        else:
            sufficiently_observed = coverage.get(feature, 0) >= max(
                required_values, MIN_OPTIONAL_FEATURE_WINDOWS
            )
        if sufficiently_observed:
            selected_optional.append(feature)
    return BASE_FEATURES + selected_optional, {
        feature: float(coverage.get(feature, 0) / len(data)) for feature in FEATURES
    }


def _stable_flag_rate(data, scores, threshold):
    decisions = 0
    evaluated = 0
    scored = pd.Series(scores, index=data.index)
    for _machine_id, machine_scores in scored.groupby(level="machine_id", sort=False):
        flags = (machine_scores.to_numpy() >= threshold).tolist()
        for index in range(ANOMALY_LOOKBACK_WINDOWS - 1, len(flags)):
            recent = flags[index - ANOMALY_LOOKBACK_WINDOWS + 1 : index + 1]
            decisions += int(recent[-1] and sum(recent) >= ANOMALY_REQUIRED_WINDOWS)
            evaluated += 1
    return float(decisions / evaluated) if evaluated else 0.0


def train_customer_model(
    customer_id, *, days=30, dataset_metadata=None, include_controlled=False
):
    customer = Customer.objects.get(pk=customer_id)
    data = dataset_for(customer, days=days, include_controlled=include_controlled)
    if len(data) < MIN_TRAINING_WINDOWS:
        raise ValueError(
            f"Au moins {MIN_TRAINING_WINDOWS} fenêtres de métriques réelles sont requises."
        )
    selected_features, feature_coverage = _select_training_features(data)
    data = data[selected_features]
    training_end = int(len(data) * 0.6)
    calibration_end = int(len(data) * 0.8)
    training_data = data.iloc[:training_end]
    calibration_data = data.iloc[training_end:calibration_end]
    validation_data = data.iloc[calibration_end:]
    optional_features = [
        feature for feature in selected_features if feature in OPTIONAL_GPU_FEATURES
    ]
    transformers = [
        (
            "numeric",
            Pipeline(
                [
                    ("imputer", SimpleImputer(strategy="median")),
                    ("scaler", RobustScaler()),
                ]
            ),
            selected_features,
        )
    ]
    if optional_features:
        transformers.append(
            (
                "optional_missing",
                MissingIndicator(features="all", error_on_new=False),
                optional_features,
            )
        )
    pipeline = Pipeline(
        [
            ("preprocessor", ColumnTransformer(transformers=transformers)),
            ("model", IsolationForest(**PARAMETERS)),
        ]
    )
    pipeline.fit(training_data)
    training_scores = -pipeline.decision_function(training_data)
    calibration_scores = -pipeline.decision_function(calibration_data)
    validation_scores = -pipeline.decision_function(validation_data)
    threshold_quantile = 1 - TARGET_WINDOW_FLAG_RATE
    threshold = float(
        max(
            np.quantile(training_scores, threshold_quantile),
            np.quantile(calibration_scores, threshold_quantile),
        )
    )
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
        "calibration_rows": len(calibration_data),
        "validation_rows": len(validation_data),
        "from": data.index.get_level_values("bucket").min().isoformat(),
        "to": data.index.get_level_values("bucket").max().isoformat(),
        "source": "NormalizedMetric",
        "window": WINDOW_FREQUENCY,
        "controlled_data_excluded": not include_controlled,
        "synthetic": bool(dataset_metadata.get("synthetic", False)),
        **dataset_metadata,
    }
    evaluation = {
        "method": "chronological_train_calibration_evaluation",
        "ground_truth_available": False,
        "false_positive_rate": None,
        "precision": None,
        "recall": None,
        "training_anomaly_rate": float((training_scores >= threshold).mean()),
        "calibration_anomaly_rate": float((calibration_scores >= threshold).mean()),
        "validation_anomaly_rate": float((validation_scores >= threshold).mean()),
        "validation_score_mean": float(validation_scores.mean()),
        "validation_score_std": float(validation_scores.std()),
        "validation_score_p95": float(np.quantile(validation_scores, 0.95)),
        "decision_threshold_quantile": threshold_quantile,
        "validation_stable_flag_rate": _stable_flag_rate(
            validation_data, validation_scores, threshold
        ),
        "temporal_policy": {
            "required_anomalous_windows": ANOMALY_REQUIRED_WINDOWS,
            "lookback_windows": ANOMALY_LOOKBACK_WINDOWS,
            "recovery_normal_windows": RECOVERY_REQUIRED_WINDOWS,
        },
    }
    try:
        with transaction.atomic():
            customer = Customer.objects.select_for_update().get(pk=customer_id)
            MLModelVersion.objects.filter(customer=customer, active=True).update(
                active=False
            )
            next_display_number = (
                MLModelVersion.objects.filter(customer=customer).aggregate(
                    maximum=Max("display_number")
                )["maximum"]
                or 0
            ) + 1
            model = MLModelVersion.objects.create(
                customer=customer,
                display_number=next_display_number,
                version=version_name,
                features=selected_features,
                preprocessing={
                    "imputer": "median",
                    "scaler": "RobustScaler",
                    "window": WINDOW_FREQUENCY,
                    "split": "chronological_60_20_20",
                    "feature_schema_version": FEATURE_SCHEMA_VERSION,
                    "missing_values": "median_imputation; missing is never zero",
                    "feature_coverage": feature_coverage,
                    "optional_missing_indicators": optional_features,
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
                    "calibration_rows": len(calibration_data),
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
        "features": selected_features,
    }


def infer_customer(
    customer_id, *, days=1, machine_ids=None, include_controlled=False
):
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
    model_features = list(model_version.features or BASE_FEATURES)
    data = dataset_for(
        customer,
        days=days,
        machine_ids=machine_ids,
        features=model_features,
        include_controlled=include_controlled,
    )
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
    schema_version = model_version.preprocessing.get("feature_schema_version", "1.0")
    if schema_version not in {"1.0", FEATURE_SCHEMA_VERSION}:
        return {
            "anomalies": 0,
            "reason": "unsupported_feature_schema",
            "model_version": model_version.version,
            "feature_schema_version": schema_version,
        }
    artifact_features = getattr(pipeline, "feature_names_in_", None)
    if artifact_features is not None and list(artifact_features) != model_features:
        return {
            "anomalies": 0,
            "reason": "artifact_feature_mismatch",
            "model_version": model_version.version,
        }
    scores = -pipeline.decision_function(data)
    created = 0
    resolved = 0
    insufficient_history = 0
    scored = pd.Series(scores, index=data.index)
    for machine_id, machine_scores in scored.groupby(level="machine_id", sort=False):
        machine_scores = machine_scores.sort_index(level="bucket")
        if len(machine_scores) < ANOMALY_LOOKBACK_WINDOWS:
            insufficient_history += 1
            continue
        recent_scores = machine_scores.iloc[-ANOMALY_LOOKBACK_WINDOWS:]
        recent_flags = recent_scores.to_numpy() >= model_version.decision_threshold
        latest_index = recent_scores.index[-1]
        bucket = latest_index[1]
        score = float(recent_scores.iloc[-1])
        stable_anomaly = bool(
            recent_flags[-1] and recent_flags.sum() >= ANOMALY_REQUIRED_WINDOWS
        )
        recovered = bool(
            len(recent_flags) >= RECOVERY_REQUIRED_WINDOWS
            and not recent_flags[-RECOVERY_REQUIRED_WINDOWS:].any()
        )
        machine = Machine.objects.get(pk=machine_id, customer=customer)
        if not stable_anomaly:
            if recovered:
                resolved += resolve_machine_alerts(
                    machine, "ML_ANOMALY", reason="ml_recovery_hysteresis"
                )
            continue
        feature_values = data.loc[latest_index]
        explanation = {
            "features": {
                key: (None if pd.isna(value) else float(value))
                for key, value in feature_values.to_dict().items()
            },
            "method": "Isolation Forest decision_function",
            "synthetic": bool(model_version.dataset.get("synthetic", False)),
            "feature_schema_version": model_version.preprocessing.get(
                "feature_schema_version", "1.0"
            ),
            "missing_features": [
                key for key, value in feature_values.items() if pd.isna(value)
            ],
            "temporal_evidence": {
                "anomalous_windows": int(recent_flags.sum()),
                "lookback_windows": ANOMALY_LOOKBACK_WINDOWS,
                "required_windows": ANOMALY_REQUIRED_WINDOWS,
            },
        }
        anomaly, anomaly_created = Anomaly.objects.get_or_create(
            customer=customer,
            machine=machine,
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
            source_key="ml:active",
            cooldown_seconds=300,
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
        "machines_evaluated": scored.index.get_level_values("machine_id").nunique(),
        "insufficient_history": insufficient_history,
        "resolved_alerts": resolved,
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
