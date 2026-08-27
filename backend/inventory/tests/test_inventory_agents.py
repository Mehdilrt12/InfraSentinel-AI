from datetime import timedelta

from django.utils import timezone

from common.testing import TenantAPITestCase
from inventory.models import Agent, EnrollmentCode, Environment, Machine
from inventory.services import _hash, create_enrollment_code
from monitoring.alert_service import create_or_update_alert
from monitoring.models import Alert, AuditLog


class EnvironmentAndMachineAPITests(TenantAPITestCase):
    def setUp(self):
        self.authenticate()

    def test_environment_create_update_delete_and_audit(self):
        created = self.client.post(
            "/api/environments/",
            {"name": "Disposable VMware", "kind": Environment.Kind.VMWARE},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        environment_id = created.data["id"]
        updated = self.client.patch(
            f"/api/environments/{environment_id}/",
            {"name": "Renamed VMware"},
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(
            self.client.delete(f"/api/environments/{environment_id}/").status_code,
            204,
        )
        self.assertEqual(
            AuditLog.objects.filter(
                customer=self.customer_a,
                target_id=str(environment_id),
                action=AuditLog.Action.CONFIG_CHANGED,
            ).count(),
            3,
        )

    def test_machine_create_update_status_and_delete(self):
        created = self.client.post(
            "/api/machines/",
            {
                "environment": str(self.environment_a.pk),
                "source_type": Environment.Kind.WINDOWS,
                "external_id": "api-machine",
                "hostname": "api-host",
                "ip_address": "10.0.0.10",
                "status": Machine.Status.UNKNOWN,
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        machine_id = created.data["id"]
        updated = self.client.patch(
            f"/api/machines/{machine_id}/",
            {"hostname": "api-host-renamed", "status": Machine.Status.OFFLINE},
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["status"], Machine.Status.OFFLINE)
        self.assertIsNone(updated.data["last_seen"])
        self.assertEqual(self.client.delete(f"/api/machines/{machine_id}/").status_code, 204)

    def test_windows_vmware_and_hyperv_machine_types_are_supported(self):
        environments = {
            Environment.Kind.WINDOWS: self.environment_a,
            Environment.Kind.VMWARE: Environment.objects.create(
                customer=self.customer_a, name="vSphere", kind=Environment.Kind.VMWARE
            ),
            Environment.Kind.HYPERV: Environment.objects.create(
                customer=self.customer_a, name="Hyper-V", kind=Environment.Kind.HYPERV
            ),
        }
        for index, (kind, environment) in enumerate(environments.items()):
            response = self.client.post(
                "/api/machines/",
                {
                    "environment": str(environment.pk),
                    "source_type": kind,
                    "external_id": f"{kind.lower()}-{index}",
                    "hostname": f"{kind.lower()}-host",
                },
                format="json",
            )
            with self.subTest(kind=kind):
                self.assertEqual(response.status_code, 201)
                self.assertEqual(response.data["source_type"], kind)

    def test_invalid_source_environment_and_cross_tenant_relationships_are_rejected(self):
        mismatch = self.client.post(
            "/api/machines/",
            {
                "environment": str(self.environment_a.pk),
                "source_type": Environment.Kind.VMWARE,
                "external_id": "mismatch",
                "hostname": "mismatch",
            },
            format="json",
        )
        self.assertEqual(mismatch.status_code, 400)
        foreign = self.client.post(
            "/api/machines/",
            {
                "environment": str(self.environment_b.pk),
                "source_type": Environment.Kind.WINDOWS,
                "external_id": "foreign",
                "hostname": "foreign",
            },
            format="json",
        )
        self.assertEqual(foreign.status_code, 400)
        self.assertFalse(Machine.objects.filter(external_id="foreign").exists())

    def test_machine_list_and_detail_are_customer_isolated(self):
        own = self.create_machine(external_id="own", hostname="own")
        foreign = self.create_machine(
            customer=self.customer_b,
            environment=self.environment_b,
            external_id="foreign",
            hostname="foreign",
        )
        listing = self.client.get("/api/machines/")
        ids = {row["id"] for row in listing.data["results"]}
        self.assertIn(str(own.pk), ids)
        self.assertNotIn(str(foreign.pk), ids)
        self.assertEqual(self.client.get(f"/api/machines/{foreign.pk}/").status_code, 404)


class AgentLifecycleAPITests(TenantAPITestCase):
    def _enroll(self, *, external_id="agent-host", hostname="agent-host"):
        raw_code = create_enrollment_code(self.customer_a, self.environment_a)
        self.client.force_authenticate(user=None)
        response = self.client.post(
            "/api/agent/enroll/",
            {
                "enrollment_code": raw_code,
                "external_id": external_id,
                "hostname": hostname,
                "ip_address": "10.2.3.4",
                "os_information": {"platform": "Windows"},
                "version": "2.0.0",
            },
            format="json",
        )
        return response

    def test_enrollment_token_heartbeat_and_response_secrecy(self):
        enrolled = self._enroll()
        self.assertEqual(enrolled.status_code, 201)
        token = enrolled.data["token"]
        agent = Agent.objects.get(pk=enrolled.data["agent_id"])
        self.assertNotEqual(agent.token_hash, token)
        self.assertEqual(agent.token_hash, _hash(token))

        heartbeat = self.client.post(
            "/api/agent/heartbeat/",
            {"version": "2.1.0"},
            format="json",
            HTTP_X_AGENT_TOKEN=token,
        )
        self.assertEqual(heartbeat.status_code, 200)
        self.assertNotIn("token", heartbeat.data)
        self.authenticate()
        listed = self.client.get("/api/agents/")
        serialized = listed.data["results"][0]
        self.assertNotIn("token", serialized)
        self.assertNotIn("token_hash", serialized)

    def test_invalid_expired_and_used_enrollment_codes_are_rejected(self):
        expired = "expired-code"
        EnrollmentCode.objects.create(
            customer=self.customer_a,
            environment=self.environment_a,
            code_hash=_hash(expired),
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        self.client.force_authenticate(user=None)
        payload = {
            "enrollment_code": expired,
            "external_id": "expired-agent",
            "hostname": "expired-agent",
        }
        self.assertEqual(
            self.client.post("/api/agent/enroll/", payload, format="json").status_code,
            400,
        )
        valid = self._enroll(external_id="single-use")
        self.assertEqual(valid.status_code, 201)
        replay = self.client.post(
            "/api/agent/enroll/",
            {
                "enrollment_code": "not-the-original-secret",
                "external_id": "replay",
                "hostname": "replay",
            },
            format="json",
        )
        self.assertEqual(replay.status_code, 400)

    def test_enrollment_code_constraints_and_environment_kind(self):
        foreign_vmware = Environment.objects.create(
            customer=self.customer_a, name="Not Windows", kind=Environment.Kind.VMWARE
        )
        with self.assertRaises(ValueError):
            create_enrollment_code(self.customer_b, self.environment_a)
        with self.assertRaises(ValueError):
            create_enrollment_code(self.customer_a, foreign_vmware)
        for invalid_ttl in (0, 1441):
            with self.subTest(ttl=invalid_ttl), self.assertRaises(ValueError):
                create_enrollment_code(
                    self.customer_a, self.environment_a, ttl_minutes=invalid_ttl
                )

    def test_invalid_revoked_token_and_malformed_payload_are_rejected(self):
        enrolled = self._enroll()
        token = enrolled.data["token"]
        self.assertEqual(
            self.client.post(
                "/api/agent/heartbeat/", {}, format="json", HTTP_X_AGENT_TOKEN="bad"
            ).status_code,
            401,
        )
        malformed = self.client.post(
            "/api/agent/metrics/",
            {"machine_id": enrolled.data["machine_id"], "metrics": None},
            format="json",
            HTTP_X_AGENT_TOKEN=token,
        )
        self.assertEqual(malformed.status_code, 400)

        self.authenticate()
        self.assertEqual(
            self.client.patch(
                f"/api/agents/{enrolled.data['agent_id']}/",
                {"enabled": False},
                format="json",
            ).status_code,
            200,
        )
        self.client.force_authenticate(user=None)
        revoked = self.client.post(
            "/api/agent/heartbeat/", {}, format="json", HTTP_X_AGENT_TOKEN=token
        )
        self.assertEqual(revoked.status_code, 401)

    def test_agent_cannot_publish_for_another_machine(self):
        enrolled = self._enroll()
        foreign = self.create_machine(
            customer=self.customer_b,
            environment=self.environment_b,
            external_id="other-tenant-machine",
            hostname="other-tenant-machine",
        )
        response = self.client.post(
            "/api/agent/metrics/",
            {
                "machine_id": str(foreign.pk),
                "metrics": [{"metric_name": "cpu", "metric_value": 10}],
            },
            format="json",
            HTTP_X_AGENT_TOKEN=enrolled.data["token"],
        )
        self.assertEqual(response.status_code, 403)

    def test_reconnection_heartbeat_marks_online_and_resolves_offline_alert(self):
        enrolled = self._enroll()
        machine = Machine.objects.get(pk=enrolled.data["machine_id"])
        machine.status = Machine.Status.OFFLINE
        machine.save(update_fields=["status"])
        alert, _ = create_or_update_alert(
            machine=machine,
            alert_type="MACHINE_OFFLINE",
            severity="CRITICAL",
            source="WINDOWS",
            message="offline",
            source_key="offline-rule",
        )
        response = self.client.post(
            "/api/agent/heartbeat/",
            {"version": "2.2.0"},
            format="json",
            HTTP_X_AGENT_TOKEN=enrolled.data["token"],
        )
        self.assertEqual(response.status_code, 200)
        machine.refresh_from_db()
        alert.refresh_from_db()
        self.assertEqual(machine.status, Machine.Status.ONLINE)
        self.assertEqual(alert.status, Alert.Status.RESOLVED)
