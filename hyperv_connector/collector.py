import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


class HyperVCollectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class HyperVConfig:
    host: str
    username: str = ""
    secret_ref: str = ""
    timeout_seconds: int = 60


class HyperVCollector:
    def __init__(self, config):
        self.config = config

    def collect(self):
        script = Path(__file__).with_name("scripts") / "collect.ps1"
        command = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-ComputerName",
            self.config.host,
        ]
        if self.config.username:
            command.extend(["-Username", self.config.username])
        environment = os.environ.copy()
        if self.config.secret_ref:
            secret = environment.pop(self.config.secret_ref, None)
            if not secret:
                raise HyperVCollectionError(
                    f"Secret Hyper-V absent: variable {self.config.secret_ref}"
                )
            environment["INFRASENTINEL_HYPERV_SECRET"] = secret
        try:
            try:
                process = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=self.config.timeout_seconds,
                    env=environment,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise HyperVCollectionError(
                    f"Délai de collecte Hyper-V dépassé ({self.config.timeout_seconds}s)."
                ) from exc
        finally:
            environment.pop("INFRASENTINEL_HYPERV_SECRET", None)
        if process.returncode:
            raise HyperVCollectionError(
                f"Échec PowerShell Hyper-V (code {process.returncode})."
            )
        try:
            return json.loads(process.stdout)
        except json.JSONDecodeError as exc:
            raise HyperVCollectionError(
                "La sortie PowerShell Hyper-V n'est pas un JSON valide."
            ) from exc
