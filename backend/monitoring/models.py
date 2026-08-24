import uuid
from django.db import models
from accounts.models import Customer
from inventory.models import Environment, Machine


class Severity(models.TextChoices):
    INFO = "INFO", "Information"
    WARNING = "WARNING", "Avertissement"
    HIGH = "HIGH", "Élevée"
    CRITICAL = "CRITICAL", "Critique"


class MonitoringRule(models.Model):
    class Operator(models.TextChoices):
        GT = ">", ">"
        LT = "<", "<"
        GTE = ">=", ">="
        LTE = "<=", "<="
        EQ = "==", "=="
        NE = "!=", "!="

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="monitoring_rules"
    )
    name = models.CharField(max_length=200)
    metric = models.CharField(max_length=120)
    operator = models.CharField(max_length=2, choices=Operator.choices)
    threshold = models.FloatField()
    duration_seconds = models.PositiveIntegerField(default=0)
    severity = models.CharField(
        max_length=16, choices=Severity.choices, default=Severity.WARNING
    )
    enabled = models.BooleanField(default=True)
    environment = models.ForeignKey(
        Environment,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="monitoring_rules",
    )
    machine = models.ForeignKey(
        Machine,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="monitoring_rules",
    )
    cooldown_seconds = models.PositiveIntegerField(default=300)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["customer", "metric", "enabled"])]


class RuleState(models.Model):
    rule = models.ForeignKey(
        MonitoringRule, on_delete=models.CASCADE, related_name="states"
    )
    machine = models.ForeignKey(
        Machine, on_delete=models.CASCADE, related_name="rule_states"
    )
    first_true_at = models.DateTimeField(null=True, blank=True)
    last_evaluated_at = models.DateTimeField(null=True, blank=True)
    last_value = models.FloatField(null=True, blank=True)
    active = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["rule", "machine"], name="uniq_rule_machine_state"
            )
        ]


class Alert(models.Model):
    class Status(models.TextChoices):
        NEW = "NEW", "Nouvelle"
        ACKNOWLEDGED = "ACKNOWLEDGED", "Acquittée"
        IN_PROGRESS = "IN_PROGRESS", "En cours"
        RESOLVED = "RESOLVED", "Résolue"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="alerts"
    )
    machine = models.ForeignKey(
        Machine, on_delete=models.CASCADE, related_name="alerts"
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    type = models.CharField(max_length=100)
    severity = models.CharField(max_length=16, choices=Severity.choices)
    source = models.CharField(max_length=32)
    message = models.TextField()
    context = models.JSONField(default=dict, blank=True)
    anomaly_score = models.FloatField(null=True, blank=True)
    recommendation = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.NEW, db_index=True
    )
    dedup_key = models.CharField(max_length=180, db_index=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now_add=True)
    occurrences = models.PositiveIntegerField(default=1)
    escalation_level = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "dedup_key"],
                condition=~models.Q(status="RESOLVED"),
                name="uniq_open_alert_customer_dedup",
            )
        ]
        indexes = [
            models.Index(fields=["customer", "status", "severity"]),
            models.Index(fields=["machine", "dedup_key", "status"]),
        ]


class Anomaly(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="anomalies"
    )
    machine = models.ForeignKey(
        Machine, on_delete=models.CASCADE, related_name="anomalies"
    )
    metric = models.ForeignKey(
        "metrics.NormalizedMetric",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="anomalies",
    )
    detected_at = models.DateTimeField(auto_now_add=True, db_index=True)
    score = models.FloatField()
    threshold = models.FloatField()
    model_version = models.CharField(max_length=80)
    explanation = models.JSONField(default=dict)
    acknowledged = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["customer", "detected_at"]),
            models.Index(fields=["machine", "detected_at"]),
        ]


class Recommendation(models.Model):
    alert = models.OneToOneField(
        Alert, on_delete=models.CASCADE, related_name="structured_recommendation"
    )
    diagnosis_hints = models.JSONField(default=list)
    actions = models.JSONField(default=list)
    rationale = models.TextField()
    destructive = models.BooleanField(default=False)
    generated_at = models.DateTimeField(auto_now_add=True)


class AuditLog(models.Model):
    customer = models.ForeignKey(
        Customer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    actor = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=120)
    target_type = models.CharField(max_length=120, blank=True)
    target_id = models.CharField(max_length=120, blank=True)
    context = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
