from datetime import timedelta
from celery import shared_task
from django.db import transaction
from django.utils import timezone
from .adapters import ADAPTERS
from .models import NotificationDelivery, NotificationEvent


def _deliver(delivery_id):
    now = timezone.now()
    with transaction.atomic():
        delivery = NotificationDelivery.objects.select_for_update().get(pk=delivery_id)
        if delivery.status in {
            NotificationDelivery.Status.SENT,
            NotificationDelivery.Status.SUPPRESSED,
        }:
            return delivery.status
        previous = (
            NotificationDelivery.objects.filter(
                preference=delivery.preference,
                event__alert__dedup_key=delivery.event.alert.dedup_key,
                status=NotificationDelivery.Status.SENT,
                sent_at__gte=now
                - timedelta(seconds=delivery.preference.cooldown_seconds),
            )
            .exclude(pk=delivery.pk)
            .exists()
            if delivery.event.alert_id
            else False
        )
        if previous:
            delivery.status = NotificationDelivery.Status.SUPPRESSED
            delivery.save(update_fields=["status", "updated_at"])
            return delivery.status
        delivery.status = NotificationDelivery.Status.SENDING
        delivery.attempts += 1
        delivery.save(update_fields=["status", "attempts", "updated_at"])
    try:
        provider_id = ADAPTERS[delivery.preference.channel].send(delivery)
    except Exception as exc:
        delay = min(3600, 30 * (2 ** min(delivery.attempts, 7)))
        NotificationDelivery.objects.filter(pk=delivery.pk).update(
            status=NotificationDelivery.Status.RETRY
            if delivery.attempts < 8
            else NotificationDelivery.Status.FAILED,
            next_attempt_at=now + timedelta(seconds=delay),
            last_error=str(exc),
        )
        return "RETRY" if delivery.attempts < 8 else "FAILED"
    NotificationDelivery.objects.filter(pk=delivery.pk).update(
        status=NotificationDelivery.Status.SENT,
        sent_at=now,
        provider_id=provider_id,
        last_error="",
    )
    return "SENT"


@shared_task(name="notifications.dispatch_pending")
def dispatch_pending_notifications(limit=100):
    now = timezone.now()
    ids = list(
        NotificationDelivery.objects.filter(
            status__in=[
                NotificationDelivery.Status.PENDING,
                NotificationDelivery.Status.RETRY,
            ],
            next_attempt_at__lte=now,
        )
        .order_by("next_attempt_at")
        .values_list("pk", flat=True)[:limit]
    )
    results = [_deliver(delivery_id) for delivery_id in ids]
    NotificationEvent.objects.filter(
        deliveries__status=NotificationDelivery.Status.SENT, processed_at__isnull=True
    ).update(processed_at=now)
    return {
        "processed": len(results),
        "sent": results.count("SENT"),
        "failed": results.count("FAILED"),
    }
