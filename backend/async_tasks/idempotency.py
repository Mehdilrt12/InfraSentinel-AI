from datetime import timedelta
import logging
from django.db import IntegrityError, transaction
from django.utils import timezone
from .models import TaskRun

logger = logging.getLogger(__name__)


def run_once(
    task_name,
    key,
    celery_task_id,
    function,
    *,
    customer_id=None,
    stale_after_seconds=3600,
):
    now = timezone.now()
    scope = {"customer_id": customer_id} if customer_id else {"customer__isnull": True}
    with transaction.atomic():
        try:
            run = TaskRun.objects.select_for_update().get(
                task_name=task_name, idempotency_key=key, **scope
            )
            if run.status == TaskRun.Status.SUCCESS:
                return {"duplicate": True, **run.result}
            if (
                run.status == TaskRun.Status.RUNNING
                and run.started_at > now - timedelta(seconds=stale_after_seconds)
            ):
                return {"duplicate": True, "running": True}
            run.status = TaskRun.Status.RUNNING
            run.celery_task_id = celery_task_id or ""
            run.error = ""
            run.started_at = now
            run.finished_at = None
            run.save()
        except TaskRun.DoesNotExist:
            try:
                run = TaskRun.objects.create(
                    customer_id=customer_id,
                    task_name=task_name,
                    idempotency_key=key,
                    celery_task_id=celery_task_id or "",
                )
            except IntegrityError:
                return {"duplicate": True, "raced": True}
    try:
        result = function() or {}
    except Exception as exc:
        logger.error(
            "Async task failed task=%s run=%s exception=%s",
            task_name,
            run.pk,
            type(exc).__name__,
        )
        TaskRun.objects.filter(pk=run.pk).update(
            status=TaskRun.Status.FAILED,
            error="Échec interne de la tâche. Consultez les logs serveur.",
            finished_at=timezone.now(),
        )
        raise
    TaskRun.objects.filter(pk=run.pk).update(
        status=TaskRun.Status.SUCCESS, result=result, finished_at=timezone.now()
    )
    return {"duplicate": False, **result}
