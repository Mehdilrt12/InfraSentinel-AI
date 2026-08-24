from datetime import timedelta
from celery import shared_task
from django.db.models import Avg, Count, Max, Min
from django.db.models.functions import TruncHour
from django.utils import timezone
from .models import MetricAggregate, NormalizedMetric


@shared_task(name="metrics.aggregate_history")
def aggregate_history(hours=2):
    cutoff = timezone.now() - timedelta(hours=hours)
    rows = (
        NormalizedMetric.objects.filter(
            timestamp__gte=cutoff, metric_value__isnull=False
        )
        .annotate(bucket=TruncHour("timestamp"))
        .values("machine_id", "metric_name", "bucket")
        .annotate(
            minimum=Min("metric_value"),
            maximum=Max("metric_value"),
            average=Avg("metric_value"),
            sample_count=Count("id"),
        )
    )
    count = 0
    for row in rows.iterator():
        MetricAggregate.objects.update_or_create(
            machine_id=row["machine_id"],
            metric_name=row["metric_name"],
            bucket_start=row["bucket"],
            bucket_seconds=3600,
            defaults={
                "minimum": row["minimum"],
                "maximum": row["maximum"],
                "average": row["average"],
                "sample_count": row["sample_count"],
            },
        )
        count += 1
    return {"aggregates": count}
