from django.core import signing

SALT = "infrasentinel.realtime.v1"


def issue_ticket(user):
    if not user.is_authenticated or not user.customer_id:
        raise ValueError("Un client est requis pour le flux temps réel.")
    return signing.dumps(
        {"user_id": user.pk, "customer_id": str(user.customer_id)},
        salt=SALT,
        compress=True,
    )


def verify_ticket(ticket):
    return signing.loads(ticket, salt=SALT, max_age=60)
