import uuid
from django.db import models
from accounts.models import Customer, User
from monitoring.models import Alert, Severity


class NotificationPreference(models.Model):
    class Channel(models.TextChoices):
        EMAIL = "EMAIL", "Email"
        TEAMS = "TEAMS", "Microsoft Teams"
        SLACK = "SLACK", "Slack"
        TELEGRAM = "TELEGRAM", "Telegram"

    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="notification_preferences"
    )
    user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )
    channel = models.CharField(
        max_length=20, choices=Channel.choices, default=Channel.EMAIL
    )
    destination = models.CharField(max_length=500)
    minimum_severity = models.CharField(
        max_length=16, choices=Severity.choices, default=Severity.HIGH
    )
    enabled = models.BooleanField(default=True)
    cooldown_seconds = models.PositiveIntegerField(default=300)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "user", "channel", "destination"],
                name="uniq_notification_preference",
            )
        ]


class NotificationEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="notification_events"
    )
    alert = models.ForeignKey(
        Alert,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="notification_events",
    )
    event_type = models.CharField(max_length=80)
    severity = models.CharField(max_length=16, choices=Severity.choices)
    payload = models.JSONField(default=dict)
    dedup_key = models.CharField(max_length=180, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "dedup_key"],
                name="uniq_notification_event_customer_dedup",
            )
        ]


class NotificationDelivery(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente"
        SENDING = "SENDING", "En cours"
        SENT = "SENT", "Envoyée"
        RETRY = "RETRY", "À réessayer"
        FAILED = "FAILED", "Échec"
        SUPPRESSED = "SUPPRESSED", "Supprimée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(
        NotificationEvent, on_delete=models.CASCADE, related_name="deliveries"
    )
    preference = models.ForeignKey(
        NotificationPreference, on_delete=models.CASCADE, related_name="deliveries"
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    provider_id = models.CharField(max_length=255, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "preference"], name="uniq_delivery_event_preference"
            )
        ]
