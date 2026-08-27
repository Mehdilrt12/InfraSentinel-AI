import math
import tempfile
import threading
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import Mock, patch

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Customer, User
from async_tasks.models import TaskRun
from hyperv_connector.collector import (
    HyperVCollectionError,
    HyperVCollector,
    HyperVConfig,
)
from integrations.services import persist_collection
from inventory.models import (
    Agent,
    Environment,
    IntegrationEndpoint,
    Machine,
    VirtualAsset,
)
from inventory.services import create_enrollment_code, enroll_agent
from metrics.models import NormalizedMetric
from metrics.normalization import normalize_metric
from ml_engine.evaluation import evaluate_detection_strategies
from ml_engine.models import MLModelVersion
from ml_engine.pipeline import train_customer_model
from ml_engine.predictive import analyze_machine_trends
from monitoring.alert_service import create_or_update_alert
from monitoring.engine import evaluate_metric
from monitoring.models import Alert, MonitoringRule, RuleState
from notifications.models import (
    NotificationDelivery,
    NotificationEvent,
    NotificationPreference,
)
from notifications.services import deliver_notification, dispatch_due_notifications
from vmware_connector.collector import VMwareCollector, VMwareConfig


class ReviewBase(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="Review", slug="review")
        self.other = Customer.objects.create(name="Other", slug="other")
        self.environment = Environment.objects.create(
            customer=self.customer, name="Windows", kind=Environment.Kind.WINDOWS
        )
        self.machine = Machine.objects.create(
            customer=self.customer,
            environment=self.environment,
            source_type=Environment.Kind.WINDOWS,
            external_id="review-host",
            hostname="review-host",
        )
        self.user = User.objects.create_user(
            username="review-admin",
            email="review@example.test",
            password="CorrectHorse12!",
            customer=self.customer,
            role=User.Role.ADMIN,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)


class TenantAndConnectorReviewTests(ReviewBase):
    def test_logout_blacklists_refresh_token(self):
        anonymous = APIClient()
        tokens = anonymous.post(
            "/api/auth/token/",
            {"email": self.user.email, "password": "CorrectHorse12!"},
            format="json",
        )
        self.assertEqual(tokens.status_code, 200)
        logged_out = anonymous.post(
            "/api/auth/logout/", {"refresh": tokens.data["refresh"]}, format="json"
        )
        self.assertEqual(logged_out.status_code, 200)
        refreshed = anonymous.post(
            "/api/auth/refresh/", {"refresh": tokens.data["refresh"]}, format="json"
        )
        self.assertEqual(refreshed.status_code, 401)

    def test_task_runs_are_tenant_isolated(self):
        mine = TaskRun.objects.create(
            customer=self.customer,
            task_name="review.mine",
            idempotency_key="mine",
        )
        TaskRun.objects.create(
            customer=self.other,
            task_name="review.other",
            idempotency_key="other",
        )
        response = self.client.get("/api/tasks/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data["results"]], [mine.pk])

    def test_tenant_cannot_reference_arbitrary_server_secret(self):
        vmware = Environment.objects.create(
            customer=self.customer, name="VMware", kind=Environment.Kind.VMWARE
        )
        payload = {
            "environment": str(vmware.pk),
            "kind": "VMWARE",
            "name": "vCenter",
            "endpoint": "https://vc.example.test",
            "username": "svc",
            "secret_ref": "POSTGRES_PASSWORD",
        }
        rejected = self.client.post("/api/connectors/", payload, format="json")
        self.assertEqual(rejected.status_code, 400)
        payload["secret_ref"] = (
            f"INFRASENTINEL_CUSTOMER_{self.customer.pk.hex.upper()}_VCENTER_PASSWORD"
        )
        accepted = self.client.post("/api/connectors/", payload, format="json")
        self.assertEqual(accepted.status_code, 201, accepted.data)
        self.assertNotIn("secret_ref", accepted.data)

    def test_connector_environment_and_transport_are_validated(self):
        payload = {
            "environment": str(self.environment.pk),
            "kind": "VMWARE",
            "name": "bad-vcenter",
            "endpoint": "http://vc.example.test",
            "username": "svc",
            "secret_ref": f"INFRASENTINEL_CUSTOMER_{self.customer.pk.hex.upper()}_VC",
        }
        response = self.client.post("/api/connectors/", payload, format="json")
        self.assertEqual(response.status_code, 400)


class AgentApiReviewTests(ReviewBase):
    def test_enrollment_heartbeat_ingestion_and_revocation(self):
        code = create_enrollment_code(self.customer, self.environment)
        anonymous = APIClient()
        enrolled = anonymous.post(
            "/api/agent/enroll/",
            {
                "enrollment_code": code,
                "external_id": "agent-e2e",
                "hostname": "agent-e2e",
                "ip_address": "127.0.0.2",
                "os_information": {"system": "Windows"},
                "version": "2.0.0",
            },
            format="json",
        )
        self.assertEqual(enrolled.status_code, 201, enrolled.data)
        token = enrolled.data["token"]
        headers = {"HTTP_X_AGENT_TOKEN": token}
        heartbeat = anonymous.post(
            "/api/agent/heartbeat/", {"version": "2.0.1"}, format="json", **headers
        )
        self.assertEqual(heartbeat.status_code, 200)
        ingested = anonymous.post(
            "/api/agent/metrics/",
            {
                "machine_id": str(enrolled.data["machine_id"]),
                "metrics": [
                    {
                        "metric_name": "cpu.percent",
                        "metric_value": 12.5,
                        "unit": "%",
                        "idempotency_key": "agent-e2e-1",
                    }
                ],
            },
            format="json",
            **headers,
        )
        self.assertEqual(ingested.status_code, 202, ingested.data)
        self.assertTrue(
            NormalizedMetric.objects.filter(
                machine_id=enrolled.data["machine_id"],
                metric_name="system.cpu.utilization",
            ).exists()
        )
        Agent.objects.filter(pk=enrolled.data["agent_id"]).update(enabled=False)
        revoked = anonymous.post("/api/agent/heartbeat/", {}, format="json", **headers)
        self.assertEqual(revoked.status_code, 401)

    def test_invalid_enrollment_metadata_is_rejected(self):
        response = APIClient().post(
            "/api/agent/enroll/",
            {
                "enrollment_code": "invalid",
                "external_id": "host",
                "hostname": "host",
                "ip_address": "999.999.999.999",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)


class MetricAndRuleReviewTests(ReviewBase):
    def _metric(self, name, value, metadata=None, when=None, unit=""):
        return NormalizedMetric.objects.create(
            timestamp=when or timezone.now(),
            customer=self.customer,
            environment=self.environment,
            machine=self.machine,
            source_type="WINDOWS",
            metric_name=name,
            metric_value=value,
            unit=unit,
            metadata=metadata or {},
        )

    def test_rate_units_are_converted_and_non_finite_values_rejected(self):
        normalized = normalize_metric(
            {
                "metric_name": "network.in",
                "metric_value": 2,
                "unit": "KiB/s",
            },
            source_type="VMWARE",
            customer=self.customer,
            environment=self.environment,
            machine=self.machine,
        )
        self.assertEqual(normalized["metric_value"], 2048)
        self.assertEqual(normalized["unit"], "bytes/s")
        self.assertEqual(normalized["metadata"]["original_unit"], "KiB/s")
        for value in [math.nan, math.inf, -math.inf]:
            with self.assertRaises(ValidationError):
                normalize_metric(
                    {"metric_name": "cpu", "metric_value": value},
                    source_type="WINDOWS",
                    customer=self.customer,
                    environment=self.environment,
                    machine=self.machine,
                )

    def test_future_timestamp_is_rejected(self):
        with self.assertRaises(ValidationError):
            normalize_metric(
                {
                    "metric_name": "cpu",
                    "metric_value": 1,
                    "timestamp": (timezone.now() + timedelta(hours=1)).isoformat(),
                },
                source_type="WINDOWS",
                customer=self.customer,
                environment=self.environment,
                machine=self.machine,
            )

    def test_rule_state_is_dimensioned_and_alert_resolves_on_recovery(self):
        rule = MonitoringRule.objects.create(
            customer=self.customer,
            name="Service arrêté",
            metric="windows.service.state",
            operator="==",
            threshold=0,
            duration_seconds=0,
            severity="HIGH",
        )
        evaluate_metric(
            self._metric("windows.service.state", 0, {"service_name": "MSSQL"})
        )
        evaluate_metric(
            self._metric("windows.service.state", 0, {"service_name": "W3SVC"})
        )
        self.assertEqual(RuleState.objects.filter(rule=rule).count(), 2)
        self.assertEqual(Alert.objects.exclude(status="RESOLVED").count(), 2)
        evaluate_metric(
            self._metric("windows.service.state", 1, {"service_name": "MSSQL"})
        )
        self.assertEqual(Alert.objects.filter(status="RESOLVED").count(), 1)
        self.assertEqual(Alert.objects.exclude(status="RESOLVED").count(), 1)


class IntegrationPersistenceReviewTests(ReviewBase):
    def setUp(self):
        super().setUp()
        self.vmware = Environment.objects.create(
            customer=self.customer, name="vSphere", kind=Environment.Kind.VMWARE
        )
        self.connector = IntegrationEndpoint.objects.create(
            customer=self.customer,
            environment=self.vmware,
            kind="VMWARE",
            name="vCenter",
            endpoint="https://vc.example.test",
            username="svc",
            secret_ref="INFRASENTINEL_CONNECTOR_VCENTER",
        )

    def test_datastore_is_persisted_and_missing_assets_become_unavailable(self):
        payload = {
            "collected_at": timezone.now().isoformat(),
            "hosts": [],
            "vms": [],
            "datastores": [
                {
                    "external_id": "datastore-1",
                    "kind": "DATASTORE",
                    "name": "SAN01",
                    "state": "AVAILABLE",
                    "metrics": [
                        {
                            "metric_name": "vmware.datastore.utilization",
                            "metric_value": 72,
                            "unit": "%",
                        }
                    ],
                }
            ],
        }
        result = persist_collection(self.connector, payload)
        self.assertEqual(result, {"hosts": 0, "vms": 0, "datastores": 1, "metrics": 1})
        asset = VirtualAsset.objects.get(external_id="datastore-1")
        self.assertEqual(asset.kind, "DATASTORE")
        persist_collection(
            self.connector,
            {
                "collected_at": timezone.now().isoformat(),
                "hosts": [],
                "vms": [],
                "datastores": [],
            },
        )
        asset.refresh_from_db()
        asset.machine.refresh_from_db()
        self.assertEqual(asset.state, "UNAVAILABLE")
        self.assertEqual(asset.machine.status, "OFFLINE")

    def test_powered_off_vm_stays_offline_after_metric_ingestion(self):
        persist_collection(
            self.connector,
            {
                "collected_at": timezone.now().isoformat(),
                "hosts": [],
                "datastores": [],
                "vms": [
                    {
                        "external_id": "vm-1",
                        "kind": "VM",
                        "name": "VM 1",
                        "state": "poweredOff",
                        "metrics": [
                            {
                                "metric_name": "vm.state",
                                "metric_value": 0,
                                "unit": "state",
                            }
                        ],
                    }
                ],
            },
        )
        self.assertEqual(
            VirtualAsset.objects.get(external_id="vm-1").machine.status, "OFFLINE"
        )

    def test_vmware_datastore_math_uses_real_capacity_fields(self):
        collector = VMwareCollector(
            VMwareConfig("https://vc.example.test", "svc", "SECRET")
        )
        datastore = SimpleNamespace(
            _moId="ds-1",
            name="SAN01",
            summary=SimpleNamespace(
                capacity=1000,
                freeSpace=250,
                name="SAN01",
                accessible=True,
                url="ds:///SAN01",
                type="VMFS",
                multipleHostAccess=True,
            ),
        )
        item = collector._datastore(datastore, timezone.now().isoformat())
        self.assertEqual(item["metrics"][0]["metric_value"], 75)
        self.assertEqual(item["metrics"][1]["metric_value"], 250)


class HyperVCollectorReviewTests(TestCase):
    @patch("hyperv_connector.collector.subprocess.run")
    def test_secret_is_only_passed_through_child_environment(self, run):
        captured_environment = {}

        def execute(_command, **kwargs):
            captured_environment.update(kwargs["env"])
            return Mock(
                returncode=0,
                stdout='{"hosts": [], "vms": [], "collected_at": "2026-01-01T00:00:00Z"}',
                stderr="",
            )

        run.side_effect = execute
        config = HyperVConfig("hv01", "svc", "HYPERV_TEST_SECRET", 10)
        with patch.dict("os.environ", {"HYPERV_TEST_SECRET": "never-in-command"}):
            result = HyperVCollector(config).collect()
        command = run.call_args.args[0]
        self.assertNotIn("never-in-command", command)
        self.assertEqual(
            captured_environment["INFRASENTINEL_HYPERV_SECRET"],
            "never-in-command",
        )
        self.assertEqual(result["hosts"], [])

    @patch("hyperv_connector.collector.subprocess.run")
    def test_powershell_failure_and_invalid_json_are_explicit(self, run):
        run.return_value = Mock(returncode=1, stdout="", stderr="permission denied")
        with self.assertRaisesRegex(HyperVCollectionError, "code 1"):
            HyperVCollector(HyperVConfig("hv01")).collect()
        run.return_value = Mock(returncode=0, stdout="not-json", stderr="")
        with self.assertRaisesRegex(HyperVCollectionError, "JSON valide"):
            HyperVCollector(HyperVConfig("hv01")).collect()


class MLReviewTests(ReviewBase):
    def _seed_test_fixture_metrics(self, buckets=25):
        # Jeu synthétique réservé aux tests; il n'est jamais présenté comme donnée réelle.
        names = [
            "system.cpu.utilization",
            "system.memory.utilization",
            "system.disk.utilization",
            "system.network.in",
            "system.network.out",
            "system.network.latency",
        ]
        start = timezone.now() - timedelta(minutes=buckets * 5)
        rows = []
        for bucket in range(buckets):
            for offset, name in enumerate(names):
                rows.append(
                    NormalizedMetric(
                        timestamp=start + timedelta(minutes=bucket * 5),
                        customer=self.customer,
                        environment=self.environment,
                        machine=self.machine,
                        source_type="WINDOWS",
                        metric_name=name,
                        metric_value=float(bucket + offset),
                        unit="%" if offset < 3 else "bytes/s",
                    )
                )
        NormalizedMetric.objects.bulk_create(rows)

    def test_training_uses_chronological_holdout_and_relative_artifact(self):
        self._seed_test_fixture_metrics()
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("ml_engine.pipeline.MODEL_DIR", Path(directory)),
        ):
            result = train_customer_model(
                self.customer.pk,
                days=2,
                dataset_metadata={"synthetic": True, "demo_suite": "tests"},
            )
            model = MLModelVersion.objects.get(pk=result["model_id"])
            self.assertEqual(
                model.evaluation_metrics["method"], "chronological_holdout"
            )
            self.assertFalse(model.evaluation_metrics["ground_truth_available"])
            self.assertIsNone(model.evaluation_metrics["precision"])
            self.assertEqual(model.dataset["training_rows"], 20)
            self.assertEqual(model.dataset["validation_rows"], 5)
            self.assertTrue(model.dataset["synthetic"])
            self.assertEqual(model.dataset["demo_suite"], "tests")
            self.assertFalse(Path(model.artifact_path).is_absolute())
            self.assertTrue((Path(directory) / model.artifact_path).is_file())

    def test_operational_evaluation_does_not_invent_labels(self):
        result = evaluate_detection_strategies(self.customer.pk, days=30)
        self.assertFalse(result["ground_truth_available"])
        self.assertIsNone(result["precision"])
        self.assertIsNone(result["recall"])

    def test_predictive_trend_is_explicitly_an_estimate(self):
        MonitoringRule.objects.create(
            customer=self.customer,
            name="CPU",
            metric="system.cpu.utilization",
            operator=">",
            threshold=90,
            severity="HIGH",
        )
        start = timezone.now() - timedelta(hours=3)
        for index in range(12):
            NormalizedMetric.objects.create(
                timestamp=start + timedelta(minutes=index * 15),
                customer=self.customer,
                environment=self.environment,
                machine=self.machine,
                source_type="WINDOWS",
                metric_name="system.cpu.utilization",
                metric_value=40 + index * 2,
                unit="%",
            )
        trend = analyze_machine_trends(self.machine, hours=6)[0]
        self.assertEqual(trend["trend"], "INCREASING")
        self.assertTrue(trend["is_estimate"])
        self.assertIn("certitude", trend["disclaimer"])


class ReplayApiReviewTests(ReviewBase):
    def test_negative_and_malformed_replay_cursor_return_400(self):
        self.assertEqual(
            self.client.get("/api/realtime/replay/?since=-1").status_code, 400
        )
        self.assertEqual(
            self.client.get("/api/realtime/replay/?since=abc").status_code, 400
        )


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    NOTIFICATION_SENDING_TIMEOUT_SECONDS=30,
)
class NotificationRecoveryReviewTests(ReviewBase):
    def setUp(self):
        super().setUp()
        self.preference = NotificationPreference.objects.create(
            customer=self.customer,
            channel="EMAIL",
            destination="ops@example.test",
            minimum_severity="HIGH",
            cooldown_seconds=300,
        )
        self.alert = Alert.objects.create(
            customer=self.customer,
            machine=self.machine,
            type="CPU",
            severity="CRITICAL",
            source="WINDOWS",
            message="CPU",
            dedup_key="review-cpu",
        )
        self.event = NotificationEvent.objects.create(
            customer=self.customer,
            alert=self.alert,
            event_type="alert.created",
            severity="CRITICAL",
            payload={"message": "CPU"},
            dedup_key="review-event",
        )

    def test_fresh_sending_delivery_is_not_sent_twice(self):
        delivery = NotificationDelivery.objects.create(
            event=self.event,
            preference=self.preference,
            status="SENDING",
            next_attempt_at=timezone.now(),
        )
        with patch("notifications.adapters.EmailAdapter.send") as send:
            self.assertEqual(deliver_notification(delivery.pk), "IN_PROGRESS")
        send.assert_not_called()

    def test_stale_sending_delivery_is_recovered(self):
        delivery = NotificationDelivery.objects.create(
            event=self.event,
            preference=self.preference,
            status="SENDING",
            next_attempt_at=timezone.now(),
        )
        NotificationDelivery.objects.filter(pk=delivery.pk).update(
            updated_at=timezone.now() - timedelta(minutes=10)
        )
        result = dispatch_due_notifications()
        delivery.refresh_from_db()
        self.assertEqual(result["recovered"], 1)
        self.assertEqual(delivery.status, "SENT")

    def test_critical_escalation_bypasses_high_cooldown(self):
        previous_event = NotificationEvent.objects.create(
            customer=self.customer,
            alert=self.alert,
            event_type="alert.created",
            severity="HIGH",
            payload={},
            dedup_key="review-event-high",
        )
        NotificationDelivery.objects.create(
            event=previous_event,
            preference=self.preference,
            status="SENT",
            sent_at=timezone.now(),
        )
        critical = NotificationDelivery.objects.create(
            event=self.event,
            preference=self.preference,
            next_attempt_at=timezone.now(),
        )
        with patch(
            "notifications.adapters.EmailAdapter.send", return_value="provider-critical"
        ) as send:
            result = deliver_notification(critical.pk)
        self.assertEqual(result, "SENT")
        send.assert_called_once()


@skipUnless(
    settings.DATABASES["default"]["ENGINE"].endswith("postgresql"),
    "PostgreSQL required",
)
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PostgreSQLNotificationConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.customer = Customer.objects.create(name="Concurrency", slug="concurrency")
        environment = Environment.objects.create(
            customer=self.customer, name="Windows", kind="WINDOWS"
        )
        machine = Machine.objects.create(
            customer=self.customer,
            environment=environment,
            source_type="WINDOWS",
            external_id="concurrent-host",
            hostname="concurrent-host",
        )
        preference = NotificationPreference.objects.create(
            customer=self.customer,
            channel="EMAIL",
            destination="ops@example.test",
            minimum_severity="HIGH",
        )
        alert = Alert.objects.create(
            customer=self.customer,
            machine=machine,
            type="CPU",
            severity="CRITICAL",
            source="WINDOWS",
            message="CPU",
            dedup_key="concurrent-cpu",
        )
        event = NotificationEvent.objects.create(
            customer=self.customer,
            alert=alert,
            event_type="alert.created",
            severity="CRITICAL",
            payload={},
            dedup_key="concurrent-event",
        )
        self.delivery = NotificationDelivery.objects.create(
            event=event, preference=preference, next_attempt_at=timezone.now()
        )

    def test_two_workers_send_one_email(self):
        entered_adapter = threading.Event()
        release_adapter = threading.Event()
        calls = []
        results = []

        def fake_send(_delivery):
            calls.append(1)
            entered_adapter.set()
            release_adapter.wait(3)
            return "provider-1"

        def execute():
            close_old_connections()
            try:
                results.append(deliver_notification(self.delivery.pk))
            finally:
                connections.close_all()

        with patch("notifications.adapters.EmailAdapter.send", side_effect=fake_send):
            first = threading.Thread(target=execute)
            first.start()
            self.assertTrue(entered_adapter.wait(3))
            second = threading.Thread(target=execute)
            second.start()
            second.join(3)
            release_adapter.set()
            first.join(3)
        self.assertEqual(calls, [1])
        self.assertCountEqual(results, ["SENT", "IN_PROGRESS"])
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, "SENT")


@skipUnless(
    settings.DATABASES["default"]["ENGINE"].endswith("postgresql"),
    "PostgreSQL required",
)
class PostgreSQLAlertConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="Alert race", slug="alert-race")
        environment = Environment.objects.create(
            customer=self.customer, name="Windows", kind="WINDOWS"
        )
        self.machine = Machine.objects.create(
            customer=self.customer,
            environment=environment,
            source_type="WINDOWS",
            external_id="alert-race-host",
            hostname="alert-race-host",
        )

    def test_simultaneous_alerts_are_deduplicated(self):
        start = threading.Barrier(2)
        results = []

        def execute():
            close_old_connections()
            try:
                machine = Machine.objects.get(pk=self.machine.pk)
                start.wait(3)
                alert, created = create_or_update_alert(
                    machine=machine,
                    alert_type="CPU",
                    severity="WARNING",
                    source="WINDOWS",
                    message="CPU high",
                    context={"metric_name": "system.cpu.utilization"},
                    source_key="same-rule",
                )
                results.append((str(alert.pk), created))
            finally:
                connections.close_all()

        threads = [threading.Thread(target=execute) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
        self.assertEqual(len(results), 2)
        self.assertEqual(len({row[0] for row in results}), 1)
        self.assertEqual(sum(row[1] for row in results), 1)
        self.assertEqual(Alert.objects.count(), 1)
        self.assertEqual(Alert.objects.get().occurrences, 2)


@skipUnless(
    settings.DATABASES["default"]["ENGINE"].endswith("postgresql"),
    "PostgreSQL required",
)
class PostgreSQLMultiAgentTests(TransactionTestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="Agent farm", slug="agent-farm")
        self.environment = Environment.objects.create(
            customer=self.customer, name="Windows", kind="WINDOWS"
        )
        self.agents = []
        for index in range(3):
            code = create_enrollment_code(self.customer, self.environment)
            agent, token = enroll_agent(
                code,
                external_id=f"farm-{index}",
                hostname=f"farm-{index}",
            )
            self.agents.append((agent.machine_id, token))

    def test_three_agents_ingest_simultaneously(self):
        start = threading.Barrier(3)
        statuses = []

        def ingest(index, machine_id, token):
            close_old_connections()
            try:
                start.wait(3)
                response = APIClient().post(
                    "/api/agent/metrics/",
                    {
                        "machine_id": str(machine_id),
                        "metrics": [
                            {
                                "metric_name": "cpu.percent",
                                "metric_value": 10 + index,
                                "idempotency_key": f"farm-{index}-metric",
                            }
                        ],
                    },
                    format="json",
                    HTTP_X_AGENT_TOKEN=token,
                )
                statuses.append(response.status_code)
            finally:
                connections.close_all()

        threads = [
            threading.Thread(target=ingest, args=(index, machine_id, token))
            for index, (machine_id, token) in enumerate(self.agents)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
        self.assertCountEqual(statuses, [202, 202, 202])
        self.assertEqual(
            NormalizedMetric.objects.filter(customer=self.customer).count(), 3
        )
        self.assertEqual(
            Machine.objects.filter(customer=self.customer, status="ONLINE").count(), 3
        )
