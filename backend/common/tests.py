from datetime import timedelta
from unittest.mock import patch
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from celery.exceptions import Retry
from django.core import mail
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from accounts.models import Customer, User
from async_tasks.idempotency import run_once
from async_tasks.models import TaskRun
from config.asgi import application
from integrations.tasks import collect_vmware_connector
from inventory.models import Agent, Environment, IntegrationEndpoint, Machine
from inventory.services import authenticate_agent, create_enrollment_code, enroll_agent
from metrics.models import NormalizedMetric
from metrics.normalization import normalize_metric
from metrics.services import ingest_metrics
from monitoring.alert_service import create_or_update_alert
from monitoring.engine import evaluate_metric
from monitoring.models import Alert, MonitoringRule, Recommendation, RuleState
from notifications.models import (
    NotificationDelivery,
    NotificationEvent,
    NotificationPreference,
)
from notifications.tasks import dispatch_pending_notifications
from realtime.models import RealtimeEvent
from realtime.tickets import issue_ticket
from vmware_connector.collector import VMwareCollectionError


class BaseData(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="Alpha", slug="alpha")
        self.other_customer = Customer.objects.create(name="Beta", slug="beta")
        self.environment = Environment.objects.create(
            customer=self.customer, name="Production", kind="WINDOWS"
        )
        self.other_environment = Environment.objects.create(
            customer=self.other_customer, name="Production", kind="WINDOWS"
        )
        self.machine = Machine.objects.create(
            customer=self.customer,
            environment=self.environment,
            source_type="WINDOWS",
            external_id="alpha-host",
            hostname="alpha-host",
        )
        self.other_machine = Machine.objects.create(
            customer=self.other_customer,
            environment=self.other_environment,
            source_type="WINDOWS",
            external_id="beta-host",
            hostname="beta-host",
        )
        self.user = User.objects.create_user(
            username="admin-alpha",
            email="admin@alpha.test",
            password="CorrectHorse12!",
            customer=self.customer,
            role="ADMIN",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)


class TenantApiTests(BaseData):
    def test_machine_list_is_tenant_isolated(self):
        response = self.client.get("/api/machines/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row["hostname"] for row in response.data["results"]], ["alpha-host"]
        )

    def test_cross_tenant_machine_relationship_is_rejected(self):
        response = self.client.post(
            "/api/machines/",
            {
                "environment": str(self.other_environment.pk),
                "source_type": "WINDOWS",
                "external_id": "bad",
                "hostname": "bad",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_agent_cannot_publish_for_another_machine(self):
        agent = Agent.objects.create(
            customer=self.customer, machine=self.machine, token_hash="a" * 64
        )
        with patch("common.api.authenticate_agent", return_value=agent):
            response = APIClient().post(
                "/api/agent/metrics/",
                {
                    "machine_id": str(self.other_machine.pk),
                    "metrics": [{"metric_name": "cpu", "metric_value": 1}],
                },
                HTTP_AUTHORIZATION="Bearer raw",
            )
        self.assertEqual(response.status_code, 403)


class EnrollmentTests(BaseData):
    def test_enrollment_is_single_use_and_token_is_hashed(self):
        code = create_enrollment_code(self.customer, self.environment)
        agent, token = enroll_agent(code, external_id="new-host", hostname="new-host")
        self.assertNotEqual(agent.token_hash, token)
        self.assertEqual(authenticate_agent(token), agent)
        with self.assertRaises(ValueError):
            enroll_agent(code, external_id="second", hostname="second")


class NormalizationTests(BaseData):
    def test_windows_vmware_hyperv_cpu_share_canonical_name(self):
        for source, raw_name in [
            ("WINDOWS", "cpu.percent"),
            ("VMWARE", "system.cpu.utilization"),
            ("HYPERV", "cpu_usage"),
        ]:
            normalized = normalize_metric(
                {"metric_name": raw_name, "metric_value": 42},
                source_type=source,
                customer=self.customer,
                environment=self.environment,
                machine=self.machine,
            )
            self.assertEqual(normalized["metric_name"], "system.cpu.utilization")

    def test_specific_metadata_is_preserved(self):
        normalized = normalize_metric(
            {
                "metric_name": "datastore.usage",
                "metric_value": 70,
                "metadata": {"datastore": "SAN01"},
            },
            source_type="VMWARE",
            customer=self.customer,
            environment=self.environment,
            machine=self.machine,
        )
        self.assertEqual(normalized["metadata"]["datastore"], "SAN01")

    def test_idempotent_ingestion_ignores_duplicate_metric(self):
        item = {"metric_name": "cpu", "metric_value": 10, "idempotency_key": "fixed"}
        self.assertEqual(
            ingest_metrics(machine=self.machine, source_type="WINDOWS", items=[item]), 1
        )
        self.assertEqual(
            ingest_metrics(machine=self.machine, source_type="WINDOWS", items=[item]), 0
        )

    def test_idempotency_key_is_scoped_by_customer(self):
        item = {"metric_name": "cpu", "metric_value": 10, "idempotency_key": "shared"}
        self.assertEqual(
            ingest_metrics(machine=self.machine, source_type="WINDOWS", items=[item]), 1
        )
        self.assertEqual(
            ingest_metrics(
                machine=self.other_machine, source_type="WINDOWS", items=[item]
            ),
            1,
        )


class RuleAndAlertTests(BaseData):
    def _metric(self, timestamp, value):
        return NormalizedMetric.objects.create(
            timestamp=timestamp,
            customer=self.customer,
            environment=self.environment,
            machine=self.machine,
            source_type="WINDOWS",
            metric_name="system.cpu.utilization",
            metric_value=value,
            unit="%",
        )

    def test_rule_waits_for_duration(self):
        rule = MonitoringRule.objects.create(
            customer=self.customer,
            name="CPU durable",
            metric="system.cpu.utilization",
            operator=">",
            threshold=90,
            duration_seconds=300,
            severity="HIGH",
        )
        start = timezone.now()
        evaluate_metric(self._metric(start, 95))
        self.assertFalse(Alert.objects.exists())
        evaluate_metric(self._metric(start + timedelta(seconds=301), 96))
        self.assertEqual(Alert.objects.count(), 1)
        self.assertTrue(RuleState.objects.get(rule=rule, machine=self.machine).active)

    def test_same_metric_is_not_reprocessed_by_periodic_scan(self):
        MonitoringRule.objects.create(
            customer=self.customer,
            name="CPU immédiat",
            metric="system.cpu.utilization",
            operator=">",
            threshold=90,
            duration_seconds=0,
            severity="WARNING",
            cooldown_seconds=0,
        )
        metric = self._metric(timezone.now(), 95)
        evaluate_metric(metric)
        evaluate_metric(metric)
        self.assertEqual(Alert.objects.get().occurrences, 1)

    def test_alerts_are_deduplicated_and_recommended(self):
        first, created = create_or_update_alert(
            machine=self.machine,
            alert_type="CPU",
            severity="HIGH",
            source="WINDOWS",
            message="CPU high",
            context={"metric_name": "system.cpu.utilization"},
            source_key="rule-1",
        )
        second, created_second = create_or_update_alert(
            machine=self.machine,
            alert_type="CPU",
            severity="HIGH",
            source="WINDOWS",
            message="CPU high",
            context={"metric_name": "system.cpu.utilization"},
            source_key="rule-1",
        )
        self.assertTrue(created)
        self.assertFalse(created_second)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(second.occurrences, 2)
        recommendation = Recommendation.objects.get(alert=first)
        self.assertFalse(recommendation.destructive)
        self.assertTrue(recommendation.actions)


class AsyncIdempotencyTests(TestCase):
    def test_duplicate_execution_returns_previous_result(self):
        calls = []
        first = run_once(
            "test.task", "same", "one", lambda: calls.append(1) or {"value": 7}
        )
        second = run_once(
            "test.task", "same", "two", lambda: calls.append(2) or {"value": 8}
        )
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(calls, [1])

    def test_failure_can_be_retried(self):
        def fail():
            raise OSError("temporary")

        with self.assertRaises(OSError):
            run_once("test.retry", "key", "one", fail)
        result = run_once("test.retry", "key", "two", lambda: {"ok": True})
        self.assertTrue(result["ok"])
        self.assertEqual(
            TaskRun.objects.get(task_name="test.retry").status, TaskRun.Status.SUCCESS
        )

    def test_stale_running_task_is_recovered_after_worker_restart(self):
        run = TaskRun.objects.create(
            task_name="test.restart",
            idempotency_key="key",
            status=TaskRun.Status.RUNNING,
        )
        TaskRun.objects.filter(pk=run.pk).update(
            started_at=timezone.now() - timedelta(hours=2)
        )
        result = run_once(
            "test.restart",
            "key",
            "new-worker",
            lambda: {"recovered": True},
            stale_after_seconds=10,
        )
        self.assertTrue(result["recovered"])

    def test_same_key_is_isolated_between_customers(self):
        first = Customer.objects.create(name="Task Alpha", slug="task-alpha")
        second = Customer.objects.create(name="Task Beta", slug="task-beta")
        one = run_once(
            "test.tenant",
            "same-key",
            "one",
            lambda: {"tenant": "alpha"},
            customer_id=first.pk,
        )
        two = run_once(
            "test.tenant",
            "same-key",
            "two",
            lambda: {"tenant": "beta"},
            customer_id=second.pk,
        )
        self.assertFalse(one["duplicate"])
        self.assertFalse(two["duplicate"])
        self.assertEqual(TaskRun.objects.filter(task_name="test.tenant").count(), 2)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class NotificationTests(BaseData):
    def setUp(self):
        super().setUp()
        self.preference = NotificationPreference.objects.create(
            customer=self.customer,
            channel="EMAIL",
            destination="ops@alpha.test",
            minimum_severity="HIGH",
            cooldown_seconds=300,
        )
        self.alert = Alert.objects.create(
            customer=self.customer,
            machine=self.machine,
            type="CPU",
            severity="CRITICAL",
            source="WINDOWS",
            message="CPU high",
            dedup_key="cpu",
        )

    def test_email_delivery_is_asynchronous_and_logged(self):
        event = NotificationEvent.objects.create(
            customer=self.customer,
            alert=self.alert,
            event_type="alert.created",
            severity="CRITICAL",
            payload={
                "alert_id": str(self.alert.pk),
                "machine": self.machine.hostname,
                "message": self.alert.message,
            },
            dedup_key="mail-1",
        )
        delivery = NotificationDelivery.objects.create(
            event=event, preference=self.preference, next_attempt_at=timezone.now()
        )
        result = dispatch_pending_notifications()
        delivery.refresh_from_db()
        self.assertEqual(result["sent"], 1)
        self.assertEqual(delivery.status, "SENT")
        self.assertEqual(len(mail.outbox), 1)

    @patch("notifications.adapters.EmailAdapter.send", side_effect=OSError("smtp down"))
    def test_email_failure_is_scheduled_for_retry(self, _send):
        event = NotificationEvent.objects.create(
            customer=self.customer,
            alert=self.alert,
            event_type="alert.created",
            severity="CRITICAL",
            payload={},
            dedup_key="mail-2",
        )
        delivery = NotificationDelivery.objects.create(
            event=event, preference=self.preference, next_attempt_at=timezone.now()
        )
        dispatch_pending_notifications()
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, "RETRY")
        self.assertGreater(delivery.next_attempt_at, timezone.now())


class ConnectorTaskTests(BaseData):
    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("integrations.tasks.VMwareCollector.collect")
    def test_vmware_task_executes_once_for_duplicate_key(self, collect):
        connector = IntegrationEndpoint.objects.create(
            customer=self.customer,
            environment=self.environment,
            kind="VMWARE",
            name="vc",
            endpoint="https://vc.test",
            username="svc",
            secret_ref="VC_SECRET",
        )
        collect.return_value = {
            "collected_at": timezone.now().isoformat(),
            "hosts": [],
            "vms": [],
        }
        with patch.dict("os.environ", {"VC_SECRET": "not-logged"}):
            first = collect_vmware_connector.apply(
                args=[str(connector.pk)], kwargs={"idempotency_key": "same"}
            ).get()
            second = collect_vmware_connector.apply(
                args=[str(connector.pk)], kwargs={"idempotency_key": "same"}
            ).get()
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(collect.call_count, 1)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("integrations.tasks.VMwareCollector.collect")
    def test_vmware_task_retries_then_succeeds(self, collect):
        connector = IntegrationEndpoint.objects.create(
            customer=self.customer,
            environment=self.environment,
            kind="VMWARE",
            name="retry-vc",
            endpoint="https://vc.test",
            username="svc",
            secret_ref="VC_SECRET",
        )
        collect.side_effect = [
            VMwareCollectionError("temporary timeout"),
            {"collected_at": timezone.now().isoformat(), "hosts": [], "vms": []},
        ]
        with patch.dict("os.environ", {"VC_SECRET": "not-logged"}):
            with self.assertRaises(Retry):
                collect_vmware_connector.apply(args=[str(connector.pk)]).get()
            result = collect_vmware_connector.apply(args=[str(connector.pk)]).get()
        self.assertFalse(result["duplicate"])
        self.assertEqual(collect.call_count, 2)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch(
        "integrations.tasks.VMwareCollector.collect",
        side_effect=VMwareCollectionError("permanent failure"),
    )
    def test_vmware_task_failure_is_recorded_after_retries(self, collect):
        connector = IntegrationEndpoint.objects.create(
            customer=self.customer,
            environment=self.environment,
            kind="VMWARE",
            name="failed-vc",
            endpoint="https://vc.test",
            username="svc",
            secret_ref="VC_SECRET",
        )
        with patch.dict("os.environ", {"VC_SECRET": "not-logged"}):
            with self.assertRaises(VMwareCollectionError):
                collect_vmware_connector.apply(
                    args=[str(connector.pk)], retries=5
                ).get()
        self.assertGreaterEqual(collect.call_count, 1)
        self.assertTrue(
            TaskRun.objects.filter(
                task_name="integrations.collect_vmware_connector",
                status=TaskRun.Status.FAILED,
            ).exists()
        )


class RealtimeSecurityTests(TransactionTestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="Realtime", slug="realtime")
        self.user = User.objects.create_user(
            username="realtime-user",
            email="realtime@example.test",
            password="CorrectHorse12!",
            customer=self.customer,
            role="ADMIN",
        )

    def test_ticket_rejects_cross_tenant_claim_tampering(self):
        ticket = issue_ticket(self.user)

        async def scenario():
            communicator = WebsocketCommunicator(
                application, f"/ws/events/?ticket={ticket}&since=0"
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.disconnect()
            bad = WebsocketCommunicator(application, "/ws/events/?ticket=invalid")
            connected_bad, code = await bad.connect()
            self.assertFalse(connected_bad)
            self.assertEqual(code, 4401)

        async_to_sync(scenario)()

    def test_reconnect_replays_events_missed_after_last_sequence(self):
        first = RealtimeEvent.objects.create(
            customer=self.customer,
            event_type="machine.online",
            aggregate_id="host-1",
            payload={"online": True},
        )
        second = RealtimeEvent.objects.create(
            customer=self.customer,
            event_type="alert.created",
            aggregate_id="alert-1",
            payload={"severity": "CRITICAL"},
        )
        ticket = issue_ticket(self.user)

        async def scenario():
            initial = WebsocketCommunicator(
                application, f"/ws/events/?ticket={ticket}&since={second.sequence}"
            )
            connected, _ = await initial.connect()
            self.assertTrue(connected)
            await initial.disconnect()

            reconnected = WebsocketCommunicator(
                application, f"/ws/events/?ticket={ticket}&since={first.sequence}"
            )
            connected_again, _ = await reconnected.connect()
            self.assertTrue(connected_again)
            replay = await reconnected.receive_json_from(timeout=1)
            self.assertEqual(replay["sequence"], second.sequence)
            self.assertEqual(replay["event_type"], "alert.created")
            await reconnected.disconnect()

        async_to_sync(scenario)()

    def test_multiple_clients_and_independent_disconnect(self):
        ticket = issue_ticket(self.user)

        async def scenario():
            first = WebsocketCommunicator(
                application, f"/ws/events/?ticket={ticket}&since=0"
            )
            second = WebsocketCommunicator(
                application, f"/ws/events/?ticket={ticket}&since=0"
            )
            self.assertTrue((await first.connect())[0])
            self.assertTrue((await second.connect())[0])
            event = {
                "sequence": 1001,
                "event_type": "metric.update",
                "aggregate_id": "host-1",
                "payload": {"metric": "cpu.usage"},
                "created_at": timezone.now().isoformat(),
            }
            await get_channel_layer().group_send(
                f"tenant_{self.customer.pk}",
                {"type": "tenant.event", "event": event},
            )
            self.assertEqual((await first.receive_json_from())["sequence"], 1001)
            self.assertEqual((await second.receive_json_from())["sequence"], 1001)
            await first.disconnect()
            event["sequence"] = 1002
            await get_channel_layer().group_send(
                f"tenant_{self.customer.pk}",
                {"type": "tenant.event", "event": event},
            )
            self.assertEqual((await second.receive_json_from())["sequence"], 1002)
            await second.disconnect()

        async_to_sync(scenario)()

    def test_malformed_replay_cursor_is_rejected(self):
        ticket = issue_ticket(self.user)

        async def scenario():
            communicator = WebsocketCommunicator(
                application, f"/ws/events/?ticket={ticket}&since=invalid"
            )
            connected, code = await communicator.connect()
            self.assertFalse(connected)
            self.assertEqual(code, 4401)

        async_to_sync(scenario)()
