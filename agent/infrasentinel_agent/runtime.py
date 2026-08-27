import logging
import os
import random
import threading
import time
from . import __version__
from .client import AgentAPIError, AgentClient
from .collector import WindowsCollector, ip_address, machine_identity, os_information

logger = logging.getLogger(__name__)


class AgentRuntime:
    def __init__(self, config, credential_store, spool, stop_event=None):
        self.config = config
        self.credentials = credential_store
        self.spool = spool
        self.stop_event = stop_event or threading.Event()
        self.client = AgentClient(config, credential_store.load())
        self.collector = WindowsCollector(config)
        self.machine_id = None

    def _enroll(self):
        code = os.getenv("INFRASENTINEL_ENROLLMENT_CODE")
        if not code:
            raise RuntimeError(
                "INFRASENTINEL_ENROLLMENT_CODE est requis pour le premier enrollment."
            )
        response = self.client.enroll(
            code,
            {
                "external_id": machine_identity(),
                "hostname": self.config.machine_name,
                "ip_address": ip_address(),
                "os_information": os_information(),
                "version": __version__,
            },
        )
        token = response.get("token")
        if not token or not response.get("machine_id"):
            raise RuntimeError("Réponse d'enrollment incomplète.")
        self.credentials.save(token)
        self.client.token = token
        self.machine_id = response["machine_id"]
        os.environ.pop("INFRASENTINEL_ENROLLMENT_CODE", None)

    def _flush(self):
        for row_id, payload in self.spool.peek():
            self.client.send_metrics(payload["machine_id"], payload["metrics"])
            self.spool.delete(row_id)

    def run(self):
        if not self.client.token:
            self._enroll()
        backoff = 1.0
        last_heartbeat = 0.0
        while not self.stop_event.is_set():
            started = time.monotonic()
            try:
                if not self.machine_id:
                    heartbeat = self.client.heartbeat(__version__)
                    self.machine_id = heartbeat.get("machine_id") or self.machine_id
                if started - last_heartbeat >= self.config.heartbeat_seconds:
                    self.client.heartbeat(__version__)
                    last_heartbeat = started
                self._flush()
                metrics = self.collector.collect()
                payload = {"machine_id": self.machine_id, "metrics": metrics}
                try:
                    self.client.send_metrics(self.machine_id, metrics)
                except AgentAPIError:
                    self.spool.push(payload)
                    raise
                backoff = 1.0
                delay = max(
                    0, self.config.interval_seconds - (time.monotonic() - started)
                )
            except AgentAPIError as exc:
                logger.error(
                    "Echec du cycle agent (%s, retryable=%s)",
                    exc.status_code,
                    exc.retryable,
                )
                if not exc.retryable:
                    delay = self.config.interval_seconds
                else:
                    delay = min(300, backoff) + random.uniform(0, min(5, backoff / 4))
                    backoff = min(300, backoff * 2)
            except Exception:
                logger.exception("Erreur agent non gérée")
                delay = min(300, backoff)
                backoff = min(300, backoff * 2)
            self.stop_event.wait(delay)
        logger.info("Arrêt propre de l'agent; %s lot(s) en attente", self.spool.count())

    def stop(self):
        self.stop_event.set()
