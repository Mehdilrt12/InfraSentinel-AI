from celery import shared_task
from django.db.models import Count
from django.utils import timezone
from accounts.models import Customer
from monitoring.models import Alert, Anomaly
from inventory.models import Machine
from .idempotency import run_once
from .models import GeneratedReport, TaskRun


@shared_task(
    bind=True,
    name="reports.generate",
    autoretry_for=(OSError,),
    retry_backoff=True,
    max_retries=3,
)
def generate_report(self, customer_id, kind="summary", idempotency_key=None):
    key = idempotency_key or f"{customer_id}:{kind}:{timezone.now():%Y-%m-%d}"

    def work():
        customer = Customer.objects.get(pk=customer_id)
        result = {
            "machines": Machine.objects.filter(customer=customer)
            .values("status")
            .annotate(count=Count("id"))
            .order_by(),
            "active_alerts": Alert.objects.filter(customer=customer)
            .exclude(status=Alert.Status.RESOLVED)
            .count(),
            "anomalies": Anomaly.objects.filter(customer=customer).count(),
            "generated_at": timezone.now().isoformat(),
        }
        result["machines"] = list(result["machines"])
        GeneratedReport.objects.create(
            customer=customer,
            kind=kind,
            status=TaskRun.Status.SUCCESS,
            result=result,
            completed_at=timezone.now(),
        )
        return result

    return run_once(
        "reports.generate",
        key,
        self.request.id,
        work,
        customer_id=customer_id,
    )
