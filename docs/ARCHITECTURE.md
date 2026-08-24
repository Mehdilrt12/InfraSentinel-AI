# Architecture InfraSentinel AI

## Vue logique

```text
Windows Service ─────────────┐
vCenter / ESXi -> pyVmomi ───┼-> Collectors -> Normalizer -> Django API
Hyper-V -> PowerShell/WMI ───┘                         |
                                                     v
                                              PostgreSQL
                                          /       |       \
                                  Rules/Alerts   ML     Outbox events
                                      |           |          |
                                      +---- Risk -+     Channels/Redis
                                               |            |
                                        Notifications     Dashboard
                                               |
                                         Celery/Redis
```

## Responsabilités physiques

- `accounts` : clients, utilisateurs et RBAC.
- `inventory` : environnements, machines, agents, connecteurs et assets virtuels.
- `metrics` : normalisation, ingestion, historique et agrégats.
- `monitoring` : règles, état temporel, alertes, anomalies, recommandations, audit.
- `ml_engine` : datasets, training, évaluation, registry et inference.
- `integrations` : orchestration des collectes VMware/Hyper-V.
- `notifications` : préférences, événements et livraisons.
- `realtime` : outbox durable, tickets et WebSocket multi-tenant.
- `async_tasks` : idempotence, suivi d'exécution et rapports.

## Flux de données

Chaque source possède une identité stable et est rattachée à un `Customer`, un
`Environment` et une `Machine`. L'API reconstruit le scope depuis l'agent ou le
connecteur authentifié; le client ne peut pas imposer un autre tenant. Les valeurs
sont normalisées avant persistance. Les tâches périodiques évaluent les règles et
le ML. Une alerte produit un événement temps réel et, selon sa gravité, un événement
de notification durable.

## Avant / après centralisation

L'ancien fonctionnement local dépendait de `localhost` et d'un seul agent. La
configuration actuelle accepte des URL externes, plusieurs agents simultanés,
CORS/CSRF/hosts explicites, PostgreSQL partagé, Redis, groupes WebSocket par tenant
et workers indépendants.

## Déploiement

Daphne sert HTTP/ASGI, un ou plusieurs workers Celery consomment Redis, un processus
Celery Beat planifie les travaux, PostgreSQL conserve l'état. Le frontend Vite est
compilé puis servi par un serveur statique/reverse proxy. TLS se termine au proxy
ou sur les endpoints configurés.

