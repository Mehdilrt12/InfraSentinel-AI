import logging
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from .models import RealtimeEvent

logger = logging.getLogger(__name__)


def publish(customer, event_type, payload, aggregate_id=""):
    event = RealtimeEvent.objects.create(
        customer=customer,
        event_type=event_type,
        payload=payload,
        aggregate_id=str(aggregate_id),
    )

    def _send():
        try:
            async_to_sync(get_channel_layer().group_send)(
                f"tenant_{customer.pk}",
                {
                    "type": "tenant.event",
                    "event": {
                        "sequence": event.sequence,
                        "event_type": event.event_type,
                        "aggregate_id": event.aggregate_id,
                        "payload": event.payload,
                        "created_at": event.created_at.isoformat(),
                    },
                },
            )
        except Exception:
            logger.exception(
                "WebSocket delivery failed; event %s remains replayable", event.sequence
            )

    transaction.on_commit(_send)
    return event
