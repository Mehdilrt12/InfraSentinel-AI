from datetime import timedelta
import numpy as np
from django.db.models import Q
from django.utils import timezone
from metrics.models import NormalizedMetric
from monitoring.models import MonitoringRule


def _target_rule(machine, metric_name):
    return (
        MonitoringRule.objects.filter(
            customer=machine.customer,
            metric=metric_name,
            enabled=True,
            operator__in=[">", ">=", "<", "<="],
        )
        .filter(Q(environment__isnull=True) | Q(environment=machine.environment))
        .filter(Q(machine__isnull=True) | Q(machine=machine))
        .order_by("-machine_id", "-environment_id", "severity")
        .first()
    )


def _confidence(sample_count, span_seconds):
    if sample_count >= 30 and span_seconds >= 6 * 3600:
        return "HIGH"
    if sample_count >= 10 and span_seconds >= 3600:
        return "MEDIUM"
    return "LOW"


def analyze_machine_trends(machine, *, hours=24, max_metrics=12):
    cutoff = timezone.now() - timedelta(hours=hours)
    rows = list(
        NormalizedMetric.objects.filter(
            machine=machine,
            timestamp__gte=cutoff,
            metric_value__isnull=False,
        )
        .order_by("metric_name", "timestamp")
        .values("metric_name", "timestamp", "metric_value", "unit")
    )
    groups = {}
    for row in rows:
        groups.setdefault(row["metric_name"], []).append(row)
    results = []
    for metric_name, samples in list(groups.items())[:max_metrics]:
        if len(samples) < 3:
            continue
        origin = samples[0]["timestamp"]
        x = np.array(
            [(sample["timestamp"] - origin).total_seconds() for sample in samples],
            dtype=float,
        )
        y = np.array([sample["metric_value"] for sample in samples], dtype=float)
        span = float(x[-1] - x[0])
        if span <= 0:
            continue
        slope = float(np.polyfit(x, y, 1)[0])
        rolling_count = min(5, len(y))
        rolling_average = float(y[-rolling_count:].mean())
        delta_per_hour = slope * 3600
        epsilon = max(1e-9, abs(rolling_average) * 0.001)
        trend = (
            "INCREASING"
            if delta_per_hour > epsilon
            else "DECREASING"
            if delta_per_hour < -epsilon
            else "STABLE"
        )
        rule = _target_rule(machine, metric_name)
        breach_at = None
        already_breached = False
        risk = 0
        if rule:
            if rule.operator in {">", ">="}:
                already_breached = rolling_average >= rule.threshold
                toward = slope > 0
            else:
                already_breached = rolling_average <= rule.threshold
                toward = slope < 0
            if already_breached:
                risk = 100
            elif toward:
                seconds = (rule.threshold - rolling_average) / slope
                if 0 < seconds <= 3650 * 86400:
                    breach_at = timezone.now() + timedelta(seconds=float(seconds))
                    if seconds <= 3600:
                        risk = 90
                    elif seconds <= 86400:
                        risk = 70
                    elif seconds <= 7 * 86400:
                        risk = 50
                    else:
                        risk = 20
        results.append(
            {
                "metric_name": metric_name,
                "unit": samples[-1]["unit"],
                "sample_count": len(samples),
                "window_hours": hours,
                "last_value": float(y[-1]),
                "rolling_average": rolling_average,
                "rate_of_change_per_hour": delta_per_hour,
                "trend": trend,
                "risk_score": risk,
                "rule_id": str(rule.pk) if rule else None,
                "threshold": rule.threshold if rule else None,
                "estimated_threshold_breach_at": (
                    breach_at.isoformat() if breach_at else None
                ),
                "already_breached": already_breached,
                "confidence": _confidence(len(samples), span),
                "is_estimate": True,
                "disclaimer": "Estimation linéaire fondée sur l'historique récent; ce n'est pas une certitude.",
            }
        )
    return sorted(results, key=lambda item: item["risk_score"], reverse=True)
