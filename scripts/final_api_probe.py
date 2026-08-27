"""Sonde HTTP destructive uniquement sur ses deux tenants temporaires.

Le backend doit déjà être lancé. Les secrets éphémères restent en mémoire et ne
sont jamais affichés. La sonde nettoie ses fixtures dans un bloc ``finally``.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import uuid
from pathlib import Path

import django
import requests


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from accounts.models import Customer, User  # noqa: E402
from inventory.models import Environment, Machine  # noqa: E402
from inventory.services import create_enrollment_code  # noqa: E402
from metrics.models import NormalizedMetric  # noqa: E402


BASE_URL = os.getenv("FINAL_VALIDATION_BASE_URL", "http://127.0.0.1:8000").rstrip(
    "/"
)
TIMEOUT = 10


def require(name: str, actual, expected) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: attendu={expected!r}, observe={actual!r}")


def request(method: str, path: str, **kwargs) -> requests.Response:
    return requests.request(
        method, f"{BASE_URL}{path}", timeout=TIMEOUT, allow_redirects=False, **kwargs
    )


def main() -> int:
    suffix = uuid.uuid4().hex[:10]
    password = secrets.token_urlsafe(24)
    customers: list[Customer] = []
    evidence: dict[str, object] = {}
    try:
        customer_a = Customer.objects.create(
            name=f"Final validation A {suffix}", slug=f"final-a-{suffix}"
        )
        customer_b = Customer.objects.create(
            name=f"Final validation B {suffix}", slug=f"final-b-{suffix}"
        )
        customers.extend([customer_a, customer_b])
        environment_a = Environment.objects.create(
            customer=customer_a, name="Windows A", kind=Environment.Kind.WINDOWS
        )
        environment_b = Environment.objects.create(
            customer=customer_b, name="Windows B", kind=Environment.Kind.WINDOWS
        )
        admin_a = User.objects.create_user(
            username=f"admin-a-{suffix}",
            email=f"admin-a-{suffix}@final.invalid",
            password=password,
            customer=customer_a,
            role=User.Role.ADMIN,
        )
        viewer_a = User.objects.create_user(
            username=f"viewer-a-{suffix}",
            email=f"viewer-a-{suffix}@final.invalid",
            password=password,
            customer=customer_a,
            role=User.Role.VIEWER,
        )
        machine_a = Machine.objects.create(
            customer=customer_a,
            environment=environment_a,
            source_type=Environment.Kind.WINDOWS,
            external_id=f"probe-a-{suffix}",
            hostname="probe-a",
        )
        machine_b = Machine.objects.create(
            customer=customer_b,
            environment=environment_b,
            source_type=Environment.Kind.WINDOWS,
            external_id=f"probe-b-{suffix}",
            hostname="probe-b",
        )

        login = request(
            "POST",
            "/api/auth/token/",
            json={"email": admin_a.email, "password": password},
        )
        require("admin_login", login.status_code, 200)
        access = login.json()["access"]
        admin_headers = {"Authorization": f"Bearer {access}"}
        evidence["admin_login"] = 200

        listing = request("GET", "/api/machines/", headers=admin_headers)
        require("machine_list", listing.status_code, 200)
        payload = listing.json()
        ids = {str(item["id"]) for item in payload["results"]}
        require("own_machine_visible", str(machine_a.pk) in ids, True)
        require("foreign_machine_hidden", str(machine_b.pk) in ids, False)
        evidence["pagination"] = sorted(
            key for key in ("count", "next", "previous", "results") if key in payload
        )

        foreign = request(
            "GET", f"/api/machines/{machine_b.pk}/", headers=admin_headers
        )
        require("cross_tenant_detail", foreign.status_code, 404)
        evidence["cross_tenant_detail"] = 404

        injected = request(
            "GET",
            "/api/machines/",
            headers=admin_headers,
            params={"search": "' OR 1=1 --"},
        )
        require("injection_query", injected.status_code, 200)
        require(
            "injection_does_not_expose_foreign",
            str(machine_b.pk)
            in {str(item["id"]) for item in injected.json()["results"]},
            False,
        )
        evidence["injection_query"] = 200

        viewer_login = request(
            "POST",
            "/api/auth/token/",
            json={"email": viewer_a.email, "password": password},
        )
        require("viewer_login", viewer_login.status_code, 200)
        viewer_headers = {
            "Authorization": f"Bearer {viewer_login.json()['access']}"
        }
        users_forbidden = request("GET", "/api/users/", headers=viewer_headers)
        require("viewer_users_forbidden", users_forbidden.status_code, 403)
        evidence["viewer_users"] = 403

        invalid_token = request(
            "GET",
            "/api/machines/",
            headers={"Authorization": "Bearer invalid-token"},
        )
        require("invalid_token", invalid_token.status_code, 401)
        evidence["invalid_token"] = 401

        malformed = request("POST", "/api/machines/", headers=admin_headers, json={})
        require("malformed_payload", malformed.status_code, 400)
        require("no_traceback_leak", "traceback" in malformed.text.lower(), False)
        evidence["malformed_payload"] = 400

        registration = request("POST", "/api/auth/register/", json={})
        require(
            "public_registration_invalid_payload",
            registration.status_code in {400, 403},
            True,
        )
        evidence["public_registration"] = {
            "status": registration.status_code,
            "mode": "disabled" if registration.status_code == 403 else "enabled-local",
        }

        csrf = request(
            "POST",
            "/api/auth/browser/login/",
            json={"email": admin_a.email, "password": password},
        )
        require("browser_login_without_csrf", csrf.status_code, 403)
        evidence["csrf_without_cookie"] = 403

        enrollment_code = create_enrollment_code(customer_a, environment_a)
        enrolled = request(
            "POST",
            "/api/agent/enroll/",
            json={
                "enrollment_code": enrollment_code,
                "external_id": f"agent-{suffix}",
                "hostname": "agent-probe",
                "ip_address": "127.0.0.2",
                "os_information": {"system": "Windows", "probe": True},
                "version": "2.0.0",
            },
        )
        require("agent_enrollment", enrolled.status_code, 201)
        enrolled_payload = enrolled.json()
        agent_token = enrolled_payload["token"]
        agent_headers = {"X-Agent-Token": agent_token}
        heartbeat = request(
            "POST",
            "/api/agent/heartbeat/",
            headers=agent_headers,
            json={"version": "2.0.0"},
        )
        require("agent_heartbeat", heartbeat.status_code, 200)
        require("heartbeat_token_not_echoed", "token" in heartbeat.text.lower(), False)

        ingested = request(
            "POST",
            "/api/agent/metrics/",
            headers=agent_headers,
            json={
                "machine_id": enrolled_payload["machine_id"],
                "metrics": [
                    {
                        "metric_name": "cpu.percent",
                        "metric_value": 17.5,
                        "unit": "%",
                        "idempotency_key": f"final-probe-{suffix}",
                    }
                ],
            },
        )
        require("agent_metric_ingestion", ingested.status_code, 202)
        require(
            "metric_normalized",
            NormalizedMetric.objects.filter(
                machine_id=enrolled_payload["machine_id"],
                metric_name="system.cpu.utilization",
                metric_value=17.5,
            ).exists(),
            True,
        )

        cross_publish = request(
            "POST",
            "/api/agent/metrics/",
            headers=agent_headers,
            json={
                "machine_id": str(machine_b.pk),
                "metrics": [{"metric_name": "cpu.percent", "metric_value": 1}],
            },
        )
        require("agent_cross_tenant_publish", cross_publish.status_code, 403)

        revoked = request(
            "PATCH",
            f"/api/agents/{enrolled_payload['agent_id']}/",
            headers=admin_headers,
            json={"enabled": False},
        )
        require("agent_revoke", revoked.status_code, 200)
        rejected = request(
            "POST", "/api/agent/heartbeat/", headers=agent_headers, json={}
        )
        require("revoked_agent_token", rejected.status_code, 401)
        evidence["agent_lifecycle"] = {
            "enroll": 201,
            "heartbeat": 200,
            "metrics": 202,
            "cross_tenant": 403,
            "revoked": 401,
        }

        security_headers = {
            name: listing.headers.get(name)
            for name in (
                "X-Content-Type-Options",
                "X-Frame-Options",
                "Referrer-Policy",
                "Content-Security-Policy",
            )
        }
        require(
            "security_headers_present",
            all(security_headers.values()),
            True,
        )
        evidence["security_headers"] = security_headers
        print(json.dumps(evidence, indent=2, sort_keys=True))
        return 0
    finally:
        for customer in customers:
            Machine.objects.filter(customer=customer).delete()
            Environment.objects.filter(customer=customer).delete()
            User.objects.filter(customer=customer).delete()
        for customer in reversed(customers):
            Customer.objects.filter(pk=customer.pk).delete()


if __name__ == "__main__":
    raise SystemExit(main())
