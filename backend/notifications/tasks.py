from celery import shared_task
from .services import dispatch_due_notifications


@shared_task(name="notifications.dispatch_pending")
def dispatch_pending_notifications(limit=100):
    return dispatch_due_notifications(limit)
