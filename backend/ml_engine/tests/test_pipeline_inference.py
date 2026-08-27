import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
from django.db import IntegrityError, transaction
from django.utils import timezone

from common.testing import TenantAPITestCase
from metrics.models import NormalizedMetric
from ml_engine.evaluation import evaluate_detection_strategies
from ml_engine.models import MLModelVersion
from ml_engine.pipeline import (
    FEATURES,
    PARAMETERS,
    dataset_for,
    infer_customer,
    metadata_json,
    train_customer_model,
)
from monitoring.alert_service import create_or_update_alert
from monitoring.models import Alert, Anomaly
from realtime.models import RealtimeEvent


class FixedScorePipeline:
    def __init__(self, decisions):
        self.decisions = decisions

    def decision_function(self, data):
        return np.asarray(self.decisions[: len(data)], dtype=float)


class MLDatasetAndTrainingTests(TenantAPITestCase):
    def setUp(self):
        self.machine = self.create_machine()

    def test_dataset_uses_only_normalized_metrics_and_five_minute_windows(self):
        start = (
            pd.Timestamp(timezone.now()).floor("5min").to_pydatetime()
            - timedelta(minutes=10)
        )
        for minute, cpu, ram in ((0, 10, 20), (1, 30, 40), (6, 50, 60)):
            for name, value in (
                ("system.cpu.utilization", cpu),
                ("system.memory.utilization", ram),
            ):
                NormalizedMetric.objects.create(
                    timestamp=start + timedelta(minutes=minute),
                    customer=self.customer_a,
                    environment=self.environment_a,
                    machine=self.machine,
                    source_type="WINDOWS",
                    metric_name=name,
                    metric_value=value,
                    unit="%",
                )
        frame = dataset_for(self.customer_a, days=1)
        self.assertEqual(list(frame.columns), FEATURES)
        self.assertEqual(len(frame), 2)
        self.assertEqual(frame.iloc[0]["system.cpu.utilization"], 20)
        self.assertEqual(frame.index.names, ["machine_id", "bucket"])

    def test_insufficient_real_dataset_is_rejected_without_model(self):
        with self.assertRaisesRegex(ValueError, "20 fenêtres"):
            train_customer_model(self.customer_a.pk, days=1)
        self.assertFalse(MLModelVersion.objects.filter(customer=self.customer_a).exists())

    def test_scientific_parameters_are_fixed_and_model_metadata_is_explainable(self):
        self.assertEqual(PARAMETERS["n_estimators"], 200)
        self.assertEqual(PARAMETERS["contamination"], 0.02)
        self.assertEqual(PARAMETERS["random_state"], 42)
        model = MLModelVersion.objects.create(
            customer=self.customer_a,
            version="metadata-test",
            features=FEATURES,
            parameters=PARAMETERS,
            dataset={"source": "NormalizedMetric", "synthetic": False},
            evaluation_metrics={"ground_truth_available": False},
        )
        payload = metadata_json(model)
        self.assertIn('"random_state": 42', payload)
        self.assertIn('"synthetic": false', payload.lower())

    def test_postgresql_enforces_one_active_model_per_customer(self):
        MLModelVersion.objects.create(
            customer=self.customer_a,
            version="active-one",
            status=MLModelVersion.Status.READY,
            active=True,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            MLModelVersion.objects.create(
                customer=self.customer_a,
                version="active-two",
                status=MLModelVersion.Status.READY,
                active=True,
            )

    def test_evaluation_matches_rule_and_ml_events_without_inventing_labels(self):
        alert, _ = create_or_update_alert(
            machine=self.machine,
            alert_type="RULE_THRESHOLD",
            severity="HIGH",
            source="WINDOWS",
            message="rule",
            source_key="evaluation",
        )
        anomaly = Anomaly.objects.create(
            customer=self.customer_a,
            machine=self.machine,
            score=0.9,
            threshold=0.8,
            model_version="evaluation-model",
        )
        result = evaluate_detection_strategies(self.customer_a.pk, days=1)
        self.assertEqual(result["rule_incidents"], 1)
        self.assertEqual(result["ml_anomalies"], 1)
        self.assertEqual(result["hybrid_overlaps"], 1)
        self.assertFalse(result["ground_truth_available"])
        self.assertIsNone(result["precision"])
        self.assertIsNone(result["recall"])
        self.assertIsNotNone(alert.pk)
        self.assertIsNotNone(anomaly.pk)


class MLInferenceTests(TenantAPITestCase):
    def setUp(self):
        self.machine = self.create_machine()
        self.now = pd.Timestamp(timezone.now()).floor("5min")

    def _frame(self, values=None):
        rows = values or [
            [10, 20, 30, 100, 100, 5],
            [99, np.nan, 95, 10_000_000, 10_000_000, 500],
        ]
        index = pd.MultiIndex.from_tuples(
            [
                (self.machine.pk, self.now),
                (self.machine.pk, self.now + pd.Timedelta(minutes=5)),
            ][: len(rows)],
            names=["machine_id", "bucket"],
        )
        return pd.DataFrame(rows, index=index, columns=FEATURES)

    def _model(self, directory, decisions=(-0.1, -0.9), **overrides):
        artifact = Path(directory) / "model.joblib"
        joblib.dump(FixedScorePipeline(list(decisions)), artifact)
        values = {
            "customer": self.customer_a,
            "version": "iforest-inference",
            "features": FEATURES,
            "parameters": PARAMETERS,
            "decision_threshold": 0.5,
            "artifact_path": artifact.name,
            "trained_at": timezone.now(),
            "status": MLModelVersion.Status.READY,
            "active": True,
        }
        values.update(overrides)
        return MLModelVersion.objects.create(**values)

    def test_saved_model_loads_scores_classifies_and_persists_anomaly(self):
        with tempfile.TemporaryDirectory() as directory:
            self._model(directory)
            frame = self._frame()
            with (
                patch("ml_engine.pipeline.MODEL_DIR", Path(directory)),
                patch("ml_engine.pipeline.dataset_for", return_value=frame),
            ):
                result = infer_customer(self.customer_a.pk)
                replay = infer_customer(self.customer_a.pk)
        self.assertEqual(result["evaluated"], 2)
        self.assertEqual(result["anomalies"], 1)
        self.assertEqual(replay["anomalies"], 0)
        anomaly = Anomaly.objects.get(customer=self.customer_a)
        self.assertGreaterEqual(anomaly.score, anomaly.threshold)
        self.assertIsNone(
            anomaly.explanation["features"]["system.memory.utilization"]
        )
        alert = Alert.objects.get(type="ML_ANOMALY")
        self.assertEqual(alert.anomaly_score, anomaly.score)
        self.assertTrue(
            RealtimeEvent.objects.filter(
                customer=self.customer_a, event_type="anomaly.detected"
            ).exists()
        )

    def test_normal_input_does_not_create_anomaly(self):
        with tempfile.TemporaryDirectory() as directory:
            self._model(directory, decisions=(0.9, 0.8))
            with (
                patch("ml_engine.pipeline.MODEL_DIR", Path(directory)),
                patch("ml_engine.pipeline.dataset_for", return_value=self._frame()),
            ):
                result = infer_customer(self.customer_a.pk)
        self.assertEqual(result["anomalies"], 0)
        self.assertFalse(Anomaly.objects.exists())

    def test_absent_model_empty_input_and_missing_artifact_have_explicit_fallbacks(self):
        self.assertEqual(
            infer_customer(self.customer_a.pk),
            {"anomalies": 0, "reason": "no_active_model"},
        )
        with tempfile.TemporaryDirectory() as directory:
            model = self._model(directory)
            empty = pd.DataFrame(columns=FEATURES)
            with patch("ml_engine.pipeline.dataset_for", return_value=empty):
                self.assertEqual(
                    infer_customer(self.customer_a.pk),
                    {"anomalies": 0, "reason": "no_recent_data"},
                )
            model.artifact_path = "missing.joblib"
            model.save(update_fields=["artifact_path"])
            with (
                patch("ml_engine.pipeline.MODEL_DIR", Path(directory)),
                patch("ml_engine.pipeline.dataset_for", return_value=self._frame()),
            ):
                missing = infer_customer(self.customer_a.pk)
        self.assertEqual(missing["reason"], "model_artifact_missing")
        self.assertEqual(missing["model_version"], model.version)

    def test_corrupted_model_failure_is_not_misreported_as_valid_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            self._model(directory)
            with (
                patch("ml_engine.pipeline.MODEL_DIR", Path(directory)),
                patch("ml_engine.pipeline.dataset_for", return_value=self._frame()),
                patch("ml_engine.pipeline.joblib.load", side_effect=ValueError("corrupt artifact")),
            ):
                with self.assertRaisesRegex(ValueError, "corrupt artifact"):
                    infer_customer(self.customer_a.pk)
        self.assertFalse(Anomaly.objects.exists())
