import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import requests
from infrasentinel_agent.client import AgentAPIError, AgentClient
from infrasentinel_agent.collector import WindowsCollector
from infrasentinel_agent.config import AgentConfig
from infrasentinel_agent.credentials import CredentialStore
from infrasentinel_agent.runtime import AgentRuntime
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

    def test_local_http_requires_explicit_opt_in_and_environment_can_override_url(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "backend_url": "http://127.0.0.1:8000",
                        "machine_name": "host",
                        "allow_http_localhost": True,
                    }
                )
            )
            config = AgentConfig.load(path)
            self.assertEqual(config.backend_url, "http://127.0.0.1:8000")
            with patch.dict(
                "os.environ", {"INFRASENTINEL_SERVER_URL": "https://central.test"}
            ):
                overridden = AgentConfig.load(path)
            self.assertEqual(overridden.backend_url, "https://central.test")

    def test_invalid_intervals_and_malformed_configuration_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text("not-json")
            with self.assertRaises(json.JSONDecodeError):
                AgentConfig.load(path)
            path.write_text(
                json.dumps(
                    {
                        "backend_url": "https://central.test",
                        "machine_name": "host",
                        "interval_seconds": 4,
                    }
                )
            )
            with self.assertRaises(ValueError):
                AgentConfig.load(path)

    def test_insecure_tls_and_credentials_in_url_require_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "backend_url": "https://user:password@central.test/path",
                        "machine_name": "host",
                    }
                )
            )
            with self.assertRaises(ValueError):
                AgentConfig.load(path)
            path.write_text(
                json.dumps(
                    {
                        "backend_url": "https://central.test",
                        "machine_name": "host",
                        "verify_tls": False,
                    }
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

    def test_peek_limit_delete_and_count_are_durable(self):
        with tempfile.TemporaryDirectory() as directory:
            spool = Spool(Path(directory) / "spool.sqlite3", 10)
            for value in range(4):
                spool.push({"n": value})
            rows = spool.peek(limit=2)
            self.assertEqual([payload["n"] for _, payload in rows], [0, 1])
            spool.delete(rows[0][0])
            self.assertEqual(spool.count(), 3)
            self.assertEqual(Spool(spool.path, 10).peek()[0][1]["n"], 1)

    @unittest.skipUnless(os.name == "nt", "DPAPI est spécifique à Windows")
    def test_windows_spool_encrypts_payload_at_rest(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spool.sqlite3"
            spool = Spool(path, 10)
            spool.push({"metric_name": "sensitive.service", "value": 1})
            connection = sqlite3.connect(path)
            try:
                raw = connection.execute("SELECT payload FROM queue").fetchone()[0]
            finally:
                connection.close()
            self.assertTrue(raw.startswith("dpapi:"))
            self.assertNotIn("sensitive.service", raw)
            self.assertEqual(spool.peek()[0][1]["metric_name"], "sensitive.service")


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
        self.assertFalse(kwargs["allow_redirects"])

    @patch("requests.Session.post")
    def test_redirect_is_not_followed_to_protect_agent_token(self, post):
        post.return_value = Mock(ok=False, status_code=302)
        with self.assertRaisesRegex(AgentAPIError, "Redirection"):
            self.client.heartbeat("2.0.0")
        self.assertFalse(post.call_args.kwargs["allow_redirects"])

    @patch("requests.Session.post")
    def test_invalid_token_is_not_retryable(self, post):
        post.return_value = Mock(ok=False, status_code=401)
        with self.assertRaises(AgentAPIError) as caught:
            self.client.heartbeat("2.0.0")
        self.assertFalse(caught.exception.retryable)

    @patch("requests.Session.post", side_effect=requests.ConnectionError("offline"))
    def test_unavailable_server_is_retryable(self, _post):
        with self.assertRaises(AgentAPIError) as caught:
            self.client.heartbeat("2.0.0")
        self.assertTrue(caught.exception.retryable)

    @patch("requests.Session.post")
    def test_rate_limit_and_server_errors_are_retryable(self, post):
        for status in (429, 500, 503):
            post.return_value = Mock(ok=False, status_code=status)
            with self.subTest(status=status), self.assertRaises(AgentAPIError) as caught:
                self.client.heartbeat("2.0.0")
            self.assertTrue(caught.exception.retryable)

    @patch("requests.Session.post")
    def test_client_errors_and_missing_token_are_not_retryable(self, post):
        post.return_value = Mock(ok=False, status_code=400)
        with self.assertRaises(AgentAPIError) as caught:
            self.client.heartbeat("2.0.0")
        self.assertFalse(caught.exception.retryable)
        unauthenticated = AgentClient(self.config)
        with self.assertRaises(AgentAPIError) as missing:
            unauthenticated.heartbeat("2.0.0")
        self.assertFalse(missing.exception.retryable)

    @patch("requests.Session.post")
    def test_non_json_and_non_object_server_responses_are_rejected(self, post):
        response = Mock(ok=True, status_code=200)
        response.json.side_effect = ValueError("invalid json")
        post.return_value = response
        with self.assertRaisesRegex(AgentAPIError, "non JSON") as invalid_json:
            self.client.heartbeat("2.0.0")
        self.assertFalse(invalid_json.exception.retryable)
        response.json.side_effect = None
        response.json.return_value = ["unexpected"]
        with self.assertRaisesRegex(AgentAPIError, "Structure") as invalid_shape:
            self.client.heartbeat("2.0.0")
        self.assertFalse(invalid_shape.exception.retryable)


class CredentialStoreTests(unittest.TestCase):
    def test_test_mode_store_round_trip_and_plaintext_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CredentialStore(Path(directory) / "credential.bin")
            with (
                patch("infrasentinel_agent.credentials.os.name", "posix"),
                patch.dict(
                    "os.environ", {"INFRASENTINEL_ALLOW_PLAINTEXT_TEST_TOKEN": "1"}
                ),
            ):
                store.save("sensitive-token")
                self.assertEqual(store.load(), "sensitive-token")
            with (
                patch("infrasentinel_agent.credentials.os.name", "posix"),
                patch.dict("os.environ", {}, clear=True),
            ):
                with self.assertRaises(RuntimeError):
                    store.load()


class CollectorTests(unittest.TestCase):
    @patch("infrasentinel_agent.collector.psutil.net_io_counters")
    @patch("infrasentinel_agent.collector.psutil.disk_io_counters")
    @patch("infrasentinel_agent.collector.psutil.disk_partitions", return_value=[])
    @patch("infrasentinel_agent.collector.psutil.pids", return_value=[1, 2, 3])
    @patch("infrasentinel_agent.collector.psutil.boot_time", return_value=1)
    @patch("infrasentinel_agent.collector.psutil.cpu_percent", return_value=25)
    @patch("infrasentinel_agent.collector.psutil.virtual_memory")
    def test_core_metrics_and_rate_metrics_are_collected(
        self,
        memory,
        _cpu,
        _boot,
        _pids,
        _partitions,
        disk,
        network,
    ):
        memory.return_value = SimpleNamespace(percent=40, available=60, total=100)
        disk.side_effect = [
            SimpleNamespace(read_bytes=100, write_bytes=200),
            SimpleNamespace(read_bytes=300, write_bytes=500),
        ]
        network.side_effect = [
            SimpleNamespace(bytes_recv=1000, bytes_sent=2000),
            SimpleNamespace(bytes_recv=1600, bytes_sent=2800),
        ]
        collector = WindowsCollector(AgentConfig("https://server.example", "host"))
        with (
            patch.object(collector, "_latency", return_value=(10, "ok")),
            patch.object(collector, "_gpu", return_value=[]),
            patch.object(collector, "_services", return_value=[]),
            patch("infrasentinel_agent.collector.time.monotonic", side_effect=[10, 12]),
        ):
            first = collector.collect()
            second = collector.collect()
        first_names = {item["metric_name"] for item in first}
        second_names = {item["metric_name"] for item in second}
        self.assertTrue(
            {
                "system.cpu.utilization",
                "system.memory.utilization",
                "system.uptime",
                "system.process.count",
                "system.network.latency",
            }.issubset(first_names)
        )
        self.assertTrue(
            {
                "system.disk.io.read",
                "system.disk.io.write",
                "system.network.in",
                "system.network.out",
            }.issubset(second_names)
        )

    def test_unreachable_latency_gpu_absence_and_service_failure_are_safe(self):
        collector = WindowsCollector(
            AgentConfig(
                "https://server.example",
                "host",
                critical_services=["CriticalSvc"],
            )
        )
        with patch(
            "infrasentinel_agent.collector.socket.create_connection",
            side_effect=TimeoutError("timeout"),
        ):
            latency, status = collector._latency()
        self.assertIsNone(latency)
        self.assertEqual(status, "unreachable")
        with patch("infrasentinel_agent.collector.shutil.which", return_value=None):
            self.assertEqual(collector._gpu("timestamp"), [])
        with (
            patch("infrasentinel_agent.collector.platform.system", return_value="Windows"),
            patch(
                "infrasentinel_agent.collector.psutil.win_service_get",
                side_effect=OSError("missing"),
                create=True,
            ),
        ):
            services = collector._services("timestamp")
        self.assertEqual(services[0]["metric_name"], "windows.service.state")
        self.assertEqual(services[0]["metric_value"], 0)
        self.assertEqual(services[0]["status"], "not_found")


class RuntimeTests(unittest.TestCase):
    class OneCycleStop:
        stopped = False

        def is_set(self):
            return self.stopped

        def wait(self, _delay):
            self.stopped = True
            return True

        def set(self):
            self.stopped = True

    def test_disconnection_spools_then_reconnection_flushes(self):
        with tempfile.TemporaryDirectory() as directory:
            spool = Spool(Path(directory) / "spool.sqlite3", 10)
            credentials = Mock()
            credentials.load.return_value = "token"
            runtime = AgentRuntime(
                AgentConfig("https://server.example", "host"),
                credentials,
                spool,
                self.OneCycleStop(),
            )
            runtime.machine_id = "machine-1"
            runtime.client.heartbeat = Mock(return_value={"machine_id": "machine-1"})
            runtime.collector.collect = Mock(
                return_value=[{"metric_name": "cpu", "metric_value": 1}]
            )
            runtime.client.send_metrics = Mock(
                side_effect=AgentAPIError("offline", retryable=True)
            )
            runtime.run()
            self.assertEqual(spool.count(), 1)
            runtime.client.send_metrics = Mock(return_value={"accepted": 1})
            runtime._flush()
            self.assertEqual(spool.count(), 0)

    def test_stop_requests_a_clean_shutdown(self):
        stop = self.OneCycleStop()
        credentials = Mock()
        credentials.load.return_value = "token"
        with tempfile.TemporaryDirectory() as directory:
            runtime = AgentRuntime(
                AgentConfig("https://server.example", "host"),
                credentials,
                Spool(Path(directory) / "spool.sqlite3"),
                stop,
            )
            runtime.stop()
        self.assertTrue(stop.is_set())

    def test_enrollment_persists_token_clears_bootstrap_secret_and_validates_response(self):
        with tempfile.TemporaryDirectory() as directory:
            credentials = Mock()
            credentials.load.return_value = None
            runtime = AgentRuntime(
                AgentConfig("https://server.example", "host"),
                credentials,
                Spool(Path(directory) / "spool.sqlite3"),
                self.OneCycleStop(),
            )
            runtime.client.enroll = Mock(
                return_value={"token": "new-token", "machine_id": "machine-1"}
            )
            with (
                patch.dict(
                    "os.environ", {"INFRASENTINEL_ENROLLMENT_CODE": "one-time-code"}
                ),
                patch("infrasentinel_agent.runtime.machine_identity", return_value="identity"),
                patch("infrasentinel_agent.runtime.ip_address", return_value="10.0.0.1"),
                patch("infrasentinel_agent.runtime.os_information", return_value={}),
            ):
                runtime._enroll()
                self.assertNotIn("INFRASENTINEL_ENROLLMENT_CODE", __import__("os").environ)
            credentials.save.assert_called_once_with("new-token")
            self.assertEqual(runtime.client.token, "new-token")
            self.assertEqual(runtime.machine_id, "machine-1")

            runtime.client.enroll.return_value = {"token": "missing-machine"}
            with patch.dict(
                "os.environ", {"INFRASENTINEL_ENROLLMENT_CODE": "second-code"}
            ):
                with self.assertRaisesRegex(RuntimeError, "incomplète"):
                    runtime._enroll()


if __name__ == "__main__":
    unittest.main()
