import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import DatabaseError, transaction
from django.test import override_settings
from django.utils import timezone

from accounts.models import User
from common.testing import TEST_PASSWORD, TenantAPITestCase
from inventory.models import Agent, Environment
from inventory.services import create_enrollment_code
from ml_engine.pipeline import FEATURES, train_customer_model
from monitoring.alert_service import create_or_update_alert
from monitoring.audit import record_audit
from monitoring.models import Alert, AuditLog


@override_settings(PUBLIC_REGISTRATION_ENABLED=True)
class AuditEventTests(TenantAPITestCase):
    def test_public_registration_audits_new_admin_without_password(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "organization": "Audited Registration",
                "email": "registered-audit@example.test",
                "password": "RegistrationHorse12!",
            },
            format="json",
            REMOTE_ADDR="192.0.2.25",
        )
        self.assertEqual(response.status_code, 201)
        event = AuditLog.objects.get(
            action=AuditLog.Action.USER_CREATED,
            target_id=str(response.data["user_id"]),
        )
        self.assertEqual(event.actor_id, response.data["user_id"])
        self.assertEqual(event.metadata["source"], "public_registration")
        self.assertNotIn("password", str(event.metadata).lower())

    def test_login_logout_capture_actor_customer_and_trusted_ip(self):
        login = self.client.post(
            "/api/auth/token/",
            {"email": self.admin_a.email, "password": TEST_PASSWORD},
            format="json",
            REMOTE_ADDR="203.0.113.10",
        )
        self.assertEqual(login.status_code, 200)
        logged_in = AuditLog.objects.get(action=AuditLog.Action.USER_LOGIN)
        self.assertEqual(logged_in.actor, self.admin_a)
        self.assertEqual(logged_in.customer, self.customer_a)
        self.assertEqual(str(logged_in.ip_address), "203.0.113.10")
        self.assertEqual(logged_in.metadata["authentication"], "jwt")

        logout = self.client.post(
            "/api/auth/logout/",
            {"refresh": login.data["refresh"]},
            format="json",
            REMOTE_ADDR="203.0.113.11",
        )
        self.assertEqual(logout.status_code, 200)
        logged_out = AuditLog.objects.get(action=AuditLog.Action.USER_LOGOUT)
        self.assertEqual(logged_out.actor_email, self.admin_a.email)
        self.assertEqual(str(logged_out.ip_address), "203.0.113.11")

    def test_user_machine_agent_and_alert_lifecycle_actions(self):
        self.authenticate()
        user_response = self.client.post(
            "/api/users/",
            {
                "email": "audited@alpha.test",
                "username": "audited-user",
                "password": "AuditedHorse12!",
                "role": User.Role.VIEWER,
            },
            format="json",
            REMOTE_ADDR="198.51.100.8",
        )
        self.assertEqual(user_response.status_code, 201)
        user_id = user_response.data["id"]
        self.assertEqual(
            self.client.patch(
                f"/api/users/{user_id}/",
                {"role": User.Role.TECHNICIAN},
                format="json",
            ).status_code,
            200,
        )

        machine_response = self.client.post(
            "/api/machines/",
            {
                "environment": str(self.environment_a.pk),
                "source_type": Environment.Kind.WINDOWS,
                "external_id": "audit-machine",
                "hostname": "audit-host",
            },
            format="json",
        )
        self.assertEqual(machine_response.status_code, 201)
        machine_id = machine_response.data["id"]
        self.assertEqual(
            self.client.patch(
                f"/api/machines/{machine_id}/",
                {"hostname": "audit-host-updated"},
                format="json",
            ).status_code,
            200,
        )

        code = create_enrollment_code(self.customer_a, self.environment_a)
        enrolled = self.client.post(
            "/api/agent/enroll/",
            {
                "enrollment_code": code,
                "external_id": "audit-agent-machine",
                "hostname": "audit-agent",
                "version": "2.0.0",
            },
            format="json",
            REMOTE_ADDR="192.0.2.40",
        )
        self.assertEqual(enrolled.status_code, 201)
        agent = Agent.objects.get(pk=enrolled.data["agent_id"])
        self.assertEqual(
            self.client.patch(
                f"/api/agents/{agent.pk}/", {"enabled": False}, format="json"
            ).status_code,
            200,
        )

        machine = self.create_machine(external_id="alert-audit", hostname="alert-audit")
        alert, created = create_or_update_alert(
            machine=machine,
            alert_type="AUDIT_TEST",
            severity="HIGH",
            source="WINDOWS",
            message="Audit lifecycle",
        )
        self.assertTrue(created)
        self.assertEqual(
            self.client.patch(
                f"/api/alerts/{alert.pk}/",
                {"status": Alert.Status.ACKNOWLEDGED},
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/alerts/{alert.pk}/",
                {"status": Alert.Status.RESOLVED},
                format="json",
            ).status_code,
            200,
        )

        expected = {
            AuditLog.Action.USER_CREATED,
            AuditLog.Action.USER_UPDATED,
            AuditLog.Action.MACHINE_CREATED,
            AuditLog.Action.MACHINE_UPDATED,
            AuditLog.Action.AGENT_ENROLLED,
            AuditLog.Action.AGENT_REVOKED,
            AuditLog.Action.ALERT_CREATED,
            AuditLog.Action.ALERT_ACKNOWLEDGED,
            AuditLog.Action.ALERT_RESOLVED,
        }
        self.assertTrue(
            expected.issubset(
                set(AuditLog.objects.filter(customer=self.customer_a).values_list("action", flat=True))
            )
        )
        enrolled_log = AuditLog.objects.get(
            action=AuditLog.Action.AGENT_ENROLLED, target_id=str(agent.pk)
        )
        self.assertIsNone(enrolled_log.actor)
        self.assertEqual(str(enrolled_log.ip_address), "192.0.2.40")
        self.assertNotIn("token", str(enrolled_log.metadata).lower())

    def test_successful_training_records_reproducible_model_event(self):
        machine = self.create_machine(external_id="ml-audit", hostname="ml-audit")
        start = pd.Timestamp(timezone.now()).floor("1min")
        index = pd.MultiIndex.from_tuples(
            [
                (machine.pk, start + pd.Timedelta(minutes=index))
                for index in range(200)
            ],
            names=["machine_id", "bucket"],
        )
        frame = pd.DataFrame(
            np.arange(200 * len(FEATURES), dtype=float).reshape(200, len(FEATURES)),
            index=index,
            columns=FEATURES,
        )
        with tempfile.TemporaryDirectory() as directory, patch(
            "ml_engine.pipeline.MODEL_DIR", Path(directory)
        ), patch("ml_engine.pipeline.dataset_for", return_value=frame):
            result = train_customer_model(self.customer_a.pk, days=1)
        event = AuditLog.objects.get(action=AuditLog.Action.MODEL_TRAINED)
        self.assertEqual(event.target_id, result["model_id"])
        self.assertEqual(event.metadata["samples"], 200)
        self.assertFalse(event.metadata["synthetic"])


class AuditIntegrityAndAPITests(TenantAPITestCase):
    def setUp(self):
        self.own = record_audit(
            AuditLog.Action.CONFIG_CHANGED,
            customer=self.customer_a,
            actor=self.admin_a,
            target=self.environment_a,
            ip_address="203.0.113.50",
            metadata={
                "operation": "update",
                "password": "must-not-persist",
                "nested": {"api_key": "must-not-persist"},
            },
        )
        self.foreign = record_audit(
            AuditLog.Action.MACHINE_CREATED,
            customer=self.customer_b,
            actor=self.admin_b,
            target=self.environment_b,
            ip_address="203.0.113.60",
        )

    def test_logs_are_immutable_through_model_database_and_api(self):
        self.own.action = AuditLog.Action.USER_LOGIN
        with self.assertRaises(DjangoValidationError):
            self.own.save()
        with self.assertRaises(DjangoValidationError):
            self.own.delete()
        with self.assertRaises(DatabaseError), transaction.atomic():
            AuditLog.objects.filter(pk=self.own.pk).update(action="TAMPERED")
        with self.assertRaises(DatabaseError), transaction.atomic():
            AuditLog.objects.filter(pk=self.own.pk).delete()
        self.own.refresh_from_db()
        self.assertEqual(self.own.action, AuditLog.Action.CONFIG_CHANGED)

        self.authenticate()
        path = f"/api/audit/{self.own.pk}/"
        self.assertEqual(self.client.post("/api/audit/", {}, format="json").status_code, 405)
        self.assertEqual(self.client.patch(path, {"action": "TAMPERED"}, format="json").status_code, 405)
        self.assertEqual(self.client.delete(path).status_code, 405)

    def test_api_is_tenant_scoped_role_restricted_searchable_and_paginated(self):
        self.authenticate()
        response = self.client.get(
            "/api/audit/",
            {
                "action": AuditLog.Action.CONFIG_CHANGED,
                "search": self.admin_a.email,
                "ip_address": "203.0.113.50",
                "page_size": 1,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.own.pk)
        self.assertEqual(response.data["results"][0]["timestamp"], response.data["results"][0]["created_at"])
        self.assertEqual(response.data["results"][0]["metadata"]["password"], "[REDACTED]")
        self.assertNotIn(self.foreign.pk, {item["id"] for item in response.data["results"]})

        supervisor = self.users_by_role[User.Role.SUPERVISOR]
        self.authenticate(supervisor)
        self.assertEqual(self.client.get("/api/audit/").status_code, 200)
        self.authenticate(self.users_by_role[User.Role.VIEWER])
        self.assertEqual(self.client.get("/api/audit/").status_code, 403)

    def test_invalid_filters_are_rejected(self):
        self.authenticate()
        for params in (
            {"actor": "not-an-id"},
            {"ip_address": "invalid"},
            {"from": "yesterday"},
            {"ordering": "metadata"},
            {"search": "x" * 201},
        ):
            with self.subTest(params=params):
                self.assertEqual(self.client.get("/api/audit/", params).status_code, 400)
