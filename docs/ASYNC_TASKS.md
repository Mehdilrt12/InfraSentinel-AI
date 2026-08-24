# Redis + Celery

## Périmètre

Celery traite uniquement les travaux longs, périodiques ou dépendants d'un service
externe : training/inference ML, envoi des notifications, collecte VMware/Hyper-V,
agrégats historiques et rapports. L'authentification, la validation, l'ingestion
en base et les lectures courtes restent synchrones.

## Configuration

- `REDIS_URL` : channel layer.
- `CELERY_BROKER_URL` : broker Redis.
- `CELERY_RESULT_BACKEND` : résultats Redis séparés.
- `CELERY_TASK_TIME_LIMIT` / `CELERY_TASK_SOFT_TIME_LIMIT` : 900/840 s par défaut.
- ACK tardif, rejet si worker perdu, prefetch 1 et visibility timeout 3600 s.

Celery Beat natif lit `CELERY_BEAT_SCHEDULE` : règles chaque minute, ML et
connecteurs toutes les cinq minutes, notifications toutes les 15 secondes,
agrégats chaque heure. L'extension `django-celery-beat` n'est volontairement pas
utilisée car sa version disponible est incompatible avec Django 6.

## Idempotence et reprise

`TaskRun(task_name,idempotency_key)` possède une contrainte unique et un rattachement
tenant exposé uniquement à son client. SUCCESS renvoie
le résultat antérieur; RUNNING récent évite le doublon; RUNNING dépassant le délai
est repris après crash worker; FAILED peut être réessayé. Les métriques connecteurs
portent aussi une clé unique par ressource/collecte/mesure. Les tâches externes ont
retry exponentiel+jitter et bornes d'essais. Les logs Celery propagent vers le
logging Django sans inclure les secrets.

## Commandes

```powershell
./.venv/Scripts/celery.exe -A config --workdir backend worker -l INFO --pool=solo
./.venv/Scripts/celery.exe -A config --workdir backend beat -l INFO
./.venv/Scripts/python.exe backend/manage.py shell -c "from metrics.tasks import aggregate_history; print(aggregate_history.delay().id)"
```

Sous Windows, `--pool=solo` est recommandé en local. Le lanceur consomme `celery`
et `hyperv`. En production Linux, le worker consomme uniquement `celery`; un worker
Windows séparé doit consommer `hyperv` avec `-Q hyperv`. Les tests couvrent
exécution, duplication, échec/retry, tâche RUNNING stale après restart, isolation
tenant, collecteur mocké et concurrence PostgreSQL.
