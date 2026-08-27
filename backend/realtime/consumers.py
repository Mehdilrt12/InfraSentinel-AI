import asyncio
from urllib.parse import parse_qs
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from accounts.models import User
from .models import RealtimeEvent
from .tickets import verify_ticket


class TenantEventConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        query = parse_qs(self.scope.get("query_string", b"").decode())
        ticket = (query.get("ticket") or [""])[0]
        try:
            since = int((query.get("since") or [0])[0] or 0)
            if since < 0:
                raise ValueError("since must be non-negative")
            claims = await self._verify_ticket(ticket)
            user = await self._user(claims["user_id"], claims["customer_id"])
        except Exception:
            await self.close(code=4401)
            return
        if not user:
            await self.close(code=4403)
            return
        self.customer_id = claims["customer_id"]
        self.user_id = claims["user_id"]
        self.group_name = f"tenant_{self.customer_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        self.expiry_task = asyncio.create_task(self._expire_connection())
        events = await self._replay(self.customer_id, since)
        for event in events:
            await self.send_json(event)

    async def disconnect(self, _code):
        expiry_task = getattr(self, "expiry_task", None)
        if expiry_task and expiry_task is not asyncio.current_task():
            expiry_task.cancel()
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def tenant_event(self, event):
        if not await self._user(self.user_id, self.customer_id):
            await self.close(code=4403)
            return
        await self.send_json(event["event"])

    async def _expire_connection(self):
        await asyncio.sleep(settings.WEBSOCKET_SESSION_MAX_SECONDS)
        await self.close(code=4401)

    @database_sync_to_async
    def _verify_ticket(self, ticket):
        return verify_ticket(ticket)

    @database_sync_to_async
    def _user(self, user_id, customer_id):
        return User.objects.filter(
            pk=user_id,
            customer_id=customer_id,
            customer__active=True,
            is_active=True,
        ).first()

    @database_sync_to_async
    def _replay(self, customer_id, since):
        rows = RealtimeEvent.objects.filter(
            customer_id=customer_id, sequence__gt=since
        ).order_by("sequence")[:500]
        return [
            {
                "sequence": row.sequence,
                "event_type": row.event_type,
                "aggregate_id": row.aggregate_id,
                "payload": row.payload,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
