import logging
from urllib.parse import urljoin
import requests

logger = logging.getLogger(__name__)


class AgentAPIError(RuntimeError):
    def __init__(self, message, status_code=None, retryable=True):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class AgentClient:
    def __init__(self, config, token=None):
        self.config = config
        self.token = token
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "InfraSentinel-Agent/2.0.0"

    def _post(self, path, payload, authenticated=True):
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if authenticated:
            if not self.token:
                raise AgentAPIError("Agent non enrôlé.", retryable=False)
            headers["X-Agent-Token"] = self.token
        try:
            response = self.session.post(
                urljoin(self.config.backend_url.rstrip("/") + "/", path.lstrip("/")),
                json=payload,
                headers=headers,
                timeout=self.config.request_timeout_seconds,
                verify=self.config.verify_tls,
            )
        except requests.RequestException as exc:
            raise AgentAPIError(f"Serveur indisponible: {exc}") from exc
        if response.status_code in {401, 403}:
            raise AgentAPIError(
                "Authentification agent refusée.", response.status_code, retryable=False
            )
        if response.status_code == 429 or response.status_code >= 500:
            raise AgentAPIError(
                f"Erreur serveur HTTP {response.status_code}.",
                response.status_code,
                retryable=True,
            )
        if not response.ok:
            raise AgentAPIError(
                f"Requête refusée HTTP {response.status_code}.",
                response.status_code,
                retryable=False,
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise AgentAPIError(
                "Réponse serveur non JSON.", response.status_code, retryable=False
            ) from exc
        if not isinstance(data, dict):
            raise AgentAPIError(
                "Structure de réponse serveur invalide.",
                response.status_code,
                retryable=False,
            )
        return data

    def enroll(self, enrollment_code, identity):
        return self._post(
            "api/agent/enroll/",
            {"enrollment_code": enrollment_code, **identity},
            authenticated=False,
        )

    def heartbeat(self, version):
        return self._post("api/agent/heartbeat/", {"version": version})

    def send_metrics(self, machine_id, metrics):
        return self._post(
            "api/agent/metrics/", {"machine_id": machine_id, "metrics": metrics}
        )
