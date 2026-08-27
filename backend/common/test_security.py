from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from async_tasks.idempotency import run_once
from async_tasks.models import TaskRun
from common.logging_utils import redact_secrets
from common.testing import TEST_PASSWORD, TenantAPITestCase
from integrations.models import CollectionRun
from integrations.tasks import _collect
from inventory.models import Agent, Environment, IntegrationEndpoint
from inventory.services import create_enrollment_code, enroll_agent


class BrowserSessionSecurityTests(TenantAPITestCase):
    def setUp(self):
        cache.clear()
        self.browser = APIClient(enforce_csrf_checks=True)

    def _csrf(self):
        response = self.browser.get("/api/auth/browser/csrf/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", response.cookies)
        return response.data["csrf_token"]

    def test_browser_login_requires_csrf_and_keeps_refresh_httponly(self):
        rejected = self.browser.post(
            "/api/auth/browser/login/",
            {"email": self.admin_a.email, "password": TEST_PASSWORD},
            format="json",
        )
        self.assertEqual(rejected.status_code, 403)

        csrf = self._csrf()
        login = self.browser.post(
            "/api/auth/browser/login/",
            {"email": self.admin_a.email, "password": TEST_PASSWORD},
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(login.status_code, 200)
        self.assertIn("access", login.data)
        self.assertNotIn("refresh", login.data)
        refresh_cookie = login.cookies[settings.JWT_REFRESH_COOKIE_NAME]
        self.assertTrue(refresh_cookie["httponly"])
        self.assertEqual(refresh_cookie["samesite"], "Strict")
        self.assertEqual(refresh_cookie["path"], "/api/auth/browser/")

        refreshed = self.browser.post(
            "/api/auth/browser/refresh/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(refreshed.status_code, 200)
        self.assertIn("access", refreshed.data)
        self.assertNotIn("refresh", refreshed.data)

        logout = self.browser.post(
            "/api/auth/browser/logout/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(logout.status_code, 204)
        self.assertEqual(logout.cookies[settings.JWT_REFRESH_COOKIE_NAME]["max-age"], 0)

    def test_login_has_account_and_ip_throttling(self):
        responses = [
            self.client.post(
                "/api/auth/token/",
                {"email": self.admin_a.email, "password": "incorrect-password"},
                format="json",
            )
            for _ in range(6)
        ]
        self.assertEqual([response.status_code for response in responses[:5]], [401] * 5)
        self.assertEqual(responses[-1].status_code, 429)

    def test_invalid_browser_refresh_is_unauthorized_but_logout_still_clears_cookie(self):
        csrf = self._csrf()
        self.browser.cookies[settings.JWT_REFRESH_COOKIE_NAME] = "invalid-token"
        refreshed = self.browser.post(
            "/api/auth/browser/refresh/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(refreshed.status_code, 401, refreshed.content)
        logout = self.browser.post(
            "/api/auth/browser/logout/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(logout.status_code, 204)
        self.assertEqual(logout.cookies[settings.JWT_REFRESH_COOKIE_NAME]["max-age"], 0)

    def test_jwt_has_explicit_issuer_audience_and_rejects_oversized_password(self):
        login = self.client.post(
            "/api/auth/token/",
            {"email": self.admin_a.email, "password": TEST_PASSWORD},
            format="json",
        )
        self.assertEqual(login.status_code, 200)
        claims = AccessToken(login.data["access"])
        self.assertEqual(claims["iss"], settings.SIMPLE_JWT["ISSUER"])
        self.assertEqual(claims["aud"], settings.SIMPLE_JWT["AUDIENCE"])
        oversized = self.client.post(
            "/api/auth/token/",
            {"email": self.admin_a.email, "password": "x" * 129},
            format="json",
        )
        self.assertEqual(oversized.status_code, 400)


class TenantAndAgentSecurityTests(TenantAPITestCase):
    def setUp(self):
        cache.clear()

    def test_inactive_customer_blocks_login_existing_jwt_session_and_agent(self):
        code = create_enrollment_code(self.customer_a, self.environment_a)
        agent, token = enroll_agent(code, external_id="inactive-agent", hostname="host")
        access = str(AccessToken.for_user(self.admin_a))
        self.customer_a.active = False
        self.customer_a.save(update_fields=["active"])

        login = self.client.post(
            "/api/auth/token/",
            {"email": self.admin_a.email, "password": TEST_PASSWORD},
            format="json",
        )
        self.assertEqual(login.status_code, 401)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 403)
        self.client.credentials()
        self.client.force_authenticate(self.admin_a)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 403)
        self.client.force_authenticate(user=None)
        heartbeat = self.client.post(
            "/api/agent/heartbeat/", {}, format="json", HTTP_X_AGENT_TOKEN=token
        )
        self.assertEqual(heartbeat.status_code, 401)
        self.assertTrue(Agent.objects.filter(pk=agent.pk, enabled=True).exists())

    def test_agent_metric_replay_is_idempotent_and_key_is_mandatory(self):
        code = create_enrollment_code(self.customer_a, self.environment_a)
        agent, token = enroll_agent(code, external_id="replay-agent", hostname="host")
        payload = {
            "machine_id": str(agent.machine_id),
            "metrics": [
                {
                    "metric_name": "cpu",
                    "metric_value": 42,
                    "idempotency_key": "security-replay-1",
                }
            ],
        }
        first = self.client.post(
            "/api/agent/metrics/", payload, format="json", HTTP_X_AGENT_TOKEN=token
        )
        replay = self.client.post(
            "/api/agent/metrics/", payload, format="json", HTTP_X_AGENT_TOKEN=token
        )
        self.assertEqual(first.status_code, 202)
        self.assertEqual(first.data["accepted"], 1)
        self.assertEqual(replay.status_code, 202)
        self.assertEqual(replay.data["accepted"], 0)

        missing_key = self.client.post(
            "/api/agent/metrics/",
            {
                "machine_id": str(agent.machine_id),
                "metrics": [{"metric_name": "cpu", "metric_value": 43}],
            },
            format="json",
            HTTP_X_AGENT_TOKEN=token,
        )
        self.assertEqual(missing_key.status_code, 400)
        long_version = self.client.post(
            "/api/agent/heartbeat/",
            {"version": "v" * 41},
            format="json",
            HTTP_X_AGENT_TOKEN=token,
        )
        self.assertEqual(long_version.status_code, 400)

    def test_superuser_invalid_customer_filter_is_a_400_not_a_500(self):
        from accounts.models import User

        root = User.objects.create_superuser(
            username="security-root", email="security-root@test.invalid", password=TEST_PASSWORD
        )
        self.client.force_authenticate(root)
        response = self.client.get("/api/machines/?customer=not-a-uuid")
        self.assertEqual(response.status_code, 400)


@override_settings(PUBLIC_REGISTRATION_ENABLED=True)
class InputLoggingAndConnectorSecurityTests(TenantAPITestCase):
    def setUp(self):
        cache.clear()
        self.authenticate()
        self.vmware_environment = Environment.objects.create(
            customer=self.customer_a,
            name="Security vCenter",
            kind=Environment.Kind.VMWARE,
        )

    def _connector_secret_ref(self):
        return f"INFRASENTINEL_CUSTOMER_{self.customer_a.pk.hex.upper()}_VC_SECRET"

    def test_connector_rejects_loopback_inline_secrets_and_insecure_tls(self):
        base = {
            "environment": str(self.vmware_environment.pk),
            "kind": "VMWARE",
            "name": "unsafe",
            "endpoint": "https://127.0.0.1",
            "username": "svc",
            "secret_ref": self._connector_secret_ref(),
        }
        self.assertEqual(self.client.post("/api/connectors/", base, format="json").status_code, 400)

        base.update({"endpoint": "https://vc.example.test", "verify_tls": False})
        self.assertEqual(self.client.post("/api/connectors/", base, format="json").status_code, 400)

        base.update({"verify_tls": True, "config": {"password": "must-not-persist"}})
        response = self.client.post("/api/connectors/", base, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("must-not-persist", str(response.data))

    def test_connector_and_task_failures_do_not_persist_raw_exception_text(self):
        connector = IntegrationEndpoint.objects.create(
            customer=self.customer_a,
            environment=self.vmware_environment,
            kind=IntegrationEndpoint.Kind.VMWARE,
            name="error-sanitization",
            endpoint="https://vc.example.test",
            username="svc",
            secret_ref=self._connector_secret_ref(),
        )

        class FailingCollector:
            def collect(self):
                raise RuntimeError("password=super-secret internal-host=10.0.0.9")

        with self.assertRaises(RuntimeError):
            _collect(connector, FailingCollector())
        connector.refresh_from_db()
        run = CollectionRun.objects.get(connector=connector)
        self.assertNotIn("super-secret", connector.last_error)
        self.assertNotIn("10.0.0.9", run.error)

        with self.assertRaises(RuntimeError):
            run_once(
                "security.failure",
                "one",
                "task-one",
                lambda: (_ for _ in ()).throw(RuntimeError("token=raw-secret")),
                customer_id=self.customer_a.pk,
            )
        task = TaskRun.objects.get(task_name="security.failure")
        self.assertNotIn("raw-secret", task.error)

    def test_logs_redact_credentials_tickets_and_jwts(self):
        value = redact_secrets(
            "Authorization: Bearer abc.def.ghi ticket=secret-ticket password=hunter2 token=opaque"
        )
        for secret in ("abc.def.ghi", "secret-ticket", "hunter2", "opaque"):
            self.assertNotIn(secret, value)

    def test_api_rejects_form_payloads_and_emits_security_headers(self):
        form = self.client.post(
            "/api/auth/register/",
            {"organization": "Form", "email": "form@test.invalid", "password": TEST_PASSWORD},
        )
        self.assertEqual(form.status_code, 415)
        health = self.client.get("/api/health/")
        self.assertEqual(health.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(health.headers["X-Frame-Options"], "DENY")
        self.assertEqual(health.headers["Referrer-Policy"], "same-origin")
        self.assertEqual(health.headers["Cross-Origin-Opener-Policy"], "same-origin")
        self.assertIn("default-src 'none'", health.headers["Content-Security-Policy"])
        self.assertIn("camera=()", health.headers["Permissions-Policy"])
