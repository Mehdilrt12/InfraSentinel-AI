from types import SimpleNamespace
from unittest.mock import patch

from celery import current_app

from accounts.models import User
from async_tasks.models import GeneratedReport, TaskRun
from async_tasks.tasks import generate_report
from common.testing import TenantAPITestCase
from ml_engine.tasks import analyze_customer, evaluate_model, train_model
from monitoring.models import Alert, Anomaly
from monitoring.tasks import evaluate_rules


class CeleryTaskContractTests(TenantAPITestCase):
    def test_required_tasks_are_discovered_by_celery(self):
        current_app.loader.import_default_modules()
        expected = {
            "reports.generate",
            "metrics.aggregate_history",
            "monitoring.evaluate_rules",
            "ml.train",
            "ml.analyze_customer",
            "ml.analyze_recent",
            "ml.evaluate",
            "notifications.dispatch_pending",
            "integrations.collect_vmware",
            "integrations.collect_hyperv",
            "integrations.collect_vmware_connector",
            "integrations.collect_hyperv_connector",
        }
        self.assertTrue(expected.issubset(set(current_app.tasks)))

    def test_report_task_executes_once_and_persists_real_tenant_counts(self):
        machine = self.create_machine(status="ONLINE")
        Alert.objects.create(
            customer=self.customer_a,
            machine=machine,
            type="RULE_THRESHOLD",
            severity="HIGH",
            source="WINDOWS",
            message="active",
            dedup_key="report-alert",
        )
        Anomaly.objects.create(
            customer=self.customer_a,
            machine=machine,
            score=0.9,
            threshold=0.8,
            model_version="report-model",
        )
        first = generate_report.apply(
            args=[str(self.customer_a.pk), "summary", "report-key"]
        ).get()
        duplicate = generate_report.apply(
            args=[str(self.customer_a.pk), "summary", "report-key"]
        ).get()
        self.assertFalse(first["duplicate"])
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(first["active_alerts"], 1)
        self.assertEqual(first["anomalies"], 1)
        self.assertEqual(GeneratedReport.objects.filter(customer=self.customer_a).count(), 1)

    def test_rule_task_returns_trigger_count(self):
        with patch("monitoring.tasks.evaluate_all_rules", return_value=7) as evaluate:
            result = evaluate_rules.apply().get()
        self.assertEqual(result, {"triggered": 7})
        evaluate.assert_called_once_with()

    def test_ml_training_inference_and_evaluation_tasks_are_idempotent(self):
        with (
            patch("ml_engine.tasks.train_customer_model", return_value={"model_id": "m1"}),
            patch("ml_engine.tasks.infer_customer", return_value={"anomalies": 2}),
            patch(
                "ml_engine.tasks.evaluate_detection_strategies",
                return_value={"ground_truth_available": False},
            ),
        ):
            trained = train_model.apply(
                args=[str(self.customer_a.pk), 30, "ml-train-key"]
            ).get()
            trained_again = train_model.apply(
                args=[str(self.customer_a.pk), 30, "ml-train-key"]
            ).get()
            analyzed = analyze_customer.apply(
                args=[str(self.customer_a.pk), "ml-infer-key"]
            ).get()
            evaluated = evaluate_model.apply(
                args=[str(self.customer_a.pk), 30, "ml-evaluate-key"]
            ).get()
        self.assertFalse(trained["duplicate"])
        self.assertTrue(trained_again["duplicate"])
        self.assertEqual(analyzed["anomalies"], 2)
        self.assertFalse(evaluated["ground_truth_available"])
        self.assertEqual(
            TaskRun.objects.filter(customer=self.customer_a, status=TaskRun.Status.SUCCESS).count(),
            3,
        )


class AsyncTaskAPITests(TenantAPITestCase):
    def test_report_enqueue_and_report_list_are_customer_isolated(self):
        own = GeneratedReport.objects.create(
            customer=self.customer_a,
            kind="summary",
            status=TaskRun.Status.SUCCESS,
            result={"ok": True},
        )
        foreign = GeneratedReport.objects.create(
            customer=self.customer_b,
            kind="summary",
            status=TaskRun.Status.SUCCESS,
            result={"foreign": True},
        )
        self.authenticate()
        response = self.client.get("/api/reports/")
        ids = {row["id"] for row in response.data["results"]}
        self.assertIn(own.pk, ids)
        self.assertNotIn(foreign.pk, ids)
        with patch(
            "common.api.generate_report.delay", return_value=SimpleNamespace(id="report-task")
        ) as delay:
            queued = self.client.post(
                "/api/reports/generate/",
                {"kind": "capacity", "idempotency_key": "api-report"},
                format="json",
            )
        self.assertEqual(queued.status_code, 202)
        self.assertEqual(queued.data["task_id"], "report-task")
        delay.assert_called_once_with(str(self.customer_a.pk), "capacity", "api-report")

    def test_task_run_api_is_admin_only_and_tenant_isolated(self):
        own = TaskRun.objects.create(
            customer=self.customer_a,
            task_name="test.own",
            idempotency_key="own",
            status=TaskRun.Status.SUCCESS,
        )
        foreign = TaskRun.objects.create(
            customer=self.customer_b,
            task_name="test.foreign",
            idempotency_key="foreign",
            status=TaskRun.Status.SUCCESS,
        )
        self.authenticate()
        response = self.client.get("/api/tasks/")
        ids = {row["id"] for row in response.data["results"]}
        self.assertIn(own.pk, ids)
        self.assertNotIn(foreign.pk, ids)
        self.authenticate(self.users_by_role[User.Role.SUPERVISOR])
        self.assertEqual(self.client.get("/api/tasks/").status_code, 403)
