from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.utils import timezone

from accounts.models import User
from common.testing import TenantAPITestCase
from metrics.models import NormalizedMetric
from ml_engine.models import MLModelVersion
from ml_engine.predictive import analyze_machine_trends
from ml_engine.tasks import analyze_recent_metrics
from monitoring.models import AuditLog, MonitoringRule


class MLAPITests(TenantAPITestCase):
    def test_train_and_evaluate_validate_auth_role_customer_and_parameters(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.post("/api/ml/models/train/", {}).status_code, 401)
        self.authenticate(self.users_by_role[User.Role.VIEWER])
        self.assertEqual(
            self.client.post("/api/ml/models/train/", {}, format="json").status_code,
            403,
        )
        self.authenticate()
        for value in ("bad", 0, 3651):
            with self.subTest(days=value):
                self.assertEqual(
                    self.client.post(
                        "/api/ml/models/train/", {"days": value}, format="json"
                    ).status_code,
                    400,
                )
        with (
            patch("common.api.train_model.delay", return_value=SimpleNamespace(id="train-task")),
            patch(
                "common.api.evaluate_model.delay",
                return_value=SimpleNamespace(id="evaluate-task"),
            ),
        ):
            trained = self.client.post(
                "/api/ml/models/train/",
                {"days": 30, "idempotency_key": "train-key"},
                format="json",
            )
            evaluated = self.client.post(
                "/api/ml/models/evaluate/", {"days": 7}, format="json"
            )
        self.assertEqual(trained.status_code, 202)
        self.assertEqual(evaluated.status_code, 202)
        self.assertEqual(trained.data["task_id"], "train-task")
        self.assertEqual(evaluated.data["task_id"], "evaluate-task")
        self.assertEqual(
            AuditLog.objects.filter(
                customer=self.customer_a,
                action__in=[
                    AuditLog.Action.MODEL_TRAINING_QUEUED,
                    AuditLog.Action.MODEL_EVALUATION_QUEUED,
                ],
            ).count(),
            2,
        )

    def test_model_api_hides_artifact_and_is_customer_isolated(self):
        own = MLModelVersion.objects.create(
            customer=self.customer_a,
            display_number=1,
            version="own-model",
            artifact_path="secret/path.joblib",
            status=MLModelVersion.Status.READY,
        )
        foreign = MLModelVersion.objects.create(
            customer=self.customer_b,
            display_number=1,
            version="foreign-model",
            artifact_path="foreign/path.joblib",
            status=MLModelVersion.Status.READY,
        )
        self.authenticate()
        response = self.client.get("/api/ml/models/")
        ids = {row["id"] for row in response.data["results"]}
        self.assertIn(str(own.pk), ids)
        self.assertNotIn(str(foreign.pk), ids)
        self.assertNotIn("artifact_path", response.data["results"][0])
        self.assertEqual(self.client.get(f"/api/ml/models/{foreign.pk}/").status_code, 404)

    def test_model_display_number_is_stable_and_preserves_technical_version(self):
        oldest = MLModelVersion.objects.create(
            customer=self.customer_a,
            display_number=1,
            version="iforest-20260827T230000-oldest",
            algorithm="IsolationForest",
            status=MLModelVersion.Status.READY,
        )
        latest = MLModelVersion.objects.create(
            customer=self.customer_a,
            display_number=2,
            version="iforest-20260827T234946-0dbe1975",
            algorithm="IsolationForest",
            status=MLModelVersion.Status.READY,
            active=True,
        )
        MLModelVersion.objects.create(
            customer=self.customer_b,
            display_number=1,
            version="iforest-foreign",
            status=MLModelVersion.Status.READY,
        )
        self.authenticate()

        first = self.client.get("/api/ml/models/")
        second = self.client.get("/api/ml/models/")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["results"], second.data["results"])
        self.assertEqual(
            [row["display_number"] for row in first.data["results"]],
            [2, 1],
        )

        rows = {row["version"]: row for row in first.data["results"]}
        self.assertEqual(rows[oldest.version]["display_number"], 1)
        self.assertEqual(rows[latest.version]["display_number"], 2)
        self.assertEqual(rows[latest.version]["version"], latest.version)
        self.assertTrue(rows[latest.version]["active"])

        detail = self.client.get(f"/api/ml/models/{latest.pk}/")
        self.assertEqual(detail.data["display_number"], 2)
        self.assertEqual(detail.data["version"], latest.version)
        self.assertTrue(detail.data["active"])


class PredictiveAnalysisTests(TenantAPITestCase):
    def setUp(self):
        self.machine = self.create_machine()

    def _seed(self, values, *, metric="system.cpu.utilization", minutes=15):
        start = timezone.now() - timedelta(minutes=minutes * len(values))
        for index, value in enumerate(values):
            NormalizedMetric.objects.create(
                timestamp=start + timedelta(minutes=index * minutes),
                customer=self.customer_a,
                environment=self.environment_a,
                machine=self.machine,
                source_type="WINDOWS",
                metric_name=metric,
                metric_value=value,
                unit="%",
            )

    def test_flat_increasing_decreasing_and_noisy_trends(self):
        cases = (
            ("flat", [50, 50, 50, 50, 50], "STABLE"),
            ("increasing", [10, 20, 30, 40, 50], "INCREASING"),
            ("decreasing", [50, 40, 30, 20, 10], "DECREASING"),
            ("noisy", [50, 55, 45, 45, 55, 50], "STABLE"),
        )
        for index, (label, values, expected) in enumerate(cases):
            metric = f"test.trend.{index}"
            self._seed(values, metric=metric)
            result = analyze_machine_trends(self.machine, hours=24)
            trend = next(item for item in result if item["metric_name"] == metric)
            with self.subTest(label=label):
                self.assertEqual(trend["trend"], expected)
                self.assertTrue(trend["is_estimate"])
                self.assertIn("certitude", trend["disclaimer"])

    def test_insufficient_history_is_omitted(self):
        self._seed([10, 20])
        self.assertEqual(analyze_machine_trends(self.machine, hours=24), [])

    def test_threshold_crossing_estimate_and_risk_are_computed(self):
        MonitoringRule.objects.create(
            customer=self.customer_a,
            machine=self.machine,
            name="CPU forecast",
            metric="system.cpu.utilization",
            operator=">=",
            threshold=90,
            severity="HIGH",
        )
        self._seed([40, 50, 60, 70, 80], minutes=30)
        trend = analyze_machine_trends(self.machine, hours=6)[0]
        self.assertEqual(trend["trend"], "INCREASING")
        self.assertIsNotNone(trend["estimated_threshold_breach_at"])
        self.assertGreater(trend["risk_score"], 0)
        self.assertEqual(trend["rolling_average"], 60)
        self.assertGreater(trend["rate_of_change_per_hour"], 0)

    def test_recent_analysis_schedules_only_active_customers(self):
        self.customer_b.active = False
        self.customer_b.save(update_fields=["active"])
        with patch("ml_engine.tasks.analyze_customer.delay") as delay:
            result = analyze_recent_metrics()
        self.assertEqual(result, {"scheduled": 1})
        delay.assert_called_once_with(str(self.customer_a.pk))
