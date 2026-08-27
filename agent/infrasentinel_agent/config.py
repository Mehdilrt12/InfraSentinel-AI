import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class AgentConfig:
    backend_url: str
    machine_name: str
    interval_seconds: int = 30
    heartbeat_seconds: int = 60
    request_timeout_seconds: int = 15
    verify_tls: bool = True
    allow_insecure_tls: bool = False
    critical_services: list[str] = field(default_factory=list)
    latency_host: str = ""
    latency_port: int = 443
    spool_max_items: int = 10000
    log_max_bytes: int = 5 * 1024 * 1024
    log_backup_count: int = 5
    allow_http_localhost: bool = False

    @classmethod
    def from_mapping(cls, data):
        config = cls(**data)
        config.validate()
        return config

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for key, env_name in {
            "backend_url": "INFRASENTINEL_SERVER_URL",
            "machine_name": "INFRASENTINEL_MACHINE_NAME",
        }.items():
            if os.getenv(env_name):
                data[key] = os.environ[env_name]
        return cls.from_mapping(data)

    def validate(self):
        parsed = urlparse(self.backend_url)
        local = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        if (
            not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("L'URL serveur ne doit contenir ni secret, ni paramètre, ni fragment.")
        if parsed.scheme != "https" and not (self.allow_http_localhost and local):
            raise ValueError(
                "HTTPS est obligatoire hors test local explicitement autorisé."
            )
        if not self.verify_tls and not self.allow_insecure_tls:
            raise ValueError(
                "La désactivation de la vérification TLS doit être explicitement autorisée."
            )
        if (
            self.interval_seconds < 5
            or self.heartbeat_seconds < 5
            or not 1 <= self.request_timeout_seconds <= 300
            or not self.machine_name
            or len(self.machine_name) > 255
        ):
            raise ValueError("Les intervalles de configuration sont invalides.")
        if any(not item or len(item) > 256 for item in self.critical_services):
            raise ValueError("La liste des services critiques est invalide.")
        return self

    def to_mapping(self):
        return asdict(self)
