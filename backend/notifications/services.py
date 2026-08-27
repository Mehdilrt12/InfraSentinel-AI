import logging
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from monitoring.models import Alert
from .adapters import ADAPTERS
from .models import NotificationDelivery, NotificationEvent, NotificationPreference

logger = logging.getLogger(__name__)


@transaction.atomic
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

    def schedule():
        try:
            from .tasks import dispatch_pending_notifications

            dispatch_pending_notifications.delay()
        except Exception:
            logger.exception(
                "Notification scheduling failed; durable event remains pending"
            )

    transaction.on_commit(schedule)
    return event


TERMINAL_STATUSES = {
    NotificationDelivery.Status.SENT,
    NotificationDelivery.Status.FAILED,
    NotificationDelivery.Status.SUPPRESSED,
}
SEVERITY_RANK = {"INFO": 0, "WARNING": 1, "HIGH": 2, "CRITICAL": 3}


def recover_stale_deliveries(now=None):
    now = now or timezone.now()
    cutoff = now - timedelta(seconds=settings.NOTIFICATION_SENDING_TIMEOUT_SECONDS)
    return NotificationDelivery.objects.filter(
        status=NotificationDelivery.Status.SENDING,
        updated_at__lt=cutoff,
    ).update(
        status=NotificationDelivery.Status.RETRY,
        next_attempt_at=now,
        last_error="Worker interrompu pendant l'envoi; livraison replanifiée.",
        updated_at=now,
    )


def _cooldown_suppresses(delivery, now):
    if not delivery.event.alert_id:
        return False
    previous = (
        NotificationDelivery.objects.select_related("event")
        .filter(
            preference=delivery.preference,
            event__alert__dedup_key=delivery.event.alert.dedup_key,
            status=NotificationDelivery.Status.SENT,
            sent_at__gte=now - timedelta(seconds=delivery.preference.cooldown_seconds),
        )
        .exclude(pk=delivery.pk)
        .order_by("-sent_at")
        .first()
    )
    if not previous:
        return False
    return not (
        delivery.event.severity == "CRITICAL"
        and SEVERITY_RANK.get(previous.event.severity, 0) < SEVERITY_RANK["CRITICAL"]
    )


def deliver_notification(delivery_id):
    now = timezone.now()
    with transaction.atomic():
        delivery = NotificationDelivery.objects.select_for_update().get(pk=delivery_id)
        if delivery.status in TERMINAL_STATUSES:
            return delivery.status
        if delivery.status == NotificationDelivery.Status.SENDING:
            return "IN_PROGRESS"
        if delivery.status not in {
            NotificationDelivery.Status.PENDING,
            NotificationDelivery.Status.RETRY,
        }:
            return "IGNORED"
        if delivery.next_attempt_at and delivery.next_attempt_at > now:
            return "NOT_DUE"
        if _cooldown_suppresses(delivery, now):
            delivery.status = NotificationDelivery.Status.SUPPRESSED
            delivery.save(update_fields=["status", "updated_at"])
            return delivery.status
        delivery.status = NotificationDelivery.Status.SENDING
        delivery.attempts += 1
        delivery.save(update_fields=["status", "attempts", "updated_at"])
    try:
        adapter = ADAPTERS.get(delivery.preference.channel)
        if not adapter:
            raise RuntimeError(f"Canal {delivery.preference.channel} non implémenté.")
        provider_id = adapter.send(delivery)
    except Exception as exc:
        public_error = (
            f"Canal {delivery.preference.channel} non implémenté."
            if not adapter
            else "Échec d'envoi de la notification. Consultez les logs serveur."
        )
        logger.error(
            "Notification delivery failed delivery=%s channel=%s exception=%s",
            delivery.pk,
            delivery.preference.channel,
            type(exc).__name__,
        )
        delay = min(3600, 30 * (2 ** min(delivery.attempts, 7)))
        retrying = delivery.attempts < 8
        NotificationDelivery.objects.filter(pk=delivery.pk).update(
            status=(
                NotificationDelivery.Status.RETRY
                if retrying
                else NotificationDelivery.Status.FAILED
            ),
            next_attempt_at=now + timedelta(seconds=delay),
            last_error=public_error,
            updated_at=timezone.now(),
        )
        return "RETRY" if retrying else "FAILED"
    NotificationDelivery.objects.filter(pk=delivery.pk).update(
        status=NotificationDelivery.Status.SENT,
        sent_at=now,
        provider_id=provider_id,
        last_error="",
        updated_at=timezone.now(),
    )
    return "SENT"


def dispatch_due_notifications(limit=100):
    now = timezone.now()
    recovered = recover_stale_deliveries(now)
    ids = list(
        NotificationDelivery.objects.filter(
            status__in=[
                NotificationDelivery.Status.PENDING,
                NotificationDelivery.Status.RETRY,
            ],
            next_attempt_at__lte=now,
        )
        .order_by("next_attempt_at", "created_at")
        .values_list("pk", flat=True)[:limit]
    )
    results = [deliver_notification(delivery_id) for delivery_id in ids]
    pending_event_ids = NotificationDelivery.objects.exclude(
        status__in=TERMINAL_STATUSES
    ).values_list("event_id", flat=True)
    NotificationEvent.objects.filter(processed_at__isnull=True).exclude(
        pk__in=pending_event_ids
    ).update(processed_at=now)
    return {
        "processed": len(results),
        "sent": results.count("SENT"),
        "failed": results.count("FAILED"),
        "recovered": recovered,
    }
