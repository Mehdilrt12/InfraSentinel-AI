import hashlib
import secrets
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from .models import Agent, EnrollmentCode, Machine


def _hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_enrollment_code(customer, environment, ttl_minutes=30):
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
    code, *, external_id, hostname, ip_address=None, os_information=None, version=""
):
    enrollment = (
        EnrollmentCode.objects.select_for_update()
        .select_related("customer", "environment")
        .filter(code_hash=_hash(code))
        .first()
    )
    if not enrollment or enrollment.used_at or enrollment.expires_at <= timezone.now():
        raise ValueError("Code d'enrollment invalide ou expiré.")
    machine, _ = Machine.objects.update_or_create(
        customer=enrollment.customer,
        source_type=Machine._meta.get_field("source_type").choices[0][0],
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
    return agent, raw_token


def authenticate_agent(raw_token):
    if not raw_token:
        return None
    return (
        Agent.objects.select_related("customer", "machine__environment")
        .filter(token_hash=_hash(raw_token), enabled=True)
        .first()
    )
