from django.utils import timezone

from accounts.models import User
from common.testing import TenantAPITestCase
from metrics.models import NormalizedMetric
from monitoring.alert_service import create_or_update_alert
from monitoring.models import Anomaly, Recommendation
from monitoring.recommendations import build_recommendation


class AnomalyAPITests(TenantAPITestCase):
    def setUp(self):
        self.machine = self.create_machine()
        self.metric = NormalizedMetric.objects.create(
            timestamp=timezone.now(),
            customer=self.customer_a,
            environment=self.environment_a,
            machine=self.machine,
            source_type="WINDOWS",
            metric_name="system.cpu.utilization",
            metric_value=99,
            unit="%",
        )
        self.anomaly = Anomaly.objects.create(
            customer=self.customer_a,
            machine=self.machine,
            metric=self.metric,
            window_start=timezone.now(),
            score=0.91,
            threshold=0.75,
            model_version="iforest-test",
            explanation={"features": {"cpu": 99}, "synthetic": False},
        )

    def test_model_serializer_and_api_persist_anomaly_context(self):
        self.authenticate()
        response = self.client.get(f"/api/anomalies/{self.anomaly.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["machine"], self.machine.pk)
        self.assertEqual(response.data["metric"], self.metric.pk)
        self.assertEqual(response.data["score"], 0.91)
        self.assertEqual(response.data["model_version"], "iforest-test")
        self.assertEqual(response.data["hostname"], self.machine.hostname)
        self.assertIn("detected_at", response.data)

    def test_acknowledgement_is_writable_only_by_manager(self):
        self.authenticate()
        acknowledged = self.client.patch(
            f"/api/anomalies/{self.anomaly.pk}/",
            {"acknowledged": True},
            format="json",
        )
        self.assertEqual(acknowledged.status_code, 200)
        self.assertTrue(acknowledged.data["acknowledged"])
        self.authenticate(self.users_by_role[User.Role.VIEWER])
        self.assertEqual(
            self.client.patch(
                f"/api/anomalies/{self.anomaly.pk}/",
                {"acknowledged": False},
                format="json",
            ).status_code,
            403,
        )

    def test_anomaly_api_is_read_only_for_creation_and_tenant_isolated(self):
        foreign_machine = self.create_machine(
            customer=self.customer_b,
            environment=self.environment_b,
            external_id="foreign-anomaly-machine",
            hostname="foreign-anomaly-machine",
        )
        foreign = Anomaly.objects.create(
            customer=self.customer_b,
            machine=foreign_machine,
            score=0.99,
            threshold=0.8,
            model_version="foreign-model",
        )
        self.authenticate()
        ids = {row["id"] for row in self.client.get("/api/anomalies/").data["results"]}
        self.assertIn(str(self.anomaly.pk), ids)
        self.assertNotIn(str(foreign.pk), ids)
        self.assertEqual(self.client.get(f"/api/anomalies/{foreign.pk}/").status_code, 404)
        self.assertEqual(self.client.post("/api/anomalies/", {}, format="json").status_code, 405)


class RecommendationTests(TenantAPITestCase):
    def test_catalog_and_fallback_cover_operational_contexts_non_destructively(self):
        cases = (
            ("system.cpu.utilization", {"source_type": "WINDOWS"}),
            ("system.memory.utilization", {"source_type": "WINDOWS"}),
            ("system.disk.utilization", {"source_type": "WINDOWS"}),
            ("system.network.latency", {"source_type": "WINDOWS"}),
            ("machine.online", {"source_type": "WINDOWS"}),
            ("windows.service.state", {"source_type": "WINDOWS"}),
            (
                "system.cpu.utilization",
                {"source_type": "VMWARE", "metric_metadata": {"resource_kind": "HOST"}},
            ),
            (
                "system.cpu.utilization",
                {"source_type": "VMWARE", "metric_metadata": {"resource_kind": "VM"}},
            ),
            (
                "system.memory.utilization",
                {"source_type": "HYPERV", "metric_metadata": {"resource_kind": "HOST"}},
            ),
            (
                "system.memory.utilization",
                {"source_type": "HYPERV", "metric_metadata": {"resource_kind": "VM"}},
            ),
        )
        for metric, context in cases:
            recommendation = build_recommendation(metric, context)
            with self.subTest(metric=metric, context=context):
                self.assertTrue(recommendation["diagnosis_hints"])
                self.assertTrue(recommendation["actions"])
                self.assertTrue(recommendation["rationale"])
                self.assertFalse(recommendation["destructive"])

    def test_vmware_and_hyperv_host_recommendations_are_contextualized(self):
        vmware = build_recommendation(
            "system.cpu.utilization",
            {"source_type": "VMWARE", "metric_metadata": {"resource_kind": "HOST"}},
        )
        hyperv = build_recommendation(
            "system.memory.utilization",
            {"source_type": "HYPERV", "metric_metadata": {"resource_kind": "HOST"}},
        )
        self.assertTrue(any("VM" in hint for hint in vmware["diagnosis_hints"]))
        self.assertTrue(any("allocations" in hint for hint in hyperv["diagnosis_hints"]))

    def test_structured_recommendation_is_exposed_only_with_own_alert(self):
        machine = self.create_machine()
        alert, _ = create_or_update_alert(
            machine=machine,
            alert_type="RULE_THRESHOLD",
            severity="HIGH",
            source="WINDOWS",
            message="CPU high",
            context={"metric_name": "system.cpu.utilization", "source_type": "WINDOWS"},
            source_key="recommendation",
        )
        self.authenticate()
        response = self.client.get(f"/api/alerts/{alert.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["structured_recommendation"]["destructive"])
        self.assertTrue(response.data["structured_recommendation"]["actions"])
        self.assertEqual(Recommendation.objects.filter(alert=alert).count(), 1)
