import logging
from django.utils import timezone
from monitoring.models import Alert
from .models import NotificationDelivery, NotificationEvent, NotificationPreference

logger = logging.getLogger(__name__)


def queue_alert_notification(alert_id, event_type):
    alert = (
        Alert.objects.select_related("customer", "machine").filter(pk=alert_id).first()
    )
    if not alert or alert.severity not in {"HIGH", "CRITICAL"}:
        return None
    event, created = NotificationEvent.objects.get_or_create(
        customer=alert.customer,
        dedup_key=f"{alert.dedup_key}:{event_type}:{alert.occurrences}",
        defaults={
            "alert": alert,
            "event_type": event_type,
            "severity": alert.severity,
            "payload": {
                "alert_id": str(alert.pk),
                "machine": alert.machine.hostname,
                "message": alert.message,
                "severity": alert.severity,
            },
        },
    )
    if not created:
        return event
    preferences = NotificationPreference.objects.filter(
        customer=alert.customer,
        enabled=True,
        channel=NotificationPreference.Channel.EMAIL,
    )
    ranks = {"INFO": 0, "WARNING": 1, "HIGH": 2, "CRITICAL": 3}
    for pref in preferences:
        if ranks[alert.severity] >= ranks[pref.minimum_severity]:
            NotificationDelivery.objects.get_or_create(
                event=event,
                preference=pref,
                defaults={"next_attempt_at": timezone.now()},
            )
    try:
        from .tasks import dispatch_pending_notifications

        dispatch_pending_notifications.delay()
    except Exception:
        logger.exception(
            "Notification scheduling failed; durable event remains pending"
        )
    return event
