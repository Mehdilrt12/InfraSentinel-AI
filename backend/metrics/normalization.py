import math
from datetime import datetime, timedelta, timezone as dt_timezone
from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_datetime

ALIASES = {
    "cpu": "system.cpu.utilization",
    "cpu.percent": "system.cpu.utilization",
    "cpu_usage": "system.cpu.utilization",
    "memory": "system.memory.utilization",
    "memory.percent": "system.memory.utilization",
    "ram_usage": "system.memory.utilization",
    "disk": "system.disk.utilization",
    "disk.percent": "system.disk.utilization",
    "disk_usage": "system.disk.utilization",
    "disk.free": "system.disk.free",
    "disk_free": "system.disk.free",
    "disk.read": "system.disk.io.read",
    "disk.write": "system.disk.io.write",
    "network.in": "system.network.in",
    "network.out": "system.network.out",
    "network_in": "system.network.in",
    "network_out": "system.network.out",
    "latency": "system.network.latency",
    "uptime": "system.uptime",
    "process_count": "system.process.count",
    "gpu": "system.gpu.utilization",
    "service.state": "windows.service.state",
    "datastore.usage": "vmware.datastore.utilization",
    "vm.state": "virtual.machine.state",
}

DEFAULT_UNITS = {
    "system.cpu.utilization": "%",
    "system.memory.utilization": "%",
    "system.disk.utilization": "%",
    "system.disk.free": "bytes",
    "system.disk.io.read": "bytes/s",
    "system.disk.io.write": "bytes/s",
    "system.network.in": "bytes/s",
    "system.network.out": "bytes/s",
    "system.network.latency": "ms",
    "system.uptime": "seconds",
    "system.process.count": "count",
    "system.gpu.utilization": "%",
}


def _timestamp(value):
    if value is None:
        return datetime.now(dt_timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=dt_timezone.utc)
    parsed = parse_datetime(str(value))
    if parsed is None:
        raise ValidationError({"timestamp": "Horodatage ISO-8601 invalide."})
    result = parsed if parsed.tzinfo else parsed.replace(tzinfo=dt_timezone.utc)
    if result > datetime.now(dt_timezone.utc) + timedelta(minutes=5):
        raise ValidationError(
            {"timestamp": "Un horodatage situé dans le futur est refusé."}
        )
    return result


def _canonical_value_unit(canonical, value, unit, metadata):
    unit = str(unit or DEFAULT_UNITS.get(canonical, "")).strip()
    if value is None:
        return value, unit
    rates = {
        "system.disk.io.read",
        "system.disk.io.write",
        "system.network.in",
        "system.network.out",
    }
    normalized_unit = unit.lower().replace(" ", "")
    factors = {"kib/s": 1024, "mib/s": 1024**2, "gib/s": 1024**3}
    if canonical in rates and normalized_unit in factors:
        metadata.setdefault("original_unit", unit)
        value *= factors[normalized_unit]
        unit = "bytes/s"
    return value, unit


def normalize_metric(raw, *, source_type, environment, machine, customer):
    raw_name = str(raw.get("metric_name") or raw.get("name") or "").strip()
    if not raw_name:
        raise ValidationError({"metric_name": "Ce champ est obligatoire."})
    canonical = ALIASES.get(raw_name.lower(), raw_name.lower().replace(" ", "."))
    if len(canonical) > 120:
        raise ValidationError(
            {"metric_name": "Le nom normalisé dépasse 120 caractères."}
        )
    value = raw.get("metric_value", raw.get("value"))
    if value is not None:
        try:
            value = float(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                {"metric_value": "Une valeur numérique est attendue."}
            ) from exc
        if not math.isfinite(value):
            raise ValidationError(
                {"metric_value": "La valeur doit être un nombre fini."}
            )
    raw_metadata = raw.get("metadata") or {}
    if not isinstance(raw_metadata, dict):
        raise ValidationError({"metadata": "Un objet JSON est attendu."})
    metadata = dict(raw_metadata)
    metadata.setdefault("raw_metric_name", raw_name)
    metadata.setdefault("normalizer_version", "2.0")
    value, unit = _canonical_value_unit(canonical, value, raw.get("unit"), metadata)
    idempotency_key = raw.get("idempotency_key") or None
    if idempotency_key is not None and len(str(idempotency_key)) > 128:
        raise ValidationError(
            {"idempotency_key": "La clé ne peut pas dépasser 128 caractères."}
        )
    return {
        "timestamp": _timestamp(raw.get("timestamp")),
        "customer": customer,
        "environment": environment,
        "machine": machine,
        "source_type": source_type,
        "metric_name": canonical,
        "metric_value": value,
        "unit": unit[:32],
        "status": str(raw.get("status") or "")[:32],
        "metadata": metadata,
        "idempotency_key": idempotency_key,
    }


def normalize_batch(items, **scope):
    if not isinstance(items, list) or not items:
        raise ValidationError({"metrics": "Une liste non vide est attendue."})
    if len(items) > 5000:
        raise ValidationError({"metrics": "Un lot ne peut pas dépasser 5000 mesures."})
    return [normalize_metric(item, **scope) for item in items]
