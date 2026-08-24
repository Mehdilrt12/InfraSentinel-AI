from django.db import transaction
from django.utils import timezone
from inventory.models import Machine, VirtualAsset
from metrics.services import ingest_metrics


@transaction.atomic
def persist_collection(connector, payload):
    hosts = payload.get("hosts") or []
    vms = payload.get("vms") or []
    metric_count = 0
    for resource in [*hosts, *vms]:
        external_id = str(resource["external_id"])
        machine, _ = Machine.objects.update_or_create(
            customer=connector.customer,
            source_type=connector.kind,
            external_id=f"{connector.pk}:{external_id}",
            defaults={
                "environment": connector.environment,
                "hostname": resource.get("name") or external_id,
                "status": Machine.Status.ONLINE,
                "last_seen": timezone.now(),
                "metadata": {
                    "connector_id": str(connector.pk),
                    **(resource.get("metadata") or {}),
                },
            },
        )
        VirtualAsset.objects.update_or_create(
            connector=connector,
            external_id=external_id,
            defaults={
                "customer": connector.customer,
                "machine": machine,
                "parent_external_id": resource.get("parent_external_id", ""),
                "kind": resource.get("kind", "VM"),
                "name": resource.get("name", external_id),
                "state": resource.get("state", ""),
                "metadata": resource.get("metadata") or {},
                "last_seen": timezone.now(),
            },
        )
        items = resource.get("metrics") or []
        if items:
            for index, item in enumerate(items):
                item.setdefault(
                    "idempotency_key",
                    f"{connector.pk}:{external_id}:{payload.get('collected_at')}:{index}",
                )
                item.setdefault("metadata", {})
                item["metadata"].update(
                    {
                        "connector_id": str(connector.pk),
                        "resource_external_id": external_id,
                        "resource_kind": resource.get("kind"),
                    }
                )
            metric_count += ingest_metrics(
                machine=machine, source_type=connector.kind, items=items
            )
    connector.last_sync_at = timezone.now()
    connector.last_error = ""
    connector.save(update_fields=["last_sync_at", "last_error"])
    return {"hosts": len(hosts), "vms": len(vms), "metrics": metric_count}
