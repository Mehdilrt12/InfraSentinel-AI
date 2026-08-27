from datetime import datetime, timezone as dt_timezone
import logging
from celery import shared_task
from django.utils import timezone
from django.conf import settings
from async_tasks.idempotency import run_once
from inventory.models import IntegrationEndpoint
from vmware_connector.collector import (
    VMwareCollector,
    VMwareCollectionError,
    VMwareConfig,
)
from hyperv_connector.collector import (
    HyperVCollector,
    HyperVCollectionError,
    HyperVConfig,
)
from .models import CollectionRun
from .services import persist_collection
from common.serializers import ConnectorSerializer

logger = logging.getLogger(__name__)


def _bucket():
    return datetime.now(dt_timezone.utc).strftime("%Y%m%d%H%M")[:-1]


def _validate_connector_runtime(connector):
    if connector.kind == IntegrationEndpoint.Kind.VMWARE:
        from urllib.parse import urlparse

        parsed = urlparse(connector.endpoint)
        if parsed.scheme != "https" or not parsed.hostname:
            raise VMwareCollectionError("Configuration vCenter refusée.")
        ConnectorSerializer._validate_target(parsed.hostname)
        if not connector.verify_tls and not settings.ALLOW_INSECURE_CONNECTOR_TLS:
            raise VMwareCollectionError("Vérification TLS vCenter obligatoire.")
    else:
        ConnectorSerializer._validate_target(connector.endpoint)
    ConnectorSerializer._validate_public_config(connector.config)


def _collect(connector, collector):
    run = CollectionRun.objects.create(
        connector=connector, status=CollectionRun.Status.RUNNING
    )
    try:
        result = persist_collection(connector, collector.collect())
    except Exception as exc:
        public_error = f"Échec de collecte {connector.kind}. Consultez les logs serveur."
        logger.error(
            "Connector collection failed connector=%s kind=%s exception=%s",
            connector.pk,
            connector.kind,
            type(exc).__name__,
        )
        run.status = CollectionRun.Status.FAILED
        run.error = public_error
        run.finished_at = timezone.now()
        run.save()
        connector.last_error = public_error
        connector.save(update_fields=["last_error"])
        raise
    run.status = CollectionRun.Status.SUCCESS
    run.finished_at = timezone.now()
    run.discovered_hosts = result["hosts"]
    run.discovered_vms = result["vms"]
    run.discovered_datastores = result["datastores"]
    run.metric_count = result["metrics"]
    run.save()
    return result


@shared_task(
    bind=True,
    name="integrations.collect_vmware_connector",
    autoretry_for=(VMwareCollectionError, OSError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def collect_vmware_connector(self, connector_id, idempotency_key=None):
    connector = IntegrationEndpoint.objects.get(
        pk=connector_id, kind=IntegrationEndpoint.Kind.VMWARE, enabled=True
    )
    config = VMwareConfig(
        connector.endpoint,
        connector.username,
        connector.secret_ref,
        connector.verify_tls,
        connector.timeout_seconds,
    )
    def execute():
        _validate_connector_runtime(connector)
        return _collect(connector, VMwareCollector(config))

    return run_once(
        "integrations.collect_vmware_connector",
        idempotency_key or f"{connector_id}:{_bucket()}",
        self.request.id,
        execute,
        customer_id=connector.customer_id,
    )


@shared_task(
    bind=True,
    name="integrations.collect_hyperv_connector",
    autoretry_for=(HyperVCollectionError, OSError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def collect_hyperv_connector(self, connector_id, idempotency_key=None):
    connector = IntegrationEndpoint.objects.get(
        pk=connector_id, kind=IntegrationEndpoint.Kind.HYPERV, enabled=True
    )
    config = HyperVConfig(
        connector.endpoint,
        connector.username,
        connector.secret_ref,
        connector.timeout_seconds,
    )
    def execute():
        _validate_connector_runtime(connector)
        return _collect(connector, HyperVCollector(config))

    return run_once(
        "integrations.collect_hyperv_connector",
        idempotency_key or f"{connector_id}:{_bucket()}",
        self.request.id,
        execute,
        customer_id=connector.customer_id,
    )


@shared_task(name="integrations.collect_vmware")
def collect_vmware():
    ids = list(
        IntegrationEndpoint.objects.filter(
            kind=IntegrationEndpoint.Kind.VMWARE, enabled=True
        ).values_list("pk", flat=True)
    )
    for connector_id in ids:
        collect_vmware_connector.delay(str(connector_id))
    return {"scheduled": len(ids)}


@shared_task(name="integrations.collect_hyperv")
def collect_hyperv():
    ids = list(
        IntegrationEndpoint.objects.filter(
            kind=IntegrationEndpoint.Kind.HYPERV, enabled=True
        ).values_list("pk", flat=True)
    )
    for connector_id in ids:
        collect_hyperv_connector.delay(str(connector_id))
    return {"scheduled": len(ids)}
