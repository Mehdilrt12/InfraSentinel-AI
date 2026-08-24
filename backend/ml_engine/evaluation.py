from datetime import timedelta
from django.db.models import Q
from django.utils import timezone
from accounts.models import Customer
from monitoring.models import Alert, Anomaly


def evaluate_detection_strategies(customer_id, *, days=30, overlap_minutes=15):
    """Compare des événements persistés sans inventer de vérité terrain."""
    customer = Customer.objects.get(pk=customer_id)
    cutoff = timezone.now() - timedelta(days=days)
    rules = list(
        Alert.objects.filter(customer=customer, timestamp__gte=cutoff)
        .filter(Q(type="RULE_THRESHOLD") | Q(type="MACHINE_OFFLINE"))
        .values("machine_id", "timestamp")
    )
    anomalies = list(
        Anomaly.objects.filter(customer=customer, detected_at__gte=cutoff).values(
            "machine_id", "detected_at"
        )
    )
    overlap = timedelta(minutes=overlap_minutes)
    paired = 0
    for anomaly in anomalies:
        if any(
            rule["machine_id"] == anomaly["machine_id"]
            and abs(rule["timestamp"] - anomaly["detected_at"]) <= overlap
            for rule in rules
        ):
            paired += 1
    return {
        "period_days": days,
        "rule_incidents": len(rules),
        "ml_anomalies": len(anomalies),
        "hybrid_overlaps": paired,
        "hybrid_unique_events": len(rules) + len(anomalies) - paired,
        "overlap_window_minutes": overlap_minutes,
        "ground_truth_available": False,
        "precision": None,
        "recall": None,
        "note": "Comparaison opérationnelle; aucune métrique supervisée n'est calculée sans labels réels.",
    }
