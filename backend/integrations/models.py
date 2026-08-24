from django.db import models
from inventory.models import IntegrationEndpoint


class CollectionRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "RUNNING", "En cours"
        SUCCESS = "SUCCESS", "Succès"
        FAILED = "FAILED", "Échec"

    connector = models.ForeignKey(
        IntegrationEndpoint, on_delete=models.CASCADE, related_name="collection_runs"
    )
    task_id = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.RUNNING
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    discovered_hosts = models.PositiveIntegerField(default=0)
    discovered_vms = models.PositiveIntegerField(default=0)
    metric_count = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
