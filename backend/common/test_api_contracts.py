from django.test import SimpleTestCase
from django.utils import timezone

from accounts.models import User
from common.testing import TEST_PASSWORD, TenantAPITestCase
from inventory.models import Environment, IntegrationEndpoint, Machine, VirtualAsset
from metrics.models import MetricAggregate
from monitoring.models import Alert, Anomaly, AuditLog


class PaginationOrderingTests(SimpleTestCase):
    def test_every_router_queryset_has_deterministic_ordering(self):
        from common.urls import router

        unordered = [
            prefix
            for prefix, viewset, _basename in router.registry
            if getattr(viewset, "queryset", None) is not None
            and not viewset.queryset.ordered
        ]
        self.assertEqual(unordered, [])


class CrossApplicationAPIContractTests(TenantAPITestCase):
    def test_health_is_public_but_dashboard_is_authenticated(self):
        responses = [self.client.get("/api/health/") for _ in range(70)]
        health = responses[-1]
        self.assertTrue(all(response.status_code == 200 for response in responses))
        self.assertEqual(health.data["status"], "ok")
        self.assertEqual(health.data["version"], "2.0.0")
        self.assertEqual(health.data["components"], {"database": "ok", "redis": "ok"})
        self.assertEqual(self.client.get("/api/dashboard/").status_code, 401)

    def test_dashboard_counts_only_current_customer_resources(self):
        online = self.create_machine(
            external_id="online", hostname="online", status=Machine.Status.ONLINE
        )
        offline = self.create_machine(
            external_id="offline", hostname="offline", status=Machine.Status.OFFLINE
        )
        foreign = self.create_machine(
            customer=self.customer_b,
            environment=self.environment_b,
            external_id="foreign-dashboard",
            hostname="foreign-dashboard",
            status=Machine.Status.OFFLINE,
        )
        Alert.objects.create(
            customer=self.customer_a,
            machine=offline,
            type="MACHINE_OFFLINE",
            severity="CRITICAL",
            source="WINDOWS",
            message="offline",
            dedup_key="dashboard-alert",
        )
        Anomaly.objects.create(
            customer=self.customer_a,
            machine=online,
            score=0.9,
            threshold=0.8,
            model_version="dashboard-model",
        )
        Alert.objects.create(
            customer=self.customer_b,
            machine=foreign,
            type="FOREIGN",
            severity="CRITICAL",
            source="WINDOWS",
            message="foreign",
            dedup_key="foreign-dashboard-alert",
        )
        self.authenticate()
        data = self.client.get("/api/dashboard/").data
        self.assertEqual(data["total_assets"], 2)
        self.assertEqual(data["online"], 1)
        self.assertEqual(data["offline"], 1)
        self.assertEqual(data["critical"], 1)
        self.assertEqual(data["anomalies"], 1)
        self.assertEqual(data["active_alerts"], 1)

    def test_assets_filters_and_metric_aggregates_are_read_only_and_isolated(self):
        vmware_environment = Environment.objects.create(
            customer=self.customer_a, name="Cross VMware", kind="VMWARE"
        )
        connector = IntegrationEndpoint.objects.create(
            customer=self.customer_a,
            environment=vmware_environment,
            kind="VMWARE",
            name="Cross vCenter",
            endpoint="https://vc.cross.test",
            secret_ref="INFRASENTINEL_CONNECTOR_CROSS",
        )
        machine = self.create_machine(
            environment=vmware_environment,
            source_type="VMWARE",
            external_id="cross-host",
            hostname="cross-host",
        )
        asset = VirtualAsset.objects.create(
            customer=self.customer_a,
            connector=connector,
            machine=machine,
            external_id="host-1",
            kind="HOST",
            name="Host 1",
        )
        aggregate = MetricAggregate.objects.create(
            machine=machine,
            metric_name="system.cpu.utilization",
            bucket_start=timezone.now(),
            minimum=10,
            maximum=30,
            average=20,
            sample_count=3,
        )
        self.authenticate()
        assets = self.client.get("/api/assets/?kind=HOST&source=VMWARE")
        self.assertEqual([row["id"] for row in assets.data["results"]], [str(asset.pk)])
        aggregates = self.client.get("/api/metric-aggregates/")
        self.assertEqual([row["id"] for row in aggregates.data["results"]], [aggregate.pk])
        self.assertEqual(self.client.post("/api/assets/", {}, format="json").status_code, 405)
        self.assertEqual(
            self.client.post("/api/metric-aggregates/", {}, format="json").status_code,
            405,
        )

    def test_audit_api_is_read_only_and_customer_isolated(self):
        own = AuditLog.objects.create(
            customer=self.customer_a,
            actor=self.admin_a,
            action="OWN",
            target_type="test",
            target_id="1",
        )
        foreign = AuditLog.objects.create(
            customer=self.customer_b,
            actor=self.admin_b,
            action="FOREIGN",
            target_type="test",
            target_id="2",
        )
        self.authenticate()
        ids = {row["id"] for row in self.client.get("/api/audit/").data["results"]}
        self.assertIn(own.pk, ids)
        self.assertNotIn(foreign.pk, ids)
        self.assertEqual(self.client.post("/api/audit/", {}, format="json").status_code, 405)

    def test_machine_trend_parameters_are_validated_over_http(self):
        machine = self.create_machine()
        self.authenticate()
        for hours in ("bad", 0, 721):
            with self.subTest(hours=hours):
                self.assertEqual(
                    self.client.get(f"/api/machines/{machine.pk}/trends/?hours={hours}").status_code,
                    400,
                )
        self.assertEqual(
            self.client.get(f"/api/machines/{machine.pk}/trends/?hours=24").status_code,
            200,
        )

    def test_enrollment_code_action_validates_ttl_and_environment_kind(self):
        self.authenticate()
        path = f"/api/environments/{self.environment_a.pk}/enrollment_code/"
        for ttl in ("bad", 0, 1441):
            with self.subTest(ttl=ttl):
                self.assertEqual(
                    self.client.post(path, {"ttl_minutes": ttl}, format="json").status_code,
                    400,
                )
        valid = self.client.post(path, {"ttl_minutes": 5}, format="json")
        self.assertEqual(valid.status_code, 201)
        self.assertIn("enrollment_code", valid.data)
        vmware = Environment.objects.create(
            customer=self.customer_a, name="Enrollment VMware", kind="VMWARE"
        )
        self.assertEqual(
            self.client.post(
                f"/api/environments/{vmware.pk}/enrollment_code/", {}, format="json"
            ).status_code,
            400,
        )

    def test_superuser_customer_query_filter_is_explicit(self):
        self.create_machine(external_id="alpha-super", hostname="alpha-super")
        beta = self.create_machine(
            customer=self.customer_b,
            environment=self.environment_b,
            external_id="beta-super",
            hostname="beta-super",
        )
        superuser = User.objects.create_superuser(
            username="super-query",
            email="super-query@test.invalid",
            password=TEST_PASSWORD,
        )
        self.authenticate(superuser)
        response = self.client.get(f"/api/machines/?customer={self.customer_b.pk}")
        self.assertEqual([row["id"] for row in response.data["results"]], [str(beta.pk)])
