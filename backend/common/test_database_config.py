import unittest

from django.conf import settings
from django.test import SimpleTestCase


@unittest.skipUnless(
    settings.DATABASES["default"]["ENGINE"].endswith("postgresql"),
    "Configuration spécifique à PostgreSQL.",
)
class PostgreSQLConnectionConfigurationTests(SimpleTestCase):
    def test_asgi_uses_non_persistent_connections_and_a_bounded_pool(self):
        database = settings.DATABASES["default"]
        pool = database["OPTIONS"].get("pool")

        self.assertEqual(database["CONN_MAX_AGE"], 0)
        self.assertIsInstance(pool, dict)
        self.assertGreaterEqual(pool["min_size"], 0)
        self.assertGreaterEqual(pool["max_size"], 1)
        self.assertLessEqual(pool["max_size"], 50)
        self.assertLessEqual(pool["min_size"], pool["max_size"])
        self.assertGreater(pool["timeout"], 0)
