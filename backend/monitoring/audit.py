import ipaddress
import re
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from django.conf import settings

from .models import Alert, AuditLog


SENSITIVE_KEY = re.compile(
    r"(?i)(password|passwd|secret|token|authorization|cookie|credential|api.?key)"
)


def client_ip(request):
    """Return a validated client IP without trusting forwarding headers by default."""
    if request is None:
        return None
    candidate = request.META.get("REMOTE_ADDR", "")
    trusted_hops = int(settings.REST_FRAMEWORK.get("NUM_PROXIES", 0) or 0)
    forwarded = [
        item.strip()
        for item in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")
        if item.strip()
    ]
    if trusted_hops and len(forwarded) >= trusted_hops:
        candidate = forwarded[-trusted_hops]
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def sanitize_metadata(value, depth=0):
    """Keep audit context useful while preventing accidental secret persistence."""
    if depth > 8:
        return "[TRUNCATED]"
    if isinstance(value, Mapping):
        return {
            str(key)[:120]: (
                "[REDACTED]"
                if SENSITIVE_KEY.search(str(key))
                else sanitize_metadata(item, depth + 1)
            )
            for key, item in list(value.items())[:100]
        }
    if isinstance(value, (list, tuple, set)):
        return [sanitize_metadata(item, depth + 1) for item in list(value)[:100]]
    if isinstance(value, (datetime, date, UUID, Decimal)):
        return str(value)
    if isinstance(value, str):
        return value[:2000]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:2000]


def request_change_metadata(request, *, operation, extra=None):
    fields = []
    if request is not None and hasattr(request, "data") and isinstance(request.data, Mapping):
        fields = sorted(
            str(key)
            for key in request.data
            if not SENSITIVE_KEY.search(str(key))
        )[:100]
    payload = {"operation": operation, "changed_fields": fields}
    if extra:
        payload.update(extra)
    return payload


def action_for_instance(instance, operation, previous=None):
    label = instance._meta.label_lower
    previous = previous or {}
    if label == "accounts.user":
        return {
            "create": AuditLog.Action.USER_CREATED,
            "update": AuditLog.Action.USER_UPDATED,
            "delete": AuditLog.Action.USER_DELETED,
        }[operation]
    if label == "inventory.machine":
        return {
            "create": AuditLog.Action.MACHINE_CREATED,
            "update": AuditLog.Action.MACHINE_UPDATED,
            "delete": AuditLog.Action.MACHINE_DELETED,
        }[operation]
    if label == "inventory.agent":
        if operation == "update" and previous.get("enabled") and not instance.enabled:
            return AuditLog.Action.AGENT_REVOKED
        return AuditLog.Action.AGENT_UPDATED
    if label == "monitoring.alert" and operation == "update":
        if previous.get("status") != instance.status:
            return {
                Alert.Status.ACKNOWLEDGED: AuditLog.Action.ALERT_ACKNOWLEDGED,
                Alert.Status.IN_PROGRESS: AuditLog.Action.ALERT_IN_PROGRESS,
                Alert.Status.RESOLVED: AuditLog.Action.ALERT_RESOLVED,
            }.get(instance.status, AuditLog.Action.ALERT_UPDATED)
        return AuditLog.Action.ALERT_UPDATED
    return AuditLog.Action.CONFIG_CHANGED


def record_audit(
    action,
    *,
    customer=None,
    actor=None,
    target=None,
    target_type="",
    target_id="",
    target_repr="",
    request=None,
    ip_address=None,
    metadata=None,
):
    if target is not None:
        target_type = target._meta.label
        target_id = str(target.pk)
        target_repr = str(target)
        customer = customer or getattr(target, "customer", None)
    authenticated_actor = actor if getattr(actor, "is_authenticated", False) else None
    return AuditLog.objects.create(
        customer=customer,
        actor=authenticated_actor,
        actor_email=getattr(authenticated_actor, "email", "") or "",
        action=action,
        target_type=str(target_type)[:120],
        target_id=str(target_id)[:120],
        target_repr=str(target_repr)[:255],
        ip_address=ip_address or client_ip(request),
        metadata=sanitize_metadata(metadata or {}),
    )
