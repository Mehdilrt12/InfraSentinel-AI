from django.db import models
from accounts.models import Customer


class TaskRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "RUNNING", "En cours"
        SUCCESS = "SUCCESS", "Succès"
        FAILED = "FAILED", "Échec"

    customer = models.ForeignKey(
        Customer,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="task_runs",
    )
    task_name = models.CharField(max_length=160)
    idempotency_key = models.CharField(max_length=255)
    celery_task_id = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.RUNNING
    )
    result = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "task_name", "idempotency_key"],
                condition=models.Q(customer__isnull=False),
                name="uniq_customer_task_idempotency_key",
            ),
            models.UniqueConstraint(
                fields=["task_name", "idempotency_key"],
                condition=models.Q(customer__isnull=True),
                name="uniq_global_task_idempotency_key",
            ),
        ]
        indexes = [
            models.Index(fields=["task_name", "status", "started_at"]),
            models.Index(fields=["customer", "status", "started_at"]),
        ]


class GeneratedReport(models.Model):
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="reports"
    )
    kind = models.CharField(max_length=80)
    status = models.CharField(
        max_length=16, choices=TaskRun.Status.choices, default=TaskRun.Status.RUNNING
    )
    parameters = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    artifact_path = models.CharField(max_length=500, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
