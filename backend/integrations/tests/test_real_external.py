import os
from unittest import skipUnless

from django.test import SimpleTestCase

from hyperv_connector.collector import HyperVCollector, HyperVConfig
from vmware_connector.collector import VMwareCollector, VMwareConfig


class RealExternalIntegrationTests(SimpleTestCase):
    @skipUnless(
        os.getenv("INFRASENTINEL_RUN_REAL_VMWARE") == "1",
        "NOT TESTED — REAL VMWARE ENVIRONMENT REQUIRED",
    )
    def test_real_vmware_collection(self):
        payload = VMwareCollector(
            VMwareConfig(
                os.environ["INFRASENTINEL_REAL_VMWARE_URL"],
                os.environ["INFRASENTINEL_REAL_VMWARE_USER"],
                "INFRASENTINEL_REAL_VMWARE_PASSWORD",
            )
        ).collect()
        self.assertIn("hosts", payload)
        self.assertIn("vms", payload)
        self.assertIn("datastores", payload)

    @skipUnless(
        os.getenv("INFRASENTINEL_RUN_REAL_HYPERV") == "1",
        "NOT TESTED — REAL HYPER-V ENVIRONMENT REQUIRED",
    )
    def test_real_hyperv_collection(self):
        payload = HyperVCollector(
            HyperVConfig(
                os.environ["INFRASENTINEL_REAL_HYPERV_HOST"],
                os.getenv("INFRASENTINEL_REAL_HYPERV_USER", ""),
                "INFRASENTINEL_REAL_HYPERV_PASSWORD",
            )
        ).collect()
        self.assertIn("hosts", payload)
        self.assertIn("vms", payload)
