from django.db import models
from accounts.models import Customer
from inventory.models import Environment, Machine


class NormalizedMetric(models.Model):
    timestamp = models.DateTimeField(db_index=True)
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="metrics"
    )
    environment = models.ForeignKey(
        Environment, on_delete=models.CASCADE, related_name="metrics"
    )
    machine = models.ForeignKey(
        Machine, on_delete=models.CASCADE, related_name="metrics"
    )
    source_type = models.CharField(max_length=16)
    metric_name = models.CharField(max_length=120)
    metric_value = models.FloatField(null=True, blank=True)
    unit = models.CharField(max_length=32, blank=True)
    status = models.CharField(max_length=32, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    idempotency_key = models.CharField(max_length=128, null=True, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "idempotency_key"],
                condition=models.Q(idempotency_key__isnull=False),
                name="uniq_metric_customer_idempotency",
            )
        ]
        indexes = [
            models.Index(fields=["customer", "timestamp"]),
            models.Index(fields=["machine", "metric_name", "timestamp"]),
            models.Index(fields=["source_type", "metric_name", "timestamp"]),
        ]
        ordering = ["-timestamp"]


class MetricAggregate(models.Model):
    machine = models.ForeignKey(
        Machine, on_delete=models.CASCADE, related_name="metric_aggregates"
    )
    metric_name = models.CharField(max_length=120)
    bucket_start = models.DateTimeField()
    bucket_seconds = models.PositiveIntegerField(default=3600)
    minimum = models.FloatField()
    maximum = models.FloatField()
    average = models.FloatField()
    sample_count = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["machine", "metric_name", "bucket_start", "bucket_seconds"],
                name="uniq_metric_aggregate_bucket",
            )
        ]
