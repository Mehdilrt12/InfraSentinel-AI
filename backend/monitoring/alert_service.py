import hashlib
from django.db import transaction
from django.utils import timezone
from inventory.models import Machine
from .audit import record_audit
from .models import Alert, AuditLog, Recommendation
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
    Machine.objects.select_for_update().only("pk").get(pk=machine.pk)
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
            changed = changed or outside_cooldown
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
        record_audit(
            AuditLog.Action.ALERT_CREATED,
            customer=machine.customer,
            target=alert,
            metadata={
                "machine_id": str(machine.pk),
                "severity": severity,
                "source": source,
                "type": alert_type,
            },
        )

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


@transaction.atomic
def resolve_open_alert(machine, alert_type, source_key, reason="condition_cleared"):
    Machine.objects.select_for_update().only("pk").get(pk=machine.pk)
    dedup_key = _dedup(machine, alert_type, source_key or alert_type)
    alert = (
        Alert.objects.select_for_update()
        .filter(
            customer=machine.customer,
            dedup_key=dedup_key,
        )
        .exclude(status=Alert.Status.RESOLVED)
        .first()
    )
    if not alert:
        return None
    alert.status = Alert.Status.RESOLVED
    alert.last_seen_at = timezone.now()
    alert.context = {**alert.context, "resolution_reason": reason}
    alert.save(update_fields=["status", "last_seen_at", "context", "updated_at"])
    record_audit(
        AuditLog.Action.ALERT_RESOLVED,
        customer=machine.customer,
        target=alert,
        metadata={"machine_id": str(machine.pk), "reason": reason, "actor": "system"},
    )
    from realtime.publisher import publish

    publish(
        machine.customer,
        "alert.updated",
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
    return alert


@transaction.atomic
def resolve_machine_alerts(machine, alert_type, reason="machine_recovered"):
    Machine.objects.select_for_update().only("pk").get(pk=machine.pk)
    alerts = list(
        Alert.objects.select_for_update().filter(
            customer=machine.customer,
            machine=machine,
            type=alert_type,
        )
        .exclude(status=Alert.Status.RESOLVED)
        .values_list("dedup_key", flat=True)
    )
    resolved = 0
    for dedup_key in alerts:
        alert = (
            Alert.objects.select_for_update().filter(
                customer=machine.customer,
                machine=machine,
                dedup_key=dedup_key,
            )
            .exclude(status=Alert.Status.RESOLVED)
            .first()
        )
        if alert:
            alert.status = Alert.Status.RESOLVED
            alert.last_seen_at = timezone.now()
            alert.context = {**alert.context, "resolution_reason": reason}
            alert.save(
                update_fields=["status", "last_seen_at", "context", "updated_at"]
            )
            record_audit(
                AuditLog.Action.ALERT_RESOLVED,
                customer=machine.customer,
                target=alert,
                metadata={
                    "machine_id": str(machine.pk),
                    "reason": reason,
                    "actor": "system",
                },
            )
            from realtime.publisher import publish

            publish(
                machine.customer,
                "alert.updated",
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
            resolved += 1
    return resolved
