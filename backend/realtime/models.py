from django.db import models
from accounts.models import Customer, User


class RealtimeEvent(models.Model):
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="realtime_events"
    )
    sequence = models.BigAutoField(primary_key=True)
    event_type = models.CharField(max_length=80, db_index=True)
    aggregate_id = models.CharField(max_length=120, blank=True)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["customer", "sequence"])]


class RealtimeTicket(models.Model):
    nonce_hash = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="realtime_tickets")
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="realtime_tickets"
    )
    expires_at = models.DateTimeField(db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
