import hashlib
import platform
import shutil
import socket
import subprocess
import time
import uuid
from datetime import datetime, timezone
import psutil


def machine_identity():
    value = None
    if platform.system() == "Windows":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography"
            ) as key:
                value = winreg.QueryValueEx(key, "MachineGuid")[0]
        except OSError:
            pass
    value = value or f"{socket.gethostname()}:{uuid.getnode()}"
    return hashlib.sha256(value.encode()).hexdigest()


def ip_address():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("1.1.1.1", 53))
            return sock.getsockname()[0]
    except OSError:
        return None


def os_information():
    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "architecture": platform.machine(),
        "hostname": socket.gethostname(),
    }


class WindowsCollector:
    def __init__(self, config):
        self.config = config
        self._last_time = None
        self._last_net = None
        self._last_disk = None

    def _metric(self, name, value, unit, timestamp, metadata=None, status=""):
        return {
            "metric_name": name,
            "metric_value": value,
            "unit": unit,
            "timestamp": timestamp,
            "metadata": metadata or {},
            "status": status,
            "idempotency_key": str(uuid.uuid4()),
        }

    def _latency(self):
        target = self.config.latency_host or socket.gethostname()
        started = time.perf_counter()
        try:
            with socket.create_connection(
                (target, self.config.latency_port),
                timeout=min(5, self.config.request_timeout_seconds),
            ):
                return (time.perf_counter() - started) * 1000, "ok"
        except OSError:
            return None, "unreachable"

    def _gpu(self, timestamp):
        executable = shutil.which("nvidia-smi")
        if not executable:
            return []
        try:
            result = subprocess.run(
                [
                    executable,
                    "--query-gpu=index,name,utilization.gpu,memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        metrics = []
        for line in result.stdout.splitlines():
            index, name, usage, used, total = [
                part.strip() for part in line.split(",", 4)
            ]
            metrics.append(
                self._metric(
                    "system.gpu.utilization",
                    float(usage),
                    "%",
                    timestamp,
                    {
                        "gpu_index": index,
                        "gpu_name": name,
                        "memory_used_mib": float(used),
                        "memory_total_mib": float(total),
                    },
                )
            )
        return metrics

    def _services(self, timestamp):
        metrics = []
        if platform.system() != "Windows":
            return metrics
        for name in self.config.critical_services:
            try:
                state = psutil.win_service_get(name).status()
                value = 1 if state == "running" else 0
            except (psutil.NoSuchProcess, OSError):
                state, value = "not_found", 0
            metrics.append(
                self._metric(
                    "windows.service.state",
                    value,
                    "state",
                    timestamp,
                    {"service_name": name},
                    state,
                )
            )
        return metrics

    def collect(self):
        now_monotonic = time.monotonic()
        timestamp = datetime.now(timezone.utc).isoformat()
        elapsed = (
            max(0.001, now_monotonic - self._last_time) if self._last_time else None
        )
        memory = psutil.virtual_memory()
        metrics = [
            self._metric(
                "system.cpu.utilization",
                psutil.cpu_percent(interval=0.2),
                "%",
                timestamp,
            ),
            self._metric(
                "system.memory.utilization",
                memory.percent,
                "%",
                timestamp,
                {"available_bytes": memory.available, "total_bytes": memory.total},
            ),
            self._metric(
                "system.uptime", time.time() - psutil.boot_time(), "seconds", timestamp
            ),
            self._metric(
                "system.process.count", len(psutil.pids()), "count", timestamp
            ),
        ]
        for partition in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(partition.mountpoint)
            except (PermissionError, OSError):
                continue
            metadata = {
                "device": partition.device,
                "mountpoint": partition.mountpoint,
                "filesystem": partition.fstype,
            }
            metrics.extend(
                [
                    self._metric(
                        "system.disk.utilization",
                        usage.percent,
                        "%",
                        timestamp,
                        metadata,
                    ),
                    self._metric(
                        "system.disk.free", usage.free, "bytes", timestamp, metadata
                    ),
                ]
            )
        disk = psutil.disk_io_counters()
        net = psutil.net_io_counters()
        if elapsed and disk and self._last_disk:
            metrics.extend(
                [
                    self._metric(
                        "system.disk.io.read",
                        max(0, disk.read_bytes - self._last_disk.read_bytes) / elapsed,
                        "bytes/s",
                        timestamp,
                    ),
                    self._metric(
                        "system.disk.io.write",
                        max(0, disk.write_bytes - self._last_disk.write_bytes)
                        / elapsed,
                        "bytes/s",
                        timestamp,
                    ),
                ]
            )
        if elapsed and net and self._last_net:
            metrics.extend(
                [
                    self._metric(
                        "system.network.in",
                        max(0, net.bytes_recv - self._last_net.bytes_recv) / elapsed,
                        "bytes/s",
                        timestamp,
                    ),
                    self._metric(
                        "system.network.out",
                        max(0, net.bytes_sent - self._last_net.bytes_sent) / elapsed,
                        "bytes/s",
                        timestamp,
                    ),
                ]
            )
        latency, latency_status = self._latency()
        metrics.append(
            self._metric(
                "system.network.latency",
                latency,
                "ms",
                timestamp,
                {"target": self.config.latency_host, "port": self.config.latency_port},
                latency_status,
            )
        )
        metrics.extend(self._gpu(timestamp))
        metrics.extend(self._services(timestamp))
        self._last_time, self._last_net, self._last_disk = now_monotonic, net, disk
        return metrics
