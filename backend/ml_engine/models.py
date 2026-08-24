import uuid
from django.db import models
from accounts.models import Customer


class MLModelVersion(models.Model):
    class Status(models.TextChoices):
        TRAINING = "TRAINING", "En entraînement"
        READY = "READY", "Prêt"
        FAILED = "FAILED", "Échec"
        ARCHIVED = "ARCHIVED", "Archivé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="ml_models"
    )
    version = models.CharField(max_length=80)
    algorithm = models.CharField(max_length=80, default="IsolationForest")
    features = models.JSONField(default=list)
    preprocessing = models.JSONField(default=dict)
    parameters = models.JSONField(default=dict)
    dataset = models.JSONField(default=dict)
    evaluation_metrics = models.JSONField(default=dict)
    decision_threshold = models.FloatField(null=True, blank=True)
    artifact_path = models.CharField(max_length=500, blank=True)
    trained_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.TRAINING
    )
    active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "version"], name="uniq_ml_customer_version"
            )
        ]
