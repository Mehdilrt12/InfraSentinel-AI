import hashlib
import secrets
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from .models import Agent, EnrollmentCode, Environment, Machine


def _hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_enrollment_code(customer, environment, ttl_minutes=30):
    if not customer.active:
        raise ValueError("Le client est désactivé.")
    if environment.customer_id != customer.pk:
        raise ValueError("L'environnement appartient à un autre client.")
    if environment.kind not in {Environment.Kind.WINDOWS, Environment.Kind.MIXED}:
        raise ValueError(
            "L'enrollment Windows exige un environnement Windows ou mixte."
        )
    if not 1 <= ttl_minutes <= 1440:
        raise ValueError("Durée d'enrollment invalide.")
    raw = secrets.token_urlsafe(32)
    EnrollmentCode.objects.create(
        customer=customer,
        environment=environment,
        code_hash=_hash(raw),
        expires_at=timezone.now() + timedelta(minutes=ttl_minutes),
    )
    return raw


@transaction.atomic
def enroll_agent(
    code,
    *,
    external_id,
    hostname,
    ip_address=None,
    os_information=None,
    version="",
    audit_ip=None,
):
    enrollment = (
        EnrollmentCode.objects.select_for_update()
        .select_related("customer", "environment")
        .filter(code_hash=_hash(code))
        .first()
    )
    if not enrollment or enrollment.used_at or enrollment.expires_at <= timezone.now():
        raise ValueError("Code d'enrollment invalide ou expiré.")
    if not enrollment.customer.active:
        raise ValueError("Code d'enrollment invalide ou expiré.")
    machine, machine_created = Machine.objects.update_or_create(
        customer=enrollment.customer,
        source_type=Environment.Kind.WINDOWS,
        external_id=external_id,
        defaults={
            "environment": enrollment.environment,
            "hostname": hostname,
            "ip_address": ip_address,
            "os_information": os_information or {},
            "status": Machine.Status.ONLINE,
            "last_seen": timezone.now(),
            "agent_version": version,
        },
    )
    raw_token = secrets.token_urlsafe(48)
    agent, _ = Agent.objects.update_or_create(
        machine=machine,
        defaults={
            "customer": enrollment.customer,
            "token_hash": _hash(raw_token),
            "enabled": True,
            "version": version,
        },
    )
    enrollment.used_at = timezone.now()
    enrollment.save(update_fields=["used_at"])
    from monitoring.audit import record_audit
    from monitoring.models import AuditLog

    record_audit(
        (
            AuditLog.Action.MACHINE_CREATED
            if machine_created
            else AuditLog.Action.MACHINE_UPDATED
        ),
        customer=enrollment.customer,
        target=machine,
        ip_address=audit_ip,
        metadata={"source": "agent_enrollment"},
    )
    record_audit(
        AuditLog.Action.AGENT_ENROLLED,
        customer=enrollment.customer,
        target=agent,
        ip_address=audit_ip,
        metadata={
            "machine_id": str(machine.pk),
            "environment_id": str(enrollment.environment_id),
            "version": version,
        },
    )
    return agent, raw_token


def authenticate_agent(raw_token):
    if not raw_token:
        return None
    return (
        Agent.objects.select_related("customer", "machine__environment")
        .filter(token_hash=_hash(raw_token), enabled=True, customer__active=True)
        .first()
    )
