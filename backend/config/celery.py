import os
from celery import Celery
from celery.signals import after_setup_logger, after_setup_task_logger

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
app = Celery("infrasentinel")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@after_setup_logger.connect
@after_setup_task_logger.connect
def configure_task_logging(logger=None, **_kwargs):
    if logger:
        logger.propagate = True
