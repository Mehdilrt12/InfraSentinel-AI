import json
import os
from dataclasses import dataclass, field
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
    critical_services: list[str] = field(default_factory=list)
    latency_host: str = ""
    latency_port: int = 443
    spool_max_items: int = 10000
    log_max_bytes: int = 5 * 1024 * 1024
    log_backup_count: int = 5
    allow_http_localhost: bool = False

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for key, env_name in {
            "backend_url": "INFRASENTINEL_SERVER_URL",
            "machine_name": "INFRASENTINEL_MACHINE_NAME",
        }.items():
            if os.getenv(env_name):
                data[key] = os.environ[env_name]
        config = cls(**data)
        parsed = urlparse(config.backend_url)
        local = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        if parsed.scheme != "https" and not (config.allow_http_localhost and local):
            raise ValueError(
                "HTTPS est obligatoire hors test local explicitement autorisé."
            )
        if config.interval_seconds < 5 or config.request_timeout_seconds < 1:
            raise ValueError("Les intervalles de configuration sont invalides.")
        return config
