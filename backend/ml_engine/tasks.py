from datetime import datetime, timezone as dt_timezone
from celery import shared_task
from accounts.models import Customer
from async_tasks.idempotency import run_once
from .pipeline import infer_customer, train_customer_model


@shared_task(
    bind=True,
    name="ml.train",
    autoretry_for=(OSError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=4,
)
def train_model(self, customer_id, days=30, idempotency_key=None):
    key = idempotency_key or f"{customer_id}:{datetime.now(dt_timezone.utc):%Y-%m-%d}"
    return run_once(
        "ml.train",
        key,
        self.request.id,
        lambda: train_customer_model(customer_id, days=days),
    )


@shared_task(
    bind=True,
    name="ml.analyze_customer",
    autoretry_for=(OSError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def analyze_customer(self, customer_id, idempotency_key=None):
    bucket = datetime.now(dt_timezone.utc).strftime("%Y%m%d%H%M")[:-1]
    return run_once(
        "ml.analyze_customer",
        idempotency_key or f"{customer_id}:{bucket}",
        self.request.id,
        lambda: infer_customer(customer_id),
    )


@shared_task(name="ml.analyze_recent")
def analyze_recent_metrics():
    for customer_id in Customer.objects.filter(active=True).values_list(
        "pk", flat=True
    ):
        analyze_customer.delay(str(customer_id))
    return {"scheduled": Customer.objects.filter(active=True).count()}
