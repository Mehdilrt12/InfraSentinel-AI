import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import requests
from infrasentinel_agent.client import AgentAPIError, AgentClient
from infrasentinel_agent.collector import WindowsCollector
from infrasentinel_agent.config import AgentConfig
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

    @patch("requests.Session.post", side_effect=requests.ConnectionError("offline"))
    def test_unavailable_server_is_retryable(self, _post):
        with self.assertRaises(AgentAPIError) as caught:
            self.client.heartbeat("2.0.0")
        self.assertTrue(caught.exception.retryable)


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


if __name__ == "__main__":
    unittest.main()
