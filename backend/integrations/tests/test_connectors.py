import json
import os
import subprocess
from datetime import datetime, timezone as dt_timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from common.testing import TenantAPITestCase
from hyperv_connector.collector import (
    HyperVCollectionError,
    HyperVCollector,
    HyperVConfig,
)
from integrations.models import CollectionRun
from integrations.services import persist_collection
from integrations.tasks import collect_hyperv, collect_hyperv_connector, collect_vmware
from inventory.models import Environment, IntegrationEndpoint, Machine, VirtualAsset
from metrics.models import NormalizedMetric
from vmware_connector.collector import (
    VMwareCollectionError,
    VMwareCollector,
    VMwareConfig,
)


class VMwareCollectorUnitTests(TenantAPITestCase):
    def test_secret_resolution_connection_failure_and_disconnect(self):
        config = VMwareConfig(
            "https://vc.example.test:8443", "svc", "VCENTER_TEST_SECRET", False, 12
        )
        collector = VMwareCollector(config)
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(VMwareCollectionError, "Secret VMware absent"):
                _ = config.password
        service_instance = Mock()
        content = Mock()
        service_instance.RetrieveContent.return_value = content
        with (
            patch.dict(os.environ, {"VCENTER_TEST_SECRET": "never-log-me"}),
            patch("vmware_connector.collector.SmartConnect", return_value=service_instance) as connect,
            patch("vmware_connector.collector.Disconnect") as disconnect,
        ):
            self.assertIs(collector.connect(), content)
            collector.close()
        self.assertEqual(connect.call_args.kwargs["host"], "vc.example.test")
        self.assertEqual(connect.call_args.kwargs["port"], 8443)
        self.assertEqual(connect.call_args.kwargs["connectionPoolTimeout"], 12)
        disconnect.assert_called_once_with(service_instance)

        with (
            patch.dict(os.environ, {"VCENTER_TEST_SECRET": "never-log-me"}),
            patch(
                "vmware_connector.collector.SmartConnect",
                side_effect=TimeoutError("timeout"),
            ),
        ):
            with self.assertRaisesRegex(VMwareCollectionError, "vCenter impossible"):
                VMwareCollector(config).connect()

    def test_host_vm_and_datastore_metrics_are_normalized(self):
        collector = VMwareCollector(VMwareConfig("vc", "svc", "SECRET"))
        timestamp = datetime.now(dt_timezone.utc).isoformat()
        cpu_info = SimpleNamespace(hz=2_000_000_000, numCpuCores=4)
        hardware = SimpleNamespace(
            cpuInfo=cpu_info,
            memorySize=16 * 1024**3,
            systemInfo=SimpleNamespace(vendor="Vendor", model="Model"),
        )
        datastore = SimpleNamespace(
            _moId="ds-1",
            name="DS1",
            summary=SimpleNamespace(
                capacity=1000,
                freeSpace=250,
                accessible=True,
                name="DS1",
                url="ds:///1",
                type="VMFS",
                multipleHostAccess=True,
            ),
        )
        host = SimpleNamespace(
            _moId="host-1",
            name="ESXi 1",
            hardware=hardware,
            summary=SimpleNamespace(
                quickStats=SimpleNamespace(
                    overallCpuUsage=4000,
                    overallMemoryUsage=4096,
                    uptime=1234,
                )
            ),
            datastore=[datastore],
            vm=[object(), object()],
            overallStatus="green",
        )
        vm = SimpleNamespace(
            _moId="vm-1",
            name="VM 1",
            runtime=SimpleNamespace(host=host, powerState="poweredOn"),
            datastore=[datastore],
            summary=SimpleNamespace(
                quickStats=SimpleNamespace(
                    overallCpuUsage=1000, guestMemoryUsage=1024, uptimeSeconds=500
                ),
                config=SimpleNamespace(
                    numCpu=2,
                    memorySizeMB=4096,
                    name="VM 1",
                    guestFullName="Windows Server",
                ),
                storage=SimpleNamespace(committed=750, uncommitted=250),
            ),
        )
        with patch.object(collector, "_perf_counter", side_effect=[10, 20, 30, 40]):
            host_payload = collector._host(Mock(), host, timestamp)
            vm_payload = collector._vm(Mock(), vm, timestamp)
        datastore_payload = collector._datastore(datastore, timestamp)
        self.assertEqual(host_payload["kind"], "HOST")
        self.assertEqual(host_payload["metadata"]["vm_count"], 2)
        self.assertEqual(vm_payload["kind"], "VM")
        self.assertEqual(vm_payload["parent_external_id"], "host-1")
        self.assertEqual(datastore_payload["kind"], "DATASTORE")
        self.assertEqual(datastore_payload["metrics"][0]["metric_value"], 75)
        self.assertEqual(VMwareCollector._bytes_per_second(2), 2048)
        self.assertIsNone(VMwareCollector._bytes_per_second(None))

    def test_collect_discovers_each_resource_type_and_always_closes(self):
        collector = VMwareCollector(VMwareConfig("vc", "svc", "SECRET"))
        host, datastore = object(), object()
        vm = SimpleNamespace(config=object())
        with (
            patch.object(collector, "connect", return_value=Mock()),
            patch.object(collector, "_views", side_effect=[[host], [vm], [datastore]]),
            patch.object(collector, "_host", return_value={"kind": "HOST"}),
            patch.object(collector, "_vm", return_value={"kind": "VM"}),
            patch.object(collector, "_datastore", return_value={"kind": "DATASTORE"}),
            patch.object(collector, "close") as close,
        ):
            payload = collector.collect()
        self.assertEqual(payload["hosts"], [{"kind": "HOST"}])
        self.assertEqual(payload["vms"], [{"kind": "VM"}])
        self.assertEqual(payload["datastores"], [{"kind": "DATASTORE"}])
        close.assert_called_once()


class HyperVCollectorUnitTests(TenantAPITestCase):
    @patch("hyperv_connector.collector.subprocess.run")
    def test_successful_response_and_command_separate_secret(self, run):
        payload = {"collected_at": "now", "hosts": [], "vms": [], "datastores": []}
        captured_environment = {}

        def execute(*_args, **kwargs):
            captured_environment.update(kwargs["env"])
            return Mock(returncode=0, stdout=json.dumps(payload), stderr="")

        run.side_effect = execute
        config = HyperVConfig("hv01", "svc", "HYPERV_SECRET", 10)
        with patch.dict(os.environ, {"HYPERV_SECRET": "never-command"}):
            result = HyperVCollector(config).collect()
        self.assertEqual(result, payload)
        command = run.call_args.args[0]
        self.assertIn("hv01", command)
        self.assertIn("svc", command)
        self.assertNotIn("never-command", command)
        self.assertEqual(captured_environment["INFRASENTINEL_HYPERV_SECRET"], "never-command")

    @patch("hyperv_connector.collector.subprocess.run")
    def test_malformed_permission_timeout_and_missing_secret_are_explicit(self, run):
        run.return_value = Mock(returncode=0, stdout="not-json", stderr="")
        with self.assertRaisesRegex(HyperVCollectionError, "JSON valide"):
            HyperVCollector(HyperVConfig("hv01")).collect()
        run.return_value = Mock(returncode=1, stdout="", stderr="permission denied")
        with self.assertRaisesRegex(HyperVCollectionError, "code 1"):
            HyperVCollector(HyperVConfig("hv01")).collect()
        run.side_effect = subprocess.TimeoutExpired("powershell", 1)
        with self.assertRaisesRegex(
            HyperVCollectionError, "Hyper-V", msg="timeout must be normalized"
        ):
            HyperVCollector(HyperVConfig("hv01", timeout_seconds=1)).collect()
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(HyperVCollectionError, "Secret Hyper-V absent"):
                HyperVCollector(HyperVConfig("hv01", secret_ref="MISSING_SECRET")).collect()


class IntegrationPersistenceAndTasksTests(TenantAPITestCase):
    def setUp(self):
        self.stamp = datetime.now(dt_timezone.utc).isoformat()
        self.vmware_environment = Environment.objects.create(
            customer=self.customer_a, name="VMware", kind=Environment.Kind.VMWARE
        )
        self.hyperv_environment = Environment.objects.create(
            customer=self.customer_a, name="HyperV", kind=Environment.Kind.HYPERV
        )
        self.vmware = IntegrationEndpoint.objects.create(
            customer=self.customer_a,
            environment=self.vmware_environment,
            kind=IntegrationEndpoint.Kind.VMWARE,
            name="vCenter",
            endpoint="https://vc.test",
            username="svc",
            secret_ref="INFRASENTINEL_CONNECTOR_TEST_VMWARE",
        )
        self.hyperv = IntegrationEndpoint.objects.create(
            customer=self.customer_a,
            environment=self.hyperv_environment,
            kind=IntegrationEndpoint.Kind.HYPERV,
            name="HyperV",
            endpoint="hv01",
            username="svc",
            secret_ref="INFRASENTINEL_CONNECTOR_TEST_HYPERV",
        )

    def _payload(self):
        stamp = self.stamp
        return {
            "collected_at": stamp,
            "hosts": [
                {
                    "external_id": "host-1",
                    "kind": "HOST",
                    "name": "Host 1",
                    "state": "green",
                    "metadata": {"health": "green"},
                    "metrics": [
                        {
                            "metric_name": "system.cpu.utilization",
                            "metric_value": 50,
                            "unit": "%",
                            "timestamp": stamp,
                        }
                    ],
                }
            ],
            "vms": [
                {
                    "external_id": "vm-1",
                    "parent_external_id": "host-1",
                    "kind": "VM",
                    "name": "VM 1",
                    "state": "poweredOn",
                    "metrics": [],
                }
            ],
            "datastores": [],
        }

    def test_persistence_associates_assets_metrics_scope_and_is_idempotent(self):
        first = persist_collection(self.vmware, self._payload())
        second = persist_collection(self.vmware, self._payload())
        self.assertEqual(first, {"hosts": 1, "vms": 1, "datastores": 0, "metrics": 1})
        self.assertEqual(second["hosts"], 1)
        self.assertEqual(second["metrics"], 0)
        self.assertEqual(VirtualAsset.objects.filter(connector=self.vmware).count(), 2)
        self.assertEqual(Machine.objects.filter(customer=self.customer_a, source_type="VMWARE").count(), 2)
        metric = NormalizedMetric.objects.get(customer=self.customer_a)
        self.assertEqual(metric.metadata["connector_id"], str(self.vmware.pk))
        self.assertEqual(metric.metadata["resource_kind"], "HOST")

    def test_scheduler_queues_only_enabled_connector_types(self):
        disabled = IntegrationEndpoint.objects.create(
            customer=self.customer_a,
            environment=self.vmware_environment,
            kind=IntegrationEndpoint.Kind.VMWARE,
            name="Disabled",
            endpoint="https://disabled.test",
            secret_ref="INFRASENTINEL_CONNECTOR_DISABLED",
            enabled=False,
        )
        with (
            patch("integrations.tasks.collect_vmware_connector.delay") as vmware_delay,
            patch("integrations.tasks.collect_hyperv_connector.delay") as hyperv_delay,
        ):
            self.assertEqual(collect_vmware(), {"scheduled": 1})
            self.assertEqual(collect_hyperv(), {"scheduled": 1})
        vmware_delay.assert_called_once_with(str(self.vmware.pk))
        hyperv_delay.assert_called_once_with(str(self.hyperv.pk))
        self.assertFalse(vmware_delay.called and str(disabled.pk) in str(vmware_delay.call_args))

    @patch("integrations.tasks.HyperVCollector.collect")
    def test_hyperv_celery_task_persists_success_and_idempotence(self, collect):
        collect.return_value = self._payload()
        with patch.dict(os.environ, {"INFRASENTINEL_CONNECTOR_TEST_HYPERV": "secret"}):
            first = collect_hyperv_connector.apply(
                args=[str(self.hyperv.pk), "hyperv-run"]
            ).get()
            duplicate = collect_hyperv_connector.apply(
                args=[str(self.hyperv.pk), "hyperv-run"]
            ).get()
        self.assertFalse(first["duplicate"])
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(CollectionRun.objects.filter(connector=self.hyperv).count(), 1)


class ConnectorAPITests(TenantAPITestCase):
    def setUp(self):
        self.vmware_environment = Environment.objects.create(
            customer=self.customer_a, name="VMware API", kind=Environment.Kind.VMWARE
        )
        self.authenticate()

    def test_connector_crud_secret_validation_and_collection_dispatch(self):
        secret_ref = f"INFRASENTINEL_CUSTOMER_{self.customer_a.pk.hex.upper()}_VCENTER"
        created = self.client.post(
            "/api/connectors/",
            {
                "environment": str(self.vmware_environment.pk),
                "kind": "VMWARE",
                "name": "API vCenter",
                "endpoint": "https://vc.api.test",
                "username": "svc",
                "secret_ref": secret_ref,
                "timeout_seconds": 30,
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        self.assertNotIn("secret_ref", created.data)
        with patch(
            "common.api.collect_vmware_connector.delay",
            return_value=SimpleNamespace(id="vmware-task"),
        ):
            queued = self.client.post(
                f"/api/connectors/{created.data['id']}/collect/", {}, format="json"
            )
        self.assertEqual(queued.status_code, 202)
        self.assertEqual(queued.data["task_id"], "vmware-task")
        invalid = self.client.post(
            "/api/connectors/",
            {
                "environment": str(self.vmware_environment.pk),
                "kind": "VMWARE",
                "name": "Insecure",
                "endpoint": "http://vc.api.test",
                "secret_ref": "SERVER_PASSWORD",
            },
            format="json",
        )
        self.assertEqual(invalid.status_code, 400)

    def test_overview_and_collection_runs_are_customer_isolated(self):
        foreign_environment = Environment.objects.create(
            customer=self.customer_b, name="Foreign VMware", kind=Environment.Kind.VMWARE
        )
        foreign = IntegrationEndpoint.objects.create(
            customer=self.customer_b,
            environment=foreign_environment,
            kind="VMWARE",
            name="Foreign vCenter",
            endpoint="https://foreign.test",
            secret_ref="INFRASENTINEL_CONNECTOR_FOREIGN",
        )
        CollectionRun.objects.create(connector=foreign, status=CollectionRun.Status.SUCCESS)
        response = self.client.get("/api/vmware/overview/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["connectors"], [])
        self.assertEqual(self.client.get("/api/collection-runs/").data["results"], [])
