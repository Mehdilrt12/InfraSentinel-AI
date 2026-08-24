from django.conf import settings
from django.core.mail import send_mail


class EmailAdapter:
    def send(self, delivery):
        payload = delivery.event.payload
        sent = send_mail(
            subject=f"[{delivery.event.severity}] InfraSentinel - {payload.get('machine', 'Infrastructure')}",
            message=f"{payload.get('message', '')}\n\nAlerte: {payload.get('alert_id', '')}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[delivery.preference.destination],
            fail_silently=False,
        )
        if sent != 1:
            raise RuntimeError("Le backend email n'a confirmé aucun envoi.")
        return "email"


ADAPTERS = {"EMAIL": EmailAdapter()}
