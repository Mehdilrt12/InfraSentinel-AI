import json
import uuid

from django.test import SimpleTestCase
from django.urls import resolve
from rest_framework.test import APIClient

from common.testing import TenantAPITestCase


HTTP_METHODS = {"get", "post", "put", "patch", "delete"}

EXPECTED_OPERATIONS = {
    "/api/agent/enroll/": {"post"},
    "/api/agent/heartbeat/": {"post"},
    "/api/agent/metrics/": {"post"},
    "/api/agents/": {"get"},
    "/api/agents/{id}/": {"get", "patch"},
    "/api/alerts/": {"get"},
    "/api/alerts/{id}/": {"get", "patch"},
    "/api/anomalies/": {"get"},
    "/api/anomalies/{id}/": {"get", "patch"},
    "/api/assets/": {"get"},
    "/api/assets/{id}/": {"get"},
    "/api/audit/": {"get"},
    "/api/audit/{id}/": {"get"},
    "/api/auth/logout/": {"post"},
    "/api/auth/browser/csrf/": {"get"},
    "/api/auth/browser/login/": {"post"},
    "/api/auth/browser/logout/": {"post"},
    "/api/auth/browser/refresh/": {"post"},
    "/api/auth/me/": {"get"},
    "/api/auth/refresh/": {"post"},
    "/api/auth/register/": {"post"},
    "/api/auth/token/": {"post"},
    "/api/collection-runs/": {"get"},
    "/api/collection-runs/{id}/": {"get"},
    "/api/connectors/": {"get", "post"},
    "/api/connectors/{id}/": {"get", "put", "patch", "delete"},
    "/api/connectors/{id}/collect/": {"post"},
    "/api/customers/": {"get", "post"},
    "/api/customers/{id}/": {"get", "put", "patch", "delete"},
    "/api/dashboard/": {"get"},
    "/api/environments/": {"get", "post"},
    "/api/environments/{id}/": {"get", "put", "patch", "delete"},
    "/api/environments/{id}/enrollment_code/": {"post"},
    "/api/health/": {"get"},
    "/api/hyperv/overview/": {"get"},
    "/api/machines/": {"get", "post"},
    "/api/machines/{id}/": {"get", "put", "patch", "delete"},
    "/api/machines/{id}/trends/": {"get"},
    "/api/metric-aggregates/": {"get"},
    "/api/metric-aggregates/{id}/": {"get"},
    "/api/metrics/": {"get"},
    "/api/metrics/{id}/": {"get"},
    "/api/ml/models/": {"get"},
    "/api/ml/models/{id}/": {"get", "patch"},
    "/api/ml/models/evaluate/": {"post"},
    "/api/ml/models/train/": {"post"},
    "/api/notifications/deliveries/": {"get"},
    "/api/notifications/deliveries/{id}/": {"get"},
    "/api/notifications/preferences/": {"get", "post"},
    "/api/notifications/preferences/{id}/": {"get", "put", "patch", "delete"},
    "/api/realtime/replay/": {"get"},
    "/api/realtime/ticket/": {"post"},
    "/api/reports/": {"get"},
    "/api/reports/{id}/": {"get"},
    "/api/reports/generate/": {"post"},
    "/api/rules/": {"get", "post"},
    "/api/rules/{id}/": {"get", "put", "patch", "delete"},
    "/api/rules/{id}/toggle/": {"post"},
    "/api/tasks/": {"get"},
    "/api/tasks/{id}/": {"get"},
    "/api/users/": {"get", "post"},
    "/api/users/{id}/": {"get", "put", "patch", "delete"},
    "/api/vmware/overview/": {"get"},
}


class OpenAPIContractTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.client = APIClient()
        response = cls.client.get(
            "/api/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json"
        )
        if response.status_code != 200:
            raise AssertionError(f"Schema endpoint returned {response.status_code}")
        cls.schema = json.loads(response.content)

    def test_schema_and_swagger_are_public_and_usable_offline(self):
        schema_response = self.client.get(
            "/api/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json"
        )
        self.assertEqual(schema_response.status_code, 200)
        self.assertEqual(self.schema["openapi"], "3.0.3")
        self.assertEqual(self.schema["info"]["title"], "InfraSentinel AI API")

        docs = self.client.get("/api/docs/")
        self.assertEqual(docs.status_code, 200)
        content = docs.content.decode()
        self.assertIn("SwaggerUIBundle", content)
        self.assertIn("/api/schema/", content)
        self.assertIn("drf_spectacular_sidecar", content)
        asset = self.client.get(
            "/static/drf_spectacular_sidecar/swagger-ui-dist/swagger-ui.css"
        )
        self.assertEqual(asset.status_code, 200)
        self.assertIn("text/css", asset.headers["Content-Type"])

    def test_schema_lists_every_current_runtime_operation(self):
        documented = {
            path: set(path_item) & HTTP_METHODS
            for path, path_item in self.schema["paths"].items()
        }
        self.assertEqual(documented, EXPECTED_OPERATIONS)
        self.assertEqual(len(documented), 63)
        self.assertEqual(sum(map(len, documented.values())), 95)

        concrete_id = str(uuid.UUID(int=1))
        for path, methods in documented.items():
            with self.subTest(path=path):
                callback = resolve(path.replace("{id}", concrete_id)).func
                actions = getattr(callback, "actions", None)
                if actions:
                    runtime_methods = (
                        set(actions)
                        & set(callback.cls.http_method_names)
                        & HTTP_METHODS
                    )
                    if path == "/api/ml/models/":
                        runtime_methods.discard("post")
                else:
                    runtime_methods = {
                        method
                        for method in HTTP_METHODS
                        if callable(getattr(callback.cls, method, None))
                    }
                self.assertEqual(runtime_methods, methods)

    def test_every_operation_documents_contract_errors_and_permissions(self):
        for path, path_item in self.schema["paths"].items():
            for method in set(path_item) & HTTP_METHODS:
                operation = path_item[method]
                with self.subTest(path=path, method=method):
                    self.assertTrue(operation.get("summary"))
                    self.assertTrue(operation.get("description"))
                    self.assertTrue(operation.get("tags"))
                    self.assertTrue(operation.get("x-permissions"))
                    statuses = set(operation.get("responses", {}))
                    self.assertTrue(any(status.startswith("2") for status in statuses))
                    self.assertTrue(
                        any(not status.startswith("2") for status in statuses)
                    )

        required_tags = {
            "Authentication",
            "Users",
            "Customers",
            "Agents",
            "Machines",
            "Metrics",
            "Alerts",
            "Anomalies",
            "Predictions",
            "VMware",
            "Hyper-V",
            "Notifications",
            "Dashboard",
        }
        declared_tags = {tag["name"] for tag in self.schema["tags"]}
        self.assertLessEqual(required_tags, declared_tags)

    def test_security_request_response_and_parameter_contracts(self):
        schemes = self.schema["components"]["securitySchemes"]
        self.assertIn("jwtAuth", schemes)
        self.assertIn("cookieAuth", schemes)
        self.assertEqual(schemes["agentToken"]["in"], "header")
        self.assertEqual(schemes["agentToken"]["name"], "X-Agent-Token")

        public_operations = {
            ("/api/health/", "get"),
            ("/api/auth/register/", "post"),
            ("/api/auth/token/", "post"),
            ("/api/auth/refresh/", "post"),
            ("/api/auth/logout/", "post"),
            ("/api/auth/browser/csrf/", "get"),
            ("/api/auth/browser/login/", "post"),
            ("/api/auth/browser/refresh/", "post"),
            ("/api/auth/browser/logout/", "post"),
            ("/api/agent/enroll/", "post"),
        }
        agent_operations = {
            ("/api/agent/heartbeat/", "post"),
            ("/api/agent/metrics/", "post"),
        }
        for path, methods in EXPECTED_OPERATIONS.items():
            for method in methods:
                operation = self.schema["paths"][path][method]
                with self.subTest(security_path=path, method=method):
                    if (path, method) in public_operations:
                        self.assertFalse(operation.get("security"))
                    elif (path, method) in agent_operations:
                        self.assertEqual(operation["security"], [{"agentToken": []}])
                    else:
                        security = operation.get("security", [])
                        self.assertIn({"jwtAuth": []}, security)
                        self.assertIn({"cookieAuth": []}, security)

        machines_create = self.schema["paths"]["/api/machines/"]["post"]
        self.assertIn("requestBody", machines_create)
        self.assertLessEqual(
            {"201", "400", "401", "403", "429"},
            set(machines_create["responses"]),
        )

        metrics_list = self.schema["paths"]["/api/metrics/"]["get"]
        metric_parameters = {item["name"] for item in metrics_list["parameters"]}
        self.assertLessEqual(
            {"page", "customer", "machine", "metric_name", "source_type"},
            metric_parameters,
        )

        trends = self.schema["paths"]["/api/machines/{id}/trends/"]["get"]
        self.assertEqual(trends["tags"], ["Predictions"])
        self.assertNotIn("page", {item["name"] for item in trends["parameters"]})
        self.assertLessEqual(
            {"200", "400", "401", "403", "404", "429"}, set(trends["responses"])
        )

        self.assertEqual(
            self.schema["paths"]["/api/vmware/overview/"]["get"]["tags"],
            ["VMware"],
        )
        self.assertEqual(
            self.schema["paths"]["/api/hyperv/overview/"]["get"]["tags"],
            ["Hyper-V"],
        )


class OpenAPIBehaviorTests(TenantAPITestCase):
    def test_direct_ml_model_creation_is_rejected_in_favor_of_training_action(self):
        self.authenticate()
        response = self.client.post("/api/ml/models/", {}, format="json")
        self.assertEqual(response.status_code, 405)
        self.assertIn("/api/ml/models/train/", str(response.data["detail"]))
