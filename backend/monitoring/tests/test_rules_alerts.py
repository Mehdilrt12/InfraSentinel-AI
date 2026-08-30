from datetime import timedelta

from django.utils import timezone

from accounts.models import User
from common.testing import TenantAPITestCase
from inventory.models import Environment, Machine
from metrics.models import NormalizedMetric
from monitoring.alert_service import create_or_update_alert
from monitoring.engine import evaluate_metric, evaluate_offline_machines
from monitoring.models import Alert, MonitoringRule, RuleState


class RuleEngineTests(TenantAPITestCase):
    def setUp(self):
        self.machine = self.create_machine()

    def _metric(self, name, value, *, timestamp=None, metadata=None):
        return NormalizedMetric.objects.create(
            timestamp=timestamp or timezone.now(),
            customer=self.customer_a,
            environment=self.environment_a,
            machine=self.machine,
            source_type="WINDOWS",
            metric_name=name,
            metric_value=value,
            unit="%",
            metadata=metadata or {},
        )

    def _rule(self, metric, operator, threshold=10, **overrides):
        values = {
            "customer": self.customer_a,
            "name": f"Rule {metric}",
            "metric": metric,
            "operator": operator,
            "threshold": threshold,
            "duration_seconds": 0,
            "severity": "WARNING",
            "cooldown_seconds": 300,
        }
        values.update(overrides)
        return MonitoringRule.objects.create(**values)

    def test_all_six_supported_operators_trigger(self):
        cases = ((">", 11), ("<", 9), (">=", 10), ("<=", 10), ("==", 10), ("!=", 11))
        for index, (operator, value) in enumerate(cases):
            metric_name = f"test.operator.{index}"
            rule = self._rule(metric_name, operator)
            alerts = evaluate_metric(self._metric(metric_name, value))
            with self.subTest(operator=operator):
                self.assertEqual(len(alerts), 1)
                self.assertEqual(alerts[0].context["rule_id"], str(rule.pk))

    def test_disabled_environment_and_machine_scopes_are_respected(self):
        other_environment = Environment.objects.create(
            customer=self.customer_a, name="Other", kind=Environment.Kind.WINDOWS
        )
        other_machine = self.create_machine(
            environment=other_environment,
            external_id="other-machine",
            hostname="other-machine",
        )
        self._rule("scope.metric", ">", enabled=False)
        self._rule("scope.metric", ">", environment=other_environment)
        self._rule("scope.metric", ">", machine=other_machine)
        self.assertEqual(evaluate_metric(self._metric("scope.metric", 100)), [])
        self.assertEqual(RuleState.objects.count(), 0)

    def test_duration_and_dimension_keep_independent_state(self):
        rule = self._rule(
            "windows.service.state", "==", threshold=0, duration_seconds=60
        )
        start = timezone.now()
        first = self._metric(
            "windows.service.state", 0, timestamp=start, metadata={"service_name": "SQL"}
        )
        second = self._metric(
            "windows.service.state",
            0,
            timestamp=start + timedelta(seconds=61),
            metadata={"service_name": "SQL"},
        )
        other = self._metric(
            "windows.service.state",
            0,
            timestamp=start + timedelta(seconds=62),
            metadata={"service_name": "IIS"},
        )
        self.assertEqual(evaluate_metric(first), [])
        self.assertEqual(len(evaluate_metric(second)), 1)
        self.assertEqual(evaluate_metric(other), [])
        self.assertEqual(rule.states.count(), 2)

    def test_multiple_rules_evaluate_same_metric_independently(self):
        for threshold in (10, 20, 30):
            self._rule(
                "system.cpu.utilization",
                ">",
                threshold=threshold,
                name=f"CPU {threshold}",
            )
        alerts = evaluate_metric(self._metric("system.cpu.utilization", 95))
        self.assertEqual(len(alerts), 3)
        self.assertEqual(Alert.objects.count(), 3)

    def test_abnormal_to_normal_resolves_and_historical_replay_is_ignored(self):
        rule = self._rule("system.memory.utilization", ">", threshold=90)
        now = timezone.now()
        alert = evaluate_metric(
            self._metric("system.memory.utilization", 95, timestamp=now)
        )[0]
        self.assertEqual(
            evaluate_metric(
                self._metric(
                    "system.memory.utilization",
                    99,
                    timestamp=now - timedelta(seconds=1),
                )
            ),
            [],
        )
        evaluate_metric(
            self._metric(
                "system.memory.utilization", 30, timestamp=now + timedelta(seconds=1)
            )
        )
        alert.refresh_from_db()
        self.assertNotEqual(alert.status, Alert.Status.RESOLVED)
        evaluate_metric(
            self._metric(
                "system.memory.utilization", 30, timestamp=now + timedelta(seconds=2)
            )
        )
        alert.refresh_from_db()
        state = RuleState.objects.get(rule=rule, machine=self.machine)
        self.assertEqual(alert.status, Alert.Status.RESOLVED)
        self.assertFalse(state.active)

    def test_large_sampling_gap_restarts_duration_evidence(self):
        rule = self._rule(
            "system.cpu.utilization", ">", threshold=80, duration_seconds=60
        )
        start = timezone.now()
        self.assertEqual(
            evaluate_metric(
                self._metric("system.cpu.utilization", 90, timestamp=start)
            ),
            [],
        )
        self.assertEqual(
            evaluate_metric(
                self._metric(
                    "system.cpu.utilization",
                    91,
                    timestamp=start + timedelta(minutes=5),
                )
            ),
            [],
        )
        state = RuleState.objects.get(rule=rule, machine=self.machine)
        self.assertEqual(state.consecutive_matches, 1)
        self.assertEqual(state.first_true_at, start + timedelta(minutes=5))

    def test_active_rule_survives_one_normal_sample_then_recovers(self):
        rule = self._rule("system.cpu.utilization", ">", threshold=80)
        start = timezone.now()
        alert = evaluate_metric(
            self._metric("system.cpu.utilization", 90, timestamp=start)
        )[0]
        evaluate_metric(
            self._metric(
                "system.cpu.utilization", 20, timestamp=start + timedelta(seconds=30)
            )
        )
        alert.refresh_from_db()
        self.assertNotEqual(alert.status, Alert.Status.RESOLVED)
        evaluate_metric(
            self._metric(
                "system.cpu.utilization", 20, timestamp=start + timedelta(seconds=60)
            )
        )
        alert.refresh_from_db()
        self.assertEqual(alert.status, Alert.Status.RESOLVED)
        self.assertFalse(RuleState.objects.get(pk=rule.states.get().pk).active)

    def test_offline_rule_changes_status_and_deduplicates_repeated_scan(self):
        self.machine.last_seen = timezone.now() - timedelta(minutes=10)
        self.machine.status = Machine.Status.ONLINE
        self.machine.save(update_fields=["last_seen", "status"])
        self._rule(
            "machine.online",
            "==",
            threshold=0,
            duration_seconds=60,
            severity="CRITICAL",
        )
        self.assertEqual(evaluate_offline_machines(), 1)
        self.assertEqual(evaluate_offline_machines(), 1)
        self.machine.refresh_from_db()
        self.assertEqual(self.machine.status, Machine.Status.OFFLINE)
        self.assertEqual(
            Alert.objects.filter(type="MACHINE_OFFLINE", machine=self.machine).count(),
            1,
        )

    def test_one_hundred_identical_metrics_create_one_durable_alert(self):
        self._rule("system.cpu.utilization", ">", threshold=90, cooldown_seconds=300)
        start = timezone.now()
        for index in range(100):
            evaluate_metric(
                self._metric(
                    "system.cpu.utilization",
                    99,
                    timestamp=start + timedelta(milliseconds=index),
                )
            )
        self.assertEqual(Alert.objects.count(), 1)
        self.assertEqual(Alert.objects.get().occurrences, 1)


class RuleAndAlertAPITests(TenantAPITestCase):
    def setUp(self):
        self.machine = self.create_machine()
        self.authenticate()

    def test_rule_crud_toggle_and_relationship_validation(self):
        created = self.client.post(
            "/api/rules/",
            {
                "name": "CPU",
                "metric": "system.cpu.utilization",
                "operator": ">",
                "threshold": 90,
                "duration_seconds": 60,
                "severity": "HIGH",
                "environment": str(self.environment_a.pk),
                "machine": str(self.machine.pk),
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        rule_id = created.data["id"]
        toggled = self.client.post(f"/api/rules/{rule_id}/toggle/", {}, format="json")
        self.assertEqual(toggled.status_code, 200)
        self.assertFalse(toggled.data["enabled"])
        self.assertEqual(
            self.client.patch(
                f"/api/rules/{rule_id}/", {"threshold": 85}, format="json"
            ).status_code,
            200,
        )
        self.assertEqual(self.client.delete(f"/api/rules/{rule_id}/").status_code, 204)

        invalid = self.client.post(
            "/api/rules/",
            {
                "name": "Invalid offline",
                "metric": "machine.online",
                "operator": ">",
                "threshold": 0,
            },
            format="json",
        )
        self.assertEqual(invalid.status_code, 400)

    def test_alert_status_lifecycle_permissions_and_customer_isolation(self):
        alert, _ = create_or_update_alert(
            machine=self.machine,
            alert_type="RULE_THRESHOLD",
            severity="HIGH",
            source="WINDOWS",
            message="CPU high",
            source_key="cpu",
        )
        for status in (
            Alert.Status.ACKNOWLEDGED,
            Alert.Status.IN_PROGRESS,
            Alert.Status.RESOLVED,
        ):
            response = self.client.patch(
                f"/api/alerts/{alert.pk}/", {"status": status}, format="json"
            )
            with self.subTest(status=status):
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["status"], status)

        foreign_machine = self.create_machine(
            customer=self.customer_b,
            environment=self.environment_b,
            external_id="foreign-alert",
            hostname="foreign-alert",
        )
        foreign, _ = create_or_update_alert(
            machine=foreign_machine,
            alert_type="RULE_THRESHOLD",
            severity="WARNING",
            source="WINDOWS",
            message="foreign",
            source_key="foreign",
        )
        self.assertEqual(self.client.get(f"/api/alerts/{foreign.pk}/").status_code, 404)
        self.authenticate(self.users_by_role[User.Role.VIEWER])
        self.assertEqual(
            self.client.patch(
                f"/api/alerts/{alert.pk}/",
                {"status": Alert.Status.NEW},
                format="json",
            ).status_code,
            403,
        )

    def test_cooldown_escalation_and_reopening_are_persisted(self):
        alert, created = create_or_update_alert(
            machine=self.machine,
            alert_type="RULE_THRESHOLD",
            severity="WARNING",
            source="WINDOWS",
            message="threshold",
            source_key="same",
            cooldown_seconds=300,
        )
        self.assertTrue(created)
        repeated, created = create_or_update_alert(
            machine=self.machine,
            alert_type="RULE_THRESHOLD",
            severity="CRITICAL",
            source="WINDOWS",
            message="threshold",
            source_key="same",
            cooldown_seconds=300,
        )
        self.assertFalse(created)
        self.assertEqual(repeated.pk, alert.pk)
        self.assertEqual(repeated.occurrences, 1)
        self.assertEqual(repeated.escalation_level, 1)
        repeated.status = Alert.Status.RESOLVED
        repeated.save(update_fields=["status"])
        reopened, created = create_or_update_alert(
            machine=self.machine,
            alert_type="RULE_THRESHOLD",
            severity="HIGH",
            source="WINDOWS",
            message="threshold again",
            source_key="same",
        )
        self.assertTrue(created)
        self.assertNotEqual(reopened.pk, repeated.pk)
