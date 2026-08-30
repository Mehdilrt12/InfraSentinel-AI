import tempfile
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
from django.utils import timezone

from common.testing import TenantAPITestCase
from metrics.models import NormalizedMetric
from ml_engine.models import MLModelVersion
from ml_engine.pipeline import (
    ANOMALY_LOOKBACK_WINDOWS,
    BASE_FEATURES,
    FEATURES,
    PARAMETERS,
    dataset_for,
    infer_customer,
    train_customer_model,
)


class NamedFeaturePipeline:
    """Small serializable artifact exposing sklearn's feature-name contract."""

    def __init__(self, feature_names, decisions=None):
        self.feature_names_in_ = np.asarray(feature_names, dtype=object)
        self.decisions = decisions or [0.9] * ANOMALY_LOOKBACK_WINDOWS

    def decision_function(self, data):
        return np.asarray(self.decisions[: len(data)], dtype=float)


class MLFeatureSchemaCompatibilityTests(TenantAPITestCase):
    def setUp(self):
        self.machine = self.create_machine()
        self.now = pd.Timestamp(timezone.now()).floor("1min")

    def _frame(self, features, rows=ANOMALY_LOOKBACK_WINDOWS):
        index = pd.MultiIndex.from_tuples(
            [
                (self.machine.pk, self.now - pd.Timedelta(minutes=rows - offset))
                for offset in range(rows)
            ],
            names=["machine_id", "bucket"],
        )
        return pd.DataFrame(
            np.full((rows, len(features)), 10.0), index=index, columns=features
        )

    def _model(self, directory, *, model_features, artifact_features, preprocessing=None):
        artifact = Path(directory) / "named-features.joblib"
        joblib.dump(NamedFeaturePipeline(artifact_features), artifact)
        return MLModelVersion.objects.create(
            customer=self.customer_a,
            display_number=1,
            version="feature-contract",
            features=model_features,
            preprocessing=preprocessing or {},
            parameters=PARAMETERS,
            decision_threshold=0.5,
            artifact_path=artifact.name,
            trained_at=timezone.now(),
            status=MLModelVersion.Status.READY,
            active=True,
        )

    def test_historical_schema_uses_its_saved_base_feature_contract(self):
        """A schema-1.0 artifact remains usable without the newer GPU columns."""

        with tempfile.TemporaryDirectory() as directory:
            model = self._model(
                directory,
                model_features=BASE_FEATURES,
                artifact_features=BASE_FEATURES,
                preprocessing={},
            )
            frame = self._frame(BASE_FEATURES)
            with (
                patch("ml_engine.pipeline.MODEL_DIR", Path(directory)),
                patch("ml_engine.pipeline.dataset_for", return_value=frame) as dataset,
            ):
                result = infer_customer(self.customer_a.pk)

        self.assertEqual(result["model_version"], model.version)
        self.assertEqual(result["evaluated"], ANOMALY_LOOKBACK_WINDOWS)
        self.assertEqual(result["anomalies"], 0)
        self.assertEqual(dataset.call_args.kwargs["features"], BASE_FEATURES)

    def test_artifact_feature_names_must_match_database_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            model = self._model(
                directory,
                model_features=BASE_FEATURES,
                artifact_features=list(reversed(BASE_FEATURES)),
                preprocessing={"feature_schema_version": "1.0"},
            )
            frame = self._frame(BASE_FEATURES)
            with (
                patch("ml_engine.pipeline.MODEL_DIR", Path(directory)),
                patch("ml_engine.pipeline.dataset_for", return_value=frame),
            ):
                result = infer_customer(self.customer_a.pk)

        self.assertEqual(
            result,
            {
                "anomalies": 0,
                "reason": "artifact_feature_mismatch",
                "model_version": model.version,
            },
        )

    def test_gpu_missingness_is_encoded_separately_from_real_zero(self):
        """Median imputation must not erase the distinction between absent and 0 %."""

        rows = 240
        index = pd.MultiIndex.from_tuples(
            [
                (self.machine.pk, self.now - pd.Timedelta(minutes=rows - offset))
                for offset in range(rows)
            ],
            names=["machine_id", "bucket"],
        )
        frame = pd.DataFrame(index=index, columns=FEATURES, dtype=float)
        for offset, feature in enumerate(BASE_FEATURES):
            frame[feature] = 10.0 + offset + np.arange(rows) % 5
        frame["system.gpu.utilization"] = np.concatenate(
            [np.arange(220, dtype=float) % 80, np.full(20, np.nan)]
        )

        with tempfile.TemporaryDirectory() as directory:
            with (
                patch("ml_engine.pipeline.MODEL_DIR", Path(directory)),
                patch("ml_engine.pipeline.dataset_for", return_value=frame),
                patch.dict(PARAMETERS, {"n_estimators": 5}),
            ):
                trained = train_customer_model(self.customer_a.pk)
            model = MLModelVersion.objects.get(pk=trained["model_id"])
            artifact = joblib.load(Path(directory) / model.artifact_path)

        self.assertIn("system.gpu.utilization", model.features)
        self.assertIn(
            "system.gpu.utilization",
            model.preprocessing["optional_missing_indicators"],
        )
        present_zero = pd.DataFrame(
            [{feature: 10.0 for feature in model.features}], columns=model.features
        )
        present_zero["system.gpu.utilization"] = 0.0
        missing = present_zero.copy()
        missing["system.gpu.utilization"] = np.nan

        preprocessor = artifact.named_steps["preprocessor"]
        encoded_zero = preprocessor.transform(present_zero)
        encoded_missing = preprocessor.transform(missing)
        self.assertEqual(encoded_zero[0, -1], 0)
        self.assertEqual(encoded_missing[0, -1], 1)
        self.assertFalse(np.array_equal(encoded_zero, encoded_missing))

    def test_gpu_memory_gauge_uses_bucket_maximum_not_sample_sum(self):
        bucket = self.now - pd.Timedelta(minutes=2)
        for seconds, value in ((5, 100.0), (35, 250.0)):
            NormalizedMetric.objects.create(
                timestamp=(bucket + pd.Timedelta(seconds=seconds)).to_pydatetime(),
                customer=self.customer_a,
                environment=self.environment_a,
                machine=self.machine,
                source_type="WINDOWS",
                metric_name="system.gpu.memory.used",
                metric_value=value,
                unit="bytes",
            )

        frame = dataset_for(
            self.customer_a,
            days=1,
            features=["system.gpu.memory.used"],
        )

        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.iloc[0]["system.gpu.memory.used"], 250.0)
