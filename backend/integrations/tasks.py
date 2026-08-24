from datetime import datetime, timezone as dt_timezone
from celery import shared_task
from django.utils import timezone
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


def _bucket():
    return datetime.now(dt_timezone.utc).strftime("%Y%m%d%H%M")[:-1]


def _collect(connector, collector):
    run = CollectionRun.objects.create(
        connector=connector, status=CollectionRun.Status.RUNNING
    )
    try:
        result = persist_collection(connector, collector.collect())
    except Exception as exc:
        run.status = CollectionRun.Status.FAILED
        run.error = str(exc)
        run.finished_at = timezone.now()
        run.save()
        connector.last_error = str(exc)
        connector.save(update_fields=["last_error"])
        raise
    run.status = CollectionRun.Status.SUCCESS
    run.finished_at = timezone.now()
    run.discovered_hosts = result["hosts"]
    run.discovered_vms = result["vms"]
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
    return run_once(
        "integrations.collect_vmware_connector",
        idempotency_key or f"{connector_id}:{_bucket()}",
        self.request.id,
        lambda: _collect(connector, VMwareCollector(config)),
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
    return run_once(
        "integrations.collect_hyperv_connector",
        idempotency_key or f"{connector_id}:{_bucket()}",
        self.request.id,
        lambda: _collect(connector, HyperVCollector(config)),
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
