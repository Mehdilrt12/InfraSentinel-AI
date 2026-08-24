import operator
from datetime import timedelta
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from metrics.models import NormalizedMetric
from inventory.models import Machine
from .alert_service import create_or_update_alert
from .models import MonitoringRule, RuleState

OPERATORS = {
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
}


def _rules_for(metric):
    return (
        MonitoringRule.objects.filter(
            customer=metric.customer,
            metric=metric.metric_name,
            enabled=True,
        )
        .filter(Q(environment__isnull=True) | Q(environment=metric.environment))
        .filter(Q(machine__isnull=True) | Q(machine=metric.machine))
    )


@transaction.atomic
def evaluate_metric(metric):
    if metric.metric_value is None:
        return []
    triggered = []
    now = metric.timestamp
    for rule in _rules_for(metric):
        state, _ = RuleState.objects.select_for_update().get_or_create(
            rule=rule, machine=metric.machine
        )
        matches = OPERATORS[rule.operator](metric.metric_value, rule.threshold)
        state.last_evaluated_at = now
        state.last_value = metric.metric_value
        if not matches:
            state.first_true_at = None
            state.active = False
            state.save()
            continue
        if state.first_true_at is None:
            state.first_true_at = now
        elapsed = max(0, (now - state.first_true_at).total_seconds())
        if elapsed >= rule.duration_seconds:
            alert, _ = create_or_update_alert(
                machine=metric.machine,
                alert_type="RULE_THRESHOLD",
                severity=rule.severity,
                source=metric.source_type,
                message=f"{rule.name}: {metric.metric_name} {rule.operator} {rule.threshold}",
                context={
                    "metric_name": metric.metric_name,
                    "value": metric.metric_value,
                    "unit": metric.unit,
                    "rule_id": str(rule.pk),
                    "duration_seconds": elapsed,
                    "source_type": metric.source_type,
                },
                source_key=str(rule.pk),
                cooldown_seconds=rule.cooldown_seconds,
            )
            state.active = True
            triggered.append(alert)
        state.save()
    return triggered


def evaluate_all_rules(since_minutes=10):
    cutoff = timezone.now() - timedelta(minutes=since_minutes)
    metrics = (
        NormalizedMetric.objects.filter(timestamp__gte=cutoff)
        .order_by("timestamp")
        .iterator(chunk_size=1000)
    )
    count = sum(len(evaluate_metric(metric)) for metric in metrics)
    count += evaluate_offline_machines()
    return count


def evaluate_offline_machines():
    count = 0
    now = timezone.now()
    for rule in MonitoringRule.objects.filter(metric="machine.online", enabled=True):
        machines = Machine.objects.filter(customer=rule.customer)
        if rule.environment_id:
            machines = machines.filter(environment=rule.environment)
        if rule.machine_id:
            machines = machines.filter(pk=rule.machine_id)
        cutoff = now - timedelta(seconds=rule.duration_seconds)
        for machine in machines.filter(
            Q(last_seen__lt=cutoff) | Q(last_seen__isnull=True)
        ):
            transitioned = machine.status != Machine.Status.OFFLINE
            machine.status = Machine.Status.OFFLINE
            machine.save(update_fields=["status"])
            if transitioned:
                from realtime.publisher import publish

                publish(
                    machine.customer,
                    "machine.offline",
                    {"machine_id": str(machine.pk), "hostname": machine.hostname},
                    machine.pk,
                )
            create_or_update_alert(
                machine=machine,
                alert_type="MACHINE_OFFLINE",
                severity=rule.severity,
                source=machine.source_type,
                message=f"{machine.hostname} ne répond plus",
                context={
                    "metric_name": "machine.online",
                    "value": 0,
                    "rule_id": str(rule.pk),
                    "source_type": machine.source_type,
                },
                source_key=str(rule.pk),
                cooldown_seconds=rule.cooldown_seconds,
            )
            count += 1
    return count
