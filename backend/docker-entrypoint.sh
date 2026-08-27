#!/bin/sh
set -eu

case "${1:-api}" in
  migrate)
    exec python manage.py migrate --noinput
    ;;
  api)
    python manage.py collectstatic --noinput
    exec daphne -b 0.0.0.0 -p 8000 config.asgi:application
    ;;
  worker)
    exec celery -A config worker \
      --loglevel="${LOG_LEVEL:-INFO}" \
      --queues=celery,hyperv \
      --hostname="worker@%h" \
      --concurrency="${CELERY_WORKER_CONCURRENCY:-2}"
    ;;
  beat)
    exec celery -A config beat \
      --loglevel="${LOG_LEVEL:-INFO}" \
      --pidfile=/app/celerybeat/celerybeat.pid \
      --schedule=/app/celerybeat/celerybeat-schedule
    ;;
  *)
    exec "$@"
    ;;
esac
