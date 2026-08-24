from django.db import transaction
from django.utils import timezone
from inventory.models import Machine
from realtime.publisher import publish
from .models import NormalizedMetric
from .normalization import normalize_batch


@transaction.atomic
def ingest_metrics(*, machine, source_type, items):
    if machine.source_type != source_type:
        raise ValueError("Le type de source ne correspond pas à la machine.")
    rows = normalize_batch(
        items,
        source_type=source_type,
        customer=machine.customer,
        environment=machine.environment,
        machine=machine,
    )
    keys = {row["idempotency_key"] for row in rows if row["idempotency_key"]}
    existing = set(
        NormalizedMetric.objects.filter(
            customer=machine.customer, idempotency_key__in=keys
        ).values_list("idempotency_key", flat=True)
    )
    seen = set(existing)
    insert_rows = []
    for row in rows:
        key = row["idempotency_key"]
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        insert_rows.append(row)
    NormalizedMetric.objects.bulk_create(
        [NormalizedMetric(**row) for row in insert_rows],
        ignore_conflicts=True,
        batch_size=1000,
    )
    machine.status = Machine.Status.ONLINE
    machine.last_seen = timezone.now()
    machine.save(update_fields=["status", "last_seen", "updated_at"])
    latest = rows[-1]
    publish(
        machine.customer,
        "metric.update",
        {
            "machine_id": str(machine.pk),
            "metric_name": latest["metric_name"],
            "metric_value": latest["metric_value"],
            "unit": latest["unit"],
            "accepted": len(insert_rows),
        },
        machine.pk,
    )
    return len(insert_rows)
