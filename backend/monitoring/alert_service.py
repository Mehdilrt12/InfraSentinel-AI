import hashlib
from django.db import transaction
from django.utils import timezone
from .models import Alert, Recommendation
from .recommendations import build_recommendation

SEVERITY_ORDER = {"INFO": 0, "WARNING": 1, "HIGH": 2, "CRITICAL": 3}


def _dedup(machine, alert_type, source_key):
    raw = f"{machine.pk}:{alert_type}:{source_key}".encode()
    return hashlib.sha256(raw).hexdigest()


@transaction.atomic
def create_or_update_alert(
    *,
    machine,
    alert_type,
    severity,
    source,
    message,
    context=None,
    anomaly_score=None,
    source_key="",
    cooldown_seconds=0,
):
    dedup_key = _dedup(machine, alert_type, source_key or alert_type)
    alert = (
        Alert.objects.select_for_update()
        .filter(
            customer=machine.customer,
            dedup_key=dedup_key,
        )
        .exclude(status=Alert.Status.RESOLVED)
        .order_by("-timestamp")
        .first()
    )
    created = alert is None
    changed = created
    now = timezone.now()
    if alert:
        outside_cooldown = (
            now - alert.last_seen_at
        ).total_seconds() >= cooldown_seconds
        if outside_cooldown:
            alert.occurrences += 1
            alert.last_seen_at = now
            alert.context = {**alert.context, **(context or {})}
            changed = True
        if SEVERITY_ORDER.get(severity, 0) > SEVERITY_ORDER.get(alert.severity, 0):
            alert.severity = severity
            alert.escalation_level += 1
            changed = True
        if anomaly_score is not None:
            alert.anomaly_score = anomaly_score
            changed = True
        alert.save()
    else:
        rec = build_recommendation(
            (context or {}).get("metric_name", alert_type), context
        )
        alert = Alert.objects.create(
            customer=machine.customer,
            machine=machine,
            type=alert_type,
            severity=severity,
            source=source,
            message=message,
            context=context or {},
            anomaly_score=anomaly_score,
            recommendation="; ".join(rec["actions"]),
            dedup_key=dedup_key,
        )
        Recommendation.objects.create(alert=alert, **rec)

    if changed:
        from realtime.publisher import publish

        publish(
            machine.customer,
            "alert.created" if created else "alert.updated",
            {
                "id": str(alert.pk),
                "machine_id": str(machine.pk),
                "severity": alert.severity,
                "status": alert.status,
                "message": alert.message,
                "occurrences": alert.occurrences,
            },
            alert.pk,
        )
    if changed and alert.severity in {"HIGH", "CRITICAL"}:
        from notifications.services import queue_alert_notification

        transaction.on_commit(
            lambda: queue_alert_notification(
                alert.pk, "alert.created" if created else "alert.updated"
            )
        )
    return alert, created
