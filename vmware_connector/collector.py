import os
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse
from pyVim.connect import Disconnect, SmartConnect
from pyVmomi import vim


class VMwareCollectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class VMwareConfig:
    endpoint: str
    username: str
    secret_ref: str
    verify_tls: bool = True
    timeout_seconds: int = 30

    @property
    def password(self):
        value = os.getenv(self.secret_ref)
        if not value:
            raise VMwareCollectionError(
                f"Secret VMware absent: variable {self.secret_ref}"
            )
        return value


class VMwareCollector:
    def __init__(self, config):
        self.config = config
        self.si = None

    def connect(self):
        parsed = urlparse(
            self.config.endpoint
            if "://" in self.config.endpoint
            else f"https://{self.config.endpoint}"
        )
        context = ssl.create_default_context()
        if not self.config.verify_tls:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        try:
            self.si = SmartConnect(
                host=parsed.hostname,
                port=parsed.port or 443,
                user=self.config.username,
                pwd=self.config.password,
                sslContext=context,
                connectionPoolTimeout=self.config.timeout_seconds,
            )
            return self.si.RetrieveContent()
        except Exception as exc:
            raise VMwareCollectionError(
                f"Connexion/authentification vCenter impossible: {exc}"
            ) from exc

    def close(self):
        if self.si:
            Disconnect(self.si)

    def _views(self, content, object_type):
        view = content.viewManager.CreateContainerView(
            content.rootFolder, [object_type], True
        )
        try:
            return list(view.view)
        finally:
            view.Destroy()

    def _perf_counter(self, content, entity, full_name):
        manager = content.perfManager
        counters = {
            f"{counter.groupInfo.key}.{counter.nameInfo.key}.{counter.rollupType}": counter.key
            for counter in manager.perfCounter
        }
        key = counters.get(full_name)
        if key is None:
            return None
        query = vim.PerformanceManager.QuerySpec(
            entity=entity,
            metricId=[vim.PerformanceManager.MetricId(counterId=key, instance="*")],
            intervalId=20,
            maxSample=1,
        )
        result = manager.QueryPerf(querySpec=[query])
        values = [
            sample
            for item in result
            for series in item.value
            for sample in series.value
        ]
        return float(sum(values)) if values else None

    def _host(self, content, host, timestamp):
        hw = host.hardware
        quick = host.summary.quickStats
        capacity_mhz = (
            (hw.cpuInfo.hz / 1_000_000) * hw.cpuInfo.numCpuCores
            if hw and hw.cpuInfo
            else 0
        )
        cpu = (
            (quick.overallCpuUsage / capacity_mhz * 100)
            if capacity_mhz and quick.overallCpuUsage is not None
            else None
        )
        memory_total = hw.memorySize if hw else 0
        memory_used = (quick.overallMemoryUsage or 0) * 1024 * 1024
        capacity = sum(
            ds.summary.capacity or 0 for ds in host.datastore if ds.summary.accessible
        )
        free = sum(
            ds.summary.freeSpace or 0 for ds in host.datastore if ds.summary.accessible
        )
        metrics = [
            self._metric("system.cpu.utilization", cpu, "%", timestamp),
            self._metric(
                "system.memory.utilization",
                memory_used / memory_total * 100 if memory_total else None,
                "%",
                timestamp,
            ),
            self._metric(
                "system.disk.utilization",
                (capacity - free) / capacity * 100 if capacity else None,
                "%",
                timestamp,
            ),
            self._metric("system.disk.free", free, "bytes", timestamp),
            self._metric(
                "system.network.in",
                self._perf_counter(content, host, "net.received.average"),
                "KiB/s",
                timestamp,
            ),
            self._metric(
                "system.network.out",
                self._perf_counter(content, host, "net.transmitted.average"),
                "KiB/s",
                timestamp,
            ),
            self._metric("system.uptime", quick.uptime, "seconds", timestamp),
        ]
        return {
            "external_id": host._moId,
            "kind": "HOST",
            "name": host.name,
            "state": str(host.overallStatus),
            "parent_external_id": "",
            "metadata": {
                "vendor": getattr(hw.systemInfo, "vendor", ""),
                "model": getattr(hw.systemInfo, "model", ""),
                "vm_count": len(host.vm),
            },
            "metrics": metrics,
        }

    def _vm(self, content, vm, timestamp):
        summary = vm.summary
        quick = summary.quickStats
        config = summary.config
        host = vm.runtime.host
        cpu_capacity = (getattr(config, "numCpu", 0) or 0) * (
            getattr(host.hardware.cpuInfo, "hz", 0) / 1_000_000
        )
        committed = getattr(summary.storage, "committed", 0) or 0
        uncommitted = getattr(summary.storage, "uncommitted", 0) or 0
        disk_total = committed + uncommitted
        metrics = [
            self._metric(
                "system.cpu.utilization",
                (quick.overallCpuUsage or 0) / cpu_capacity * 100
                if cpu_capacity
                else None,
                "%",
                timestamp,
            ),
            self._metric(
                "system.memory.utilization",
                (quick.guestMemoryUsage or 0) / config.memorySizeMB * 100
                if config.memorySizeMB
                else None,
                "%",
                timestamp,
            ),
            self._metric(
                "system.disk.utilization",
                committed / disk_total * 100 if disk_total else None,
                "%",
                timestamp,
            ),
            self._metric(
                "system.network.in",
                self._perf_counter(content, vm, "net.received.average"),
                "KiB/s",
                timestamp,
            ),
            self._metric(
                "system.network.out",
                self._perf_counter(content, vm, "net.transmitted.average"),
                "KiB/s",
                timestamp,
            ),
            self._metric("system.uptime", quick.uptimeSeconds, "seconds", timestamp),
            self._metric(
                "virtual.machine.state",
                1 if str(vm.runtime.powerState) == "poweredOn" else 0,
                "state",
                timestamp,
                status=str(vm.runtime.powerState),
            ),
        ]
        return {
            "external_id": vm._moId,
            "kind": "VM",
            "name": config.name or vm.name,
            "state": str(vm.runtime.powerState),
            "parent_external_id": host._moId if host else "",
            "metadata": {
                "guest": config.guestFullName or "",
                "datastores": [ds.name for ds in vm.datastore],
            },
            "metrics": metrics,
        }

    @staticmethod
    def _metric(name, value, unit, timestamp, status=""):
        return {
            "metric_name": name,
            "metric_value": value,
            "unit": unit,
            "timestamp": timestamp,
            "status": status,
            "metadata": {},
        }

    def collect(self):
        timestamp = datetime.now(timezone.utc).isoformat()
        content = self.connect()
        try:
            hosts = [
                self._host(content, host, timestamp)
                for host in self._views(content, vim.HostSystem)
            ]
            vms = [
                self._vm(content, vm, timestamp)
                for vm in self._views(content, vim.VirtualMachine)
                if vm.config is not None
            ]
            return {"collected_at": timestamp, "hosts": hosts, "vms": vms}
        finally:
            self.close()
