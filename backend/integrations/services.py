from django.db import transaction
from django.utils import timezone
from inventory.models import Machine, VirtualAsset
from metrics.services import ingest_metrics


@transaction.atomic
def persist_collection(connector, payload):
    hosts = payload.get("hosts") or []
    vms = payload.get("vms") or []
    datastores = payload.get("datastores") or []
    metric_count = 0
    seen_external_ids = set()
    for resource in [*hosts, *vms, *datastores]:
        external_id = str(resource["external_id"])
        seen_external_ids.add(external_id)
        state = str(resource.get("state", ""))
        offline_states = {
            "poweredoff",
            "off",
            "stopped",
            "unavailable",
            "inaccessible",
        }
        machine_status = (
            Machine.Status.OFFLINE
            if state.lower() in offline_states
            else Machine.Status.ONLINE
        )
        machine, _ = Machine.objects.update_or_create(
            customer=connector.customer,
            source_type=connector.kind,
            external_id=f"{connector.pk}:{external_id}",
            defaults={
                "environment": connector.environment,
                "hostname": resource.get("name") or external_id,
                "status": machine_status,
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
            if machine_status == Machine.Status.OFFLINE:
                Machine.objects.filter(pk=machine.pk).update(
                    status=Machine.Status.OFFLINE
                )
    stale_assets = connector.assets.exclude(external_id__in=seen_external_ids)
    for asset in stale_assets.select_related("machine"):
        asset.state = "UNAVAILABLE"
        asset.save(update_fields=["state"])
        if asset.machine and asset.machine.status != Machine.Status.OFFLINE:
            asset.machine.status = Machine.Status.OFFLINE
            asset.machine.save(update_fields=["status", "updated_at"])
            from realtime.publisher import publish

            publish(
                connector.customer,
                "machine.offline",
                {
                    "machine_id": str(asset.machine_id),
                    "hostname": asset.machine.hostname,
                },
                asset.machine_id,
            )
    connector.last_sync_at = timezone.now()
    connector.last_error = ""
    connector.save(update_fields=["last_sync_at", "last_error"])
    return {
        "hosts": len(hosts),
        "vms": len(vms),
        "datastores": len(datastores),
        "metrics": metric_count,
    }
