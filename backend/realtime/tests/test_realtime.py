from unittest.mock import patch

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase
from django.core import signing

from accounts.models import Customer, User
from common.testing import TEST_PASSWORD, TenantAPITestCase
from config.asgi import application
from realtime.models import RealtimeEvent
from realtime.publisher import publish
from realtime.tickets import issue_ticket, verify_ticket


class RealtimeHTTPAndPublisherTests(TenantAPITestCase):
    def test_ticket_round_trip_and_ticket_endpoint_require_customer(self):
        ticket = issue_ticket(self.admin_a)
        claims = verify_ticket(ticket)
        self.assertEqual(claims["user_id"], self.admin_a.pk)
        self.assertEqual(claims["customer_id"], str(self.customer_a.pk))
        with self.assertRaises(signing.BadSignature):
            verify_ticket(ticket)
        self.authenticate()
        response = self.client.post("/api/realtime/ticket/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["expires_in"], 60)

        superuser = User.objects.create_superuser(
            username="global", email="global@admin.test", password=TEST_PASSWORD
        )
        self.authenticate(superuser)
        self.assertEqual(
            self.client.post("/api/realtime/ticket/", {}, format="json").status_code,
            403,
        )

    def test_http_replay_is_ordered_filtered_and_tenant_isolated(self):
        own_first = RealtimeEvent.objects.create(
            customer=self.customer_a,
            event_type="machine.online",
            aggregate_id="one",
            payload={"online": True},
        )
        own_second = RealtimeEvent.objects.create(
            customer=self.customer_a,
            event_type="alert.created",
            aggregate_id="two",
            payload={"severity": "HIGH"},
        )
        RealtimeEvent.objects.create(
            customer=self.customer_b,
            event_type="alert.created",
            aggregate_id="foreign",
            payload={"severity": "CRITICAL"},
        )
        self.authenticate()
        response = self.client.get(f"/api/realtime/replay/?since={own_first.sequence}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["sequence"] for row in response.data], [own_second.sequence])
        self.assertNotIn("foreign", {row["aggregate_id"] for row in response.data})

    def test_websocket_failure_keeps_durable_replay_event(self):
        class FailingLayer:
            async def group_send(self, *_args, **_kwargs):
                raise OSError("channel unavailable")

        with (
            patch("realtime.publisher.get_channel_layer", return_value=FailingLayer()),
            self.assertLogs("realtime.publisher", level="ERROR") as logs,
            self.captureOnCommitCallbacks(execute=True),
        ):
            event = publish(
                self.customer_a,
                "metric.update",
                {"metric_name": "system.cpu.utilization"},
                "machine-1",
            )
        self.assertTrue(RealtimeEvent.objects.filter(pk=event.pk).exists())
        self.assertTrue(any("remains replayable" in line for line in logs.output))


class RealtimeTenantWebSocketTests(TransactionTestCase):
    def setUp(self):
        self.customer_a = Customer.objects.create(name="Realtime A", slug="realtime-a")
        self.customer_b = Customer.objects.create(name="Realtime B", slug="realtime-b")
        self.user_a = User.objects.create_user(
            username="realtime-a",
            email="realtime-a@test.invalid",
            password=TEST_PASSWORD,
            customer=self.customer_a,
            role=User.Role.ADMIN,
        )
        self.user_b = User.objects.create_user(
            username="realtime-b",
            email="realtime-b@test.invalid",
            password=TEST_PASSWORD,
            customer=self.customer_b,
            role=User.Role.ADMIN,
        )

    def test_disabled_user_ticket_is_rejected(self):
        ticket = issue_ticket(self.user_a)
        self.user_a.is_active = False
        self.user_a.save(update_fields=["is_active"])

        async def scenario():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/events/?ticket={ticket}&since=0",
                headers=[(b"origin", b"http://127.0.0.1:5173")],
            )
            connected, code = await communicator.connect()
            self.assertFalse(connected)
            self.assertEqual(code, 4403)

        async_to_sync(scenario)()

    def test_untrusted_websocket_origin_is_rejected(self):
        ticket = issue_ticket(self.user_a)

        async def scenario():
            communicator = WebsocketCommunicator(
                application,
                f"/ws/events/?ticket={ticket}&since=0",
                headers=[(b"origin", b"https://evil.example")],
            )
            connected, _ = await communicator.connect()
            self.assertFalse(connected)

        async_to_sync(scenario)()

    def test_live_event_is_delivered_only_to_matching_customer_group(self):
        ticket_a = issue_ticket(self.user_a)
        ticket_b = issue_ticket(self.user_b)

        async def scenario():
            client_a = WebsocketCommunicator(
                application,
                f"/ws/events/?ticket={ticket_a}&since=0",
                headers=[(b"origin", b"http://127.0.0.1:5173")],
            )
            client_b = WebsocketCommunicator(
                application,
                f"/ws/events/?ticket={ticket_b}&since=0",
                headers=[(b"origin", b"http://127.0.0.1:5173")],
            )
            self.assertTrue((await client_a.connect())[0])
            self.assertTrue((await client_b.connect())[0])
            event = {
                "sequence": 501,
                "event_type": "anomaly.detected",
                "aggregate_id": "anomaly-a",
                "payload": {"customer": "A"},
                "created_at": "2026-01-01T00:00:00Z",
            }
            await get_channel_layer().group_send(
                f"tenant_{self.customer_a.pk}",
                {"type": "tenant.event", "event": event},
            )
            self.assertEqual((await client_a.receive_json_from())["sequence"], 501)
            self.assertTrue(await client_b.receive_nothing(timeout=0.1))
            await client_a.disconnect()
            await client_b.disconnect()

        async_to_sync(scenario)()
