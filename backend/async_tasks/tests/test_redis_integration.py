import os
import uuid
from unittest import skipUnless

import redis
from django.conf import settings
from django.test import SimpleTestCase
from kombu import Connection


@skipUnless(
    os.getenv("INFRASENTINEL_RUN_REDIS_INTEGRATION") == "1",
    "NOT TESTED — REAL REDIS INTEGRATION",
)
class RedisIntegrationTests(SimpleTestCase):
    def test_connection_set_get_and_reconnect(self):
        client = redis.Redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=True,
        )
        key = f"infrasentinel:test:{uuid.uuid4()}"
        try:
            self.assertTrue(client.ping())
            client.set(key, "phase-17.5", ex=30)
            self.assertEqual(client.get(key), "phase-17.5")
            client.connection_pool.disconnect()
            self.assertEqual(client.get(key), "phase-17.5")
        finally:
            client.delete(key)
            client.connection_pool.disconnect()

    def test_celery_broker_round_trip_on_isolated_queue(self):
        queue_name = f"infrasentinel-test-{uuid.uuid4()}"
        with Connection(settings.CELERY_BROKER_URL, connect_timeout=2) as connection:
            connection.ensure_connection(max_retries=1)
            queue = connection.SimpleQueue(queue_name)
            try:
                queue.put({"probe": "phase-17.5"})
                message = queue.get(block=True, timeout=2)
                self.assertEqual(message.payload, {"probe": "phase-17.5"})
                message.ack()
            finally:
                queue.close()

    def test_temporary_outage_fails_fast_without_affecting_unit_suite(self):
        unavailable = redis.Redis(
            host="127.0.0.1",
            port=1,
            socket_connect_timeout=0.1,
            socket_timeout=0.1,
        )
        with self.assertRaises(redis.RedisError):
            unavailable.ping()
