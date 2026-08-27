import json
import os
import socket
from pathlib import Path
from urllib.parse import urlparse

from . import __version__
from .client import AgentClient
from .collector import ip_address, machine_identity, os_information
from .config import AgentConfig
from .credentials import CredentialStore


class InstallationConfigurationError(RuntimeError):
    """Raised when setup cannot create a verified agent configuration."""


def _atomic_write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_enrollment_file(path):
    if not path:
        return None
    enrollment_path = Path(path)
    code = enrollment_path.read_text(encoding="utf-8").strip()
    if not code or len(code) > 256 or any(character.isspace() for character in code):
        raise InstallationConfigurationError(
            "Le fichier d'enrôlement ne contient pas un jeton valide."
        )
    return code


def remove_enrollment_file(path):
    """Best-effort overwrite then remove for installer-created temporary files."""
    if not path:
        return
    enrollment_path = Path(path)
    try:
        size = enrollment_path.stat().st_size
        with enrollment_path.open("r+b", buffering=0) as handle:
            handle.write(os.urandom(size))
            handle.flush()
            os.fsync(handle.fileno())
    except FileNotFoundError:
        return
    finally:
        enrollment_path.unlink(missing_ok=True)


def _build_config(config_path, server_url, machine_name, allow_http_localhost):
    config_path = Path(config_path)
    if config_path.exists():
        values = AgentConfig.load(config_path).to_mapping()
    else:
        values = {}

    if server_url:
        values["backend_url"] = server_url.rstrip("/")
        values["allow_http_localhost"] = bool(allow_http_localhost)
    elif "backend_url" not in values:
        raise InstallationConfigurationError(
            "L'URL serveur est obligatoire pour une première installation."
        )
    if machine_name:
        values["machine_name"] = machine_name
    else:
        values.setdefault("machine_name", socket.gethostname())

    parsed = urlparse(values["backend_url"])
    values["latency_host"] = parsed.hostname or ""
    values["latency_port"] = parsed.port or (
        443 if parsed.scheme == "https" else 80
    )
    return AgentConfig.from_mapping(values)


def configure_installation(
    data_dir,
    server_url,
    machine_name=None,
    enrollment_file=None,
    allow_http_localhost=False,
    delete_enrollment_file=False,
):
    """Enroll or validate an upgrade before setup registers the service.

    The bootstrap secret is read from a file so it never appears in process
    arguments.  Only the server-issued agent token is persisted, through DPAPI.
    """
    data_dir = Path(data_dir)
    config_path = data_dir / "config.json"
    credential_store = CredentialStore(data_dir / "credentials.dat")
    try:
        enrollment_code = _read_enrollment_file(enrollment_file)
        config = _build_config(
            config_path,
            server_url,
            machine_name,
            allow_http_localhost,
        )

        if enrollment_code:
            client = AgentClient(config)
            response = client.enroll(
                enrollment_code,
                {
                    "external_id": machine_identity(),
                    "hostname": config.machine_name,
                    "ip_address": ip_address(),
                    "os_information": os_information(),
                    "version": __version__,
                },
            )
            token = response.get("token")
            machine_id = response.get("machine_id")
            agent_id = response.get("agent_id")
            if not token or not machine_id or not agent_id:
                raise InstallationConfigurationError(
                    "La réponse d'enrôlement du serveur est incomplète."
                )
            credential_store.save(token)
        else:
            token = credential_store.load()
            if not token:
                raise InstallationConfigurationError(
                    "Un fichier d'enrôlement est obligatoire pour une première installation."
                )
            response = AgentClient(config, token).heartbeat(__version__)
            machine_id = response.get("machine_id")
            agent_id = response.get("agent_id")
            if not machine_id:
                raise InstallationConfigurationError(
                    "Le serveur n'a pas confirmé l'identité de l'agent existant."
                )

        _atomic_write_json(config_path, config.to_mapping())
        return {
            "agent_id": agent_id,
            "machine_id": machine_id,
            "server_url": config.backend_url,
        }
    finally:
        if delete_enrollment_file:
            remove_enrollment_file(enrollment_file)
