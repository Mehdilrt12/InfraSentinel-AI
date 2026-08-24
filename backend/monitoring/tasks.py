from celery import shared_task
from .engine import evaluate_all_rules


@shared_task(
    name="monitoring.evaluate_rules",
    autoretry_for=(OSError,),
    retry_backoff=True,
    max_retries=4,
)
def evaluate_rules():
    return {"triggered": evaluate_all_rules()}
