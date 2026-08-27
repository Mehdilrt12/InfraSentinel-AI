from datetime import timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone

from common.testing import TenantAPITestCase
from inventory.models import Environment
from metrics.models import MetricAggregate, NormalizedMetric
from metrics.normalization import normalize_batch, normalize_metric
from metrics.services import ingest_metrics
from metrics.tasks import aggregate_history


class MetricNormalizationTests(TenantAPITestCase):
    def setUp(self):
        self.machine = self.create_machine()
        self.scope = {
            "source_type": self.machine.source_type,
            "environment": self.machine.environment,
            "machine": self.machine,
            "customer": self.machine.customer,
        }

    def test_aliases_units_and_specific_metadata_are_preserved(self):
        cases = (
            ("cpu", "system.cpu.utilization", "%", "WINDOWS"),
            ("ram_usage", "system.memory.utilization", "%", "VMWARE"),
            ("disk_free", "system.disk.free", "bytes", "HYPERV"),
            ("service.state", "windows.service.state", "", "WINDOWS"),
            ("datastore.usage", "vmware.datastore.utilization", "", "VMWARE"),
            ("vm.state", "virtual.machine.state", "", "HYPERV"),
        )
        for raw_name, expected, unit, source in cases:
            scope = {**self.scope, "source_type": source}
            row = normalize_metric(
                {
                    "metric_name": raw_name,
                    "metric_value": 1,
                    "metadata": {"resource": raw_name},
                },
                **scope,
            )
            with self.subTest(raw_name=raw_name, source=source):
                self.assertEqual(row["metric_name"], expected)
                self.assertEqual(row["unit"], unit)
                self.assertEqual(row["metadata"]["resource"], raw_name)
                self.assertEqual(row["metadata"]["raw_metric_name"], raw_name)

    def test_rate_units_are_converted_to_bytes_per_second(self):
        row = normalize_metric(
            {
                "metric_name": "network.in",
                "metric_value": 2,
                "unit": "MiB/s",
            },
            **self.scope,
        )
        self.assertEqual(row["metric_value"], 2 * 1024**2)
        self.assertEqual(row["unit"], "bytes/s")
        self.assertEqual(row["metadata"]["original_unit"], "MiB/s")

    def test_invalid_metric_shapes_and_values_are_rejected(self):
        cases = (
            ({"metric_value": 1}, "metric_name"),
            ({"metric_name": "cpu", "metric_value": "bad"}, "metric_value"),
            ({"metric_name": "cpu", "metric_value": float("nan")}, "metric_value"),
            ({"metric_name": "cpu", "metric_value": 1, "metadata": []}, "metadata"),
            ({"metric_name": "x" * 121, "metric_value": 1}, "metric_name"),
            (
                {"metric_name": "cpu", "metric_value": 1, "idempotency_key": "x" * 129},
                "idempotency_key",
            ),
            ({"metric_name": "cpu", "metric_value": 1, "timestamp": "not-a-date"}, "timestamp"),
        )
        for payload, field in cases:
            with self.subTest(field=field), self.assertRaises(ValidationError):
                normalize_metric(payload, **self.scope)

    def test_future_timestamp_is_rejected_but_stale_timestamp_is_retained(self):
        with self.assertRaises(ValidationError):
            normalize_metric(
                {
                    "metric_name": "cpu",
                    "metric_value": 1,
                    "timestamp": timezone.now() + timedelta(minutes=6),
                },
                **self.scope,
            )
        stale = timezone.now() - timedelta(days=365)
        row = normalize_metric(
            {"metric_name": "cpu", "metric_value": 1, "timestamp": stale},
            **self.scope,
        )
        self.assertEqual(row["timestamp"], stale)

    def test_batch_requires_non_empty_bounded_list(self):
        for payload in (None, {}, [], "metrics"):
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                normalize_batch(payload, **self.scope)
        with self.assertRaises(ValidationError):
            normalize_batch(
                [{"metric_name": "cpu", "metric_value": 1}] * 5001,
                **self.scope,
            )


class MetricPersistenceAndAPITests(TenantAPITestCase):
    def setUp(self):
        self.machine = self.create_machine()

    def test_ingestion_is_idempotent_inside_and_across_batches(self):
        timestamp = timezone.now()
        items = [
            {
                "metric_name": "cpu",
                "metric_value": 10,
                "timestamp": timestamp,
                "idempotency_key": "same-key",
            },
            {
                "metric_name": "cpu",
                "metric_value": 20,
                "timestamp": timestamp,
                "idempotency_key": "same-key",
            },
        ]
        self.assertEqual(
            ingest_metrics(machine=self.machine, source_type="WINDOWS", items=items),
            1,
        )
        self.assertEqual(
            ingest_metrics(machine=self.machine, source_type="WINDOWS", items=items),
            0,
        )
        metric = NormalizedMetric.objects.get(idempotency_key="same-key")
        self.assertEqual(metric.metric_value, 10)

    def test_ingestion_rejects_source_mismatch_and_missing_data(self):
        with self.assertRaises(ValueError):
            ingest_metrics(
                machine=self.machine,
                source_type=Environment.Kind.VMWARE,
                items=[{"metric_name": "cpu", "metric_value": 1}],
            )
        with self.assertRaises(ValidationError):
            ingest_metrics(machine=self.machine, source_type="WINDOWS", items=None)

    def test_metric_api_is_read_only_filtered_and_customer_isolated(self):
        own = NormalizedMetric.objects.create(
            timestamp=timezone.now(),
            customer=self.customer_a,
            environment=self.environment_a,
            machine=self.machine,
            source_type="WINDOWS",
            metric_name="system.cpu.utilization",
            metric_value=20,
            unit="%",
        )
        foreign_machine = self.create_machine(
            customer=self.customer_b,
            environment=self.environment_b,
            external_id="foreign-metric-host",
            hostname="foreign-metric-host",
        )
        foreign = NormalizedMetric.objects.create(
            timestamp=timezone.now(),
            customer=self.customer_b,
            environment=self.environment_b,
            machine=foreign_machine,
            source_type="WINDOWS",
            metric_name="system.cpu.utilization",
            metric_value=99,
            unit="%",
        )
        self.authenticate()
        response = self.client.get(
            f"/api/metrics/?machine={self.machine.pk}&metric_name=system.cpu.utilization"
        )
        ids = {row["id"] for row in response.data["results"]}
        self.assertIn(own.pk, ids)
        self.assertNotIn(foreign.pk, ids)
        self.assertEqual(self.client.get(f"/api/metrics/{foreign.pk}/").status_code, 404)
        self.assertEqual(self.client.post("/api/metrics/", {}, format="json").status_code, 405)

    def test_history_aggregation_is_idempotent_and_computes_statistics(self):
        start = timezone.now().replace(minute=5, second=0, microsecond=0)
        for index, value in enumerate((10, 20, 30)):
            NormalizedMetric.objects.create(
                timestamp=start + timedelta(minutes=index),
                customer=self.customer_a,
                environment=self.environment_a,
                machine=self.machine,
                source_type="WINDOWS",
                metric_name="system.cpu.utilization",
                metric_value=value,
                unit="%",
            )
        first = aggregate_history(hours=2)
        second = aggregate_history(hours=2)
        self.assertEqual(first, {"aggregates": 1})
        self.assertEqual(second, {"aggregates": 1})
        aggregate = MetricAggregate.objects.get(
            machine=self.machine, metric_name="system.cpu.utilization"
        )
        self.assertEqual(aggregate.minimum, 10)
        self.assertEqual(aggregate.maximum, 30)
        self.assertEqual(aggregate.average, 20)
        self.assertEqual(aggregate.sample_count, 3)
