from django.db import models
from accounts.models import Customer


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
