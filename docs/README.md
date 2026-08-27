# Documentation technique InfraSentinel AI

Ce répertoire décrit l'état réellement vérifié de la plateforme au 27 août 2026.
La documentation distingue le code testé, les intégrations testées avec mocks et
les validations qui nécessitent encore une infrastructure externe.

## Parcours recommandé

| Besoin | Document |
|---|---|
| Vérifier la release de soutenance | [validation locale finale](LOCAL_FINAL_VALIDATION_REPORT.md), [validation historique](FINAL_VALIDATION_REPORT.md), [release finale](FINAL_RELEASE.md) |
| Comprendre le système | [Architecture](ARCHITECTURE.md), [base de données](DATABASE.md), [métriques](METRICS.md) |
| Exploiter en local/LAN | [architecture du laboratoire](LOCAL_LAB_ARCHITECTURE.md), [audit des données réelles](REAL_LOCAL_DATA_AUDIT.md), [campagne LAN](REAL_LOCAL_LAN_VALIDATION.md) |
| Utiliser l'API | [API/OpenAPI](API.md), [temps réel](REALTIME.md), [audit](AUDIT_LOGS.md) |
| Exploiter la supervision | [règles](RULE_ENGINE.md), [alertes](ALERT_ENGINE.md), [recommandations](RECOMMENDATIONS.md), [notifications](NOTIFICATIONS.md) |
| Comprendre l'IA/ML | [pipeline ML](ML.md), [évaluation](ML_EVALUATION.md), [analyse prédictive](PREDICTIVE_ANALYSIS.md) |
| Déployer les collecteurs | [agent Windows](AGENT.md), [installateur](AGENT_INSTALLATION.md), [VMware](VMWARE.md), [Hyper-V](HYPERV.md) |
| Déployer la plateforme | [tâches asynchrones](ASYNC_TASKS.md), [Docker](DOCKER.md), [déploiement](DEPLOYMENT.md), [sécurité](SECURITY_AUDIT.md) |
| Exploiter le laboratoire local | [architecture locale](LOCAL_LAB_ARCHITECTURE.md), [validation ML locale](LOCAL_ML_VALIDATION.md), [performance locale](LOCAL_PERFORMANCE_REPORT.md), [démonstration locale](LOCAL_PFE_DEMO.md) |
| Préparer la soutenance | [performance locale](LOCAL_PERFORMANCE_REPORT.md), [validation ML locale](LOCAL_ML_VALIDATION.md), [scénario local](LOCAL_PFE_DEMO.md), [dashboard](DASHBOARD.md) |

Les rapports [baseline](BASELINE.md), [reconstruction](RECONSTRUCTION_AUDIT.md) et
[récupération des tests](TEST_RECOVERY_REPORT.md) sont historiques : les chiffres
de validation courants dans ce document et dans `DATABASE.md` les remplacent.

## État vérifié

- Backend : Django 6.0.8, Django REST Framework 3.17.1, Channels 4.3.2,
  Celery 5.6 et PostgreSQL 17.
- Frontend : React 19.1.1, Vite 6.4.3, Axios et Recharts.
- ML : scikit-learn 1.9, pandas 3.0.3, Isolation Forest versionné par tenant.
- Agent : Python, psutil, requests, pywin32, service Windows et installateur Inno Setup.
- Suite Django complète sur PostgreSQL et Redis réel : **186 découverts,
  183 réussis, 3 ignorés, 0 échec**, le 26 août 2026.
- Schéma OpenAPI : génération et validation `drf-spectacular` réussies.

Cela ne prouve pas une connexion réelle à vCenter, une collecte Hyper-V autorisée,
un envoi SMTP externe, un déploiement distant ni une capacité de production. Ces
limites sont rappelées dans les documents concernés.

## Démarrage reproductible

### Docker

```powershell
./scripts/prepare-local-compose-env.ps1
docker compose --env-file .env up --build
docker compose --env-file .env ps
```

Par défaut, le dashboard est publié sur `http://127.0.0.1:5173` et l'API sur
`http://127.0.0.1:8000`. Voir [Docker](DOCKER.md) pour les healthchecks.
Pour le LAN, exécuter `./scripts/prepare-local-compose-env.ps1 -Lan`; PostgreSQL
et Redis restent alors liés à loopback tandis que 5173/8000 deviennent
accessibles selon les règles du pare-feu Private.

### Développement Windows

```powershell
Copy-Item backend/.env.example backend/.env
# Configurer PostgreSQL et Redis dans backend/.env
./scripts/setup.ps1
./scripts/start-local.ps1
```

Le frontend seul ne suffit pas : une erreur « serveur API injoignable » signifie
généralement que Daphne/Django n'écoute pas sur l'URL configurée par
`VITE_API_URL`.

## Validation

```powershell
. ./scripts/common.ps1
Import-DotEnv backend/.env
$env:DATABASE_ENGINE='postgresql'
$env:CHANNEL_LAYER='memory'
$env:CELERY_TASK_ALWAYS_EAGER='true'
Push-Location backend
../.venv/Scripts/python.exe manage.py migrate --check
../.venv/Scripts/python.exe manage.py test
../.venv/Scripts/python.exe manage.py spectacular --file ../runtime/openapi.yaml --validate
Pop-Location

Push-Location frontend
npm ci
npm run lint
npm run test
npm run build
Pop-Location

Push-Location agent
../.venv/Scripts/python.exe -m unittest discover -s tests -v
Pop-Location
```

Les commandes supposent une base PostgreSQL de test créable par l'utilisateur
configuré. Ne jamais réutiliser une base de production pour `manage.py test`.

## Configuration minimale

Les exemples versionnés ne contiennent aucun secret. Les variables essentielles
sont `DJANGO_SECRET_KEY`, `JWT_SIGNING_KEY`, `ALLOWED_HOSTS`, `FRONTEND_URL`,
`CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`, les variables `POSTGRES_*`,
`REDIS_URL`, `CELERY_BROKER_URL` et `CELERY_RESULT_BACKEND`. Les URLs publiques du
frontend peuvent venir de `VITE_API_URL` et `VITE_WS_URL`; l'image Docker locale
utilise par défaut les routes same-origin `/api` et `/ws`, ce qui convient au
LAN sans hardcoder l'adresse du serveur. L'inscription publique est contrôlée
par `VITE_PUBLIC_REGISTRATION_ENABLED` au moment du build.

## Diagnostic rapide

1. Vérifier `GET /api/health/` et les healthchecks Docker.
2. Vérifier que les origines incluent le schéma, le domaine et le port exacts.
3. Vérifier les migrations avec `python manage.py showmigrations`.
4. Vérifier les logs `api`, `worker`, `beat`, PostgreSQL et Redis sans publier les
   secrets ou les paramètres de ticket WebSocket.
5. Pour Hyper-V, vérifier qu'un worker Windows consomme explicitement la queue
   `hyperv`; le worker Linux Docker ne la consomme pas.
