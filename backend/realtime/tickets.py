import hashlib
import secrets
from datetime import timedelta

from django.core import signing
from django.db import transaction
from django.utils import timezone

from .models import RealtimeTicket

SALT = "infrasentinel.realtime.v1"


def issue_ticket(user):
    if (
        not user.is_authenticated
        or not user.is_active
        or not user.customer_id
        or not user.customer.active
    ):
        raise ValueError("Un client est requis pour le flux temps réel.")
    now = timezone.now()
    RealtimeTicket.objects.filter(expires_at__lt=now - timedelta(days=1)).delete()
    nonce = secrets.token_urlsafe(32)
    RealtimeTicket.objects.create(
        nonce_hash=hashlib.sha256(nonce.encode()).hexdigest(),
        user=user,
        customer=user.customer,
        expires_at=now + timedelta(seconds=60),
    )
    return signing.dumps(
        {
            "nonce": nonce,
            "user_id": user.pk,
            "customer_id": str(user.customer_id),
        },
        salt=SALT,
        compress=True,
    )


def verify_ticket(ticket):
    claims = signing.loads(ticket, salt=SALT, max_age=60)
    nonce_hash = hashlib.sha256(claims.get("nonce", "").encode()).hexdigest()
    with transaction.atomic():
        stored = (
            RealtimeTicket.objects.select_for_update()
            .filter(
                nonce_hash=nonce_hash,
                user_id=claims.get("user_id"),
                customer_id=claims.get("customer_id"),
                used_at__isnull=True,
                expires_at__gt=timezone.now(),
            )
            .first()
        )
        if not stored:
            raise signing.BadSignature("Ticket invalide, expiré ou déjà utilisé.")
        stored.used_at = timezone.now()
        stored.save(update_fields=["used_at"])
    return claims
