"""Probe WebSocket réseau pour la validation finale.

Le script crée un tenant temporaire, utilise l'API HTTP pour obtenir deux tickets,
valide la diffusion via Daphne/Redis puis le replay après reconnexion. Toutes les
données créées sont supprimées en fin d'exécution.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import sys
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import websockets
from asgiref.sync import sync_to_async


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from accounts.models import Customer, User  # noqa: E402
from realtime.models import RealtimeEvent  # noqa: E402
from realtime.publisher import publish  # noqa: E402


API_URL = os.getenv("FINAL_API_URL", "http://127.0.0.1:8000/api").rstrip("/")
WS_URL = os.getenv("FINAL_WS_URL", "ws://127.0.0.1:8000/ws/events/")
ORIGIN = os.getenv("FINAL_ORIGIN", "http://127.0.0.1:5173")
PASSWORD = secrets.token_urlsafe(24)


def request_json(path: str, payload: dict, token: str = "") -> tuple[int, dict]:
    request = Request(
        f"{API_URL}{path}",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        body = json.loads(exc.read().decode() or "{}")
        return exc.code, body


@sync_to_async(thread_sensitive=True)
def create_fixture() -> tuple[Customer, User]:
    suffix = uuid.uuid4().hex[:10]
    customer = Customer.objects.create(
        name=f"Final WebSocket Probe {suffix}", slug=f"final-ws-{suffix}"
    )
    user = User.objects.create_user(
        username=f"final-ws-{suffix}",
        email=f"final-ws-{suffix}@example.invalid",
        password=PASSWORD,
        customer=customer,
        role=User.Role.ADMIN,
    )
    return customer, user


@sync_to_async(thread_sensitive=True)
def publish_event(customer: Customer, index: int) -> RealtimeEvent:
    return publish(
        customer,
        "metric.update",
        {"probe": True, "index": index},
        aggregate_id=f"final-probe-{index}",
    )


@sync_to_async(thread_sensitive=True)
def cleanup(customer: Customer) -> None:
    User.objects.filter(customer=customer).delete()
    customer.delete()


async def ticket(access: str) -> str:
    status, body = await asyncio.to_thread(
        request_json, "/realtime/ticket/", {}, access
    )
    if status != 200:
        raise RuntimeError(f"ticket HTTP {status}")
    return body["ticket"]


async def main() -> None:
    customer, user = await create_fixture()
    evidence: dict[str, object] = {}
    try:
        status, login = await asyncio.to_thread(
            request_json,
            "/auth/token/",
            {"email": user.email, "password": PASSWORD},
        )
        if status != 200:
            raise RuntimeError(f"login HTTP {status}")
        access = login["access"]
        first_ticket, second_ticket = await asyncio.gather(
            ticket(access), ticket(access)
        )
        async with (
            websockets.connect(
                f"{WS_URL}?{urlencode({'ticket': first_ticket})}",
                origin=ORIGIN,
            ) as first,
            websockets.connect(
                f"{WS_URL}?{urlencode({'ticket': second_ticket})}",
                origin=ORIGIN,
            ) as second,
        ):
            await publish_event(customer, 1)
            received = await asyncio.gather(
                asyncio.wait_for(first.recv(), 5),
                asyncio.wait_for(second.recv(), 5),
            )
            messages = [json.loads(item) for item in received]
            if any(item["event_type"] != "metric.update" for item in messages):
                raise RuntimeError("unexpected event type")
            sequence = messages[0]["sequence"]
            evidence["multiple_clients"] = 2
            evidence["broadcast_sequence_match"] = (
                sequence == messages[1]["sequence"]
            )

        missed = await publish_event(customer, 2)
        reconnect_ticket = await ticket(access)
        reconnect_url = f"{WS_URL}?{urlencode({'ticket': reconnect_ticket, 'since': sequence})}"
        async with websockets.connect(
            reconnect_url, origin=ORIGIN
        ) as reconnected:
            replay = json.loads(await asyncio.wait_for(reconnected.recv(), 5))
            evidence["replay_after_disconnect"] = replay["sequence"] == missed.sequence

        try:
            async with websockets.connect(
                reconnect_url, origin=ORIGIN
            ) as reused:
                await reused.recv()
        except websockets.exceptions.InvalidStatus as exc:
            evidence["reused_ticket_http_status"] = exc.response.status_code
        except websockets.exceptions.ConnectionClosed as exc:
            evidence["reused_ticket_close_code"] = exc.code
        if not (
            evidence.get("reused_ticket_http_status") == 403
            or evidence.get("reused_ticket_close_code") == 4401
        ):
            raise RuntimeError("reused ticket was not rejected")
        print(json.dumps(evidence, indent=2, sort_keys=True))
    finally:
        await cleanup(customer)


if __name__ == "__main__":
    asyncio.run(main())
