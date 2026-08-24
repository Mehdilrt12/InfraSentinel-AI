import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from infrasentinel_agent.client import AgentAPIError, AgentClient
from infrasentinel_agent.config import AgentConfig
from infrasentinel_agent.spool import Spool


class AgentConfigTests(unittest.TestCase):
    def test_remote_http_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {"backend_url": "http://example.com", "machine_name": "host"}
                )
            )
            with self.assertRaises(ValueError):
                AgentConfig.load(path)


class SpoolTests(unittest.TestCase):
    def test_fifo_and_limit_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spool.sqlite3"
            spool = Spool(path, 2)
            spool.push({"n": 1})
            spool.push({"n": 2})
            spool.push({"n": 3})
            self.assertEqual([item[1]["n"] for item in Spool(path, 2).peek()], [2, 3])


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.config = AgentConfig("https://server.example", "host")
        self.client = AgentClient(self.config, "secret-token")

    @patch("requests.Session.post")
    def test_token_is_header_only_and_response_validated(self, post):
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {"status": "ok"}
        post.return_value = response
        self.client.heartbeat("2.0.0")
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs["headers"]["X-Agent-Token"], "secret-token")
        self.assertNotIn("secret-token", str(kwargs["json"]))

    @patch("requests.Session.post")
    def test_invalid_token_is_not_retryable(self, post):
        post.return_value = Mock(ok=False, status_code=401)
        with self.assertRaises(AgentAPIError) as caught:
            self.client.heartbeat("2.0.0")
        self.assertFalse(caught.exception.retryable)


if __name__ == "__main__":
    unittest.main()
