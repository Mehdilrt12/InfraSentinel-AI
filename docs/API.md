# API InfraSentinel AI

## Contrat publié

L'API publie un contrat OpenAPI 3.0.3 généré depuis les routes, ViewSets,
serializers, permissions et annotations réellement présents dans le backend.

| Ressource | URL | Accès |
|---|---|---|
| Schéma OpenAPI | `GET /api/schema/` | YAML par défaut; JSON avec `Accept: application/vnd.oai.openapi+json` |
| Swagger UI | `GET /api/docs/` | Interface interactive, assets Swagger servis localement par le sidecar |

`API_DOCS_PUBLIC=true` expose le schéma et Swagger sans authentification, sans
exposer de données ni de secret. Avec `API_DOCS_PUBLIC=false`, ces deux routes
sont réservées à un utilisateur de rôle `ADMIN`. Les routes de documentation ne
sont volontairement pas incluses dans leur propre schéma
(`SERVE_INCLUDE_SCHEMA=false`).
La valeur par défaut hors debug est `false`.

La génération repose sur `drf-spectacular==0.30.0` et le sidecar Swagger
`2026.8.1`, avec des composants de requête et de réponse séparés. Chaque opération contient un résumé, une
description, ses tags, ses statuts de réponse et l'extension `x-permissions`.
Les opérations multi-tenant contiennent aussi `x-tenant-scope`.

Les fichiers CSS/JavaScript Swagger sont collectés dans `STATIC_ROOT` et servis
par WhiteNoise, y compris avec `DEBUG=false`. Le script local et le conteneur API
exécutent `collectstatic` avant Daphne; l'interface ne dépend donc pas d'un CDN.

## Authentification et permissions

### Utilisateurs

Les APIs métier acceptent :

- `Authorization: Bearer <access-token>` ;
- une session Django. Une écriture authentifiée par session reste soumise à la
  protection CSRF de Django.

L'access token expire après 15 minutes. Le refresh token expire après un jour,
est renouvelé à chaque rafraîchissement et l'ancien token est placé en liste
noire. Le bouton **Authorize** de Swagger utilise le schéma `jwtAuth`.

Le dashboard utilise les routes `/api/auth/browser/*` : access token conservé
uniquement en mémoire, refresh rotatif dans un cookie `HttpOnly; SameSite=Strict`
et protection CSRF obligatoire. Les routes `/auth/token`, `/auth/refresh` et
`/auth/logout` restent disponibles pour les clients non navigateur qui savent
protéger leur propre stockage de secrets.

Règles de rôle :

- `AUTHENTICATED` : lecture dans le tenant courant ;
- `ADMIN` ou `SUPERVISOR` : créations, modifications et suppressions protégées
  par `ReadOnlyUnlessManager` ;
- `ADMIN` : administration des utilisateurs, clients et tâches ;
- un superutilisateur peut traverser les tenants. Le paramètre `customer=<uuid>`
  lui permet de limiter les listes concernées ; ce paramètre est ignoré pour les
  autres utilisateurs.

### Agents

Après enrôlement, l'agent utilise `X-Agent-Token: <token>` ou
`Authorization: Bearer <token>`. Ce token opaque n'est renvoyé qu'une fois, n'est
pas un JWT et ne permet de publier que pour la machine associée. Swagger déclare
ce mécanisme sous `agentToken`.

### Isolation client

Les querysets métier sont filtrés côté serveur par `customer`. Un identifiant
d'un autre client renvoie `404` ou une liste vide, au lieu de révéler
l'existence de la ressource. Les relations envoyées dans un body sont validées
pour empêcher une association inter-tenant.

## Conventions HTTP

- Les listes sont paginées avec `page` et renvoient
  `{count, next, previous, results}`. La taille serveur est de 100 éléments.
- Les détails utilisent `id`; il s'agit d'un UUID sauf pour les ressources dont
  le modèle Django utilise un entier (`metrics`, `metric-aggregates`, `audit`,
  `collection-runs`, `tasks`, `reports`, `notifications/preferences`).
- Les erreurs DRF utilisent généralement `{"detail": "..."}`. Les erreurs de
  validation peuvent utiliser un objet par champ dans `detail` ou directement
  dans le body.
- Statuts usuels : `400` validation, `401` authentification, `403` permission ou
  tenant, `404` ressource invisible/inexistante, `405` méthode interdite et
  `429` throttling.
- `DELETE` renvoie `204` sans body. Les tâches Celery planifiées renvoient
  `202 {"task_id": "...", "status": "queued"}`.

## Catalogue des endpoints

Les noms de body ci-dessous correspondent aux composants visibles dans Swagger.
`JWT` signifie JWT Bearer ou session Django.

### Système, authentification et dashboard

| Méthode et URL | Paramètres / body | Réponse de succès | Permission | Erreurs documentées |
|---|---|---|---|---|
| `GET /api/health/` | Aucun | `200` état, version et heure serveur | Public | `429` |
| `POST /api/auth/register/` | organisation, email, mot de passe 10–128 caractères | `201` IDs user/customer/environment | Public si `PUBLIC_REGISTRATION_ENABLED=true` | `400`, `403`, `429` |
| `POST /api/auth/token/` | email, mot de passe | `200` access + refresh | Public | `400`, `401`, `429` |
| `POST /api/auth/refresh/` | refresh | `200` nouvel access et refresh tourné | Porteur du refresh | `400`, `401`, `429` |
| `POST /api/auth/logout/` | refresh | `200` body vide, token révoqué | Porteur du refresh | `400`, `401`, `429` |
| `GET /api/auth/browser/csrf/` | Aucun | `200` jeton CSRF | Public | `429` |
| `POST /api/auth/browser/login/` | email, mot de passe + CSRF | `200` access; refresh uniquement HttpOnly | Public + CSRF | `400`, `401`, `403`, `429` |
| `POST /api/auth/browser/refresh/` | Cookie refresh + CSRF | `200` nouvel access; cookie tourné | Cookie + CSRF | `400`, `401`, `403`, `429` |
| `POST /api/auth/browser/logout/` | Cookie refresh + CSRF | `204`, cookie supprimé | Cookie + CSRF | `400`, `401`, `403`, `429` |
| `GET /api/auth/me/` | Aucun | `200 User` | JWT, authentifié | `401`, `403`, `429` |
| `GET /api/dashboard/` | Aucun | `200` compteurs du tenant | JWT, authentifié | `401`, `403`, `429` |

### Clients et utilisateurs

| Méthode et URL | Paramètres / body | Réponse de succès | Permission | Erreurs documentées |
|---|---|---|---|---|
| `GET`, `POST /api/customers/` | GET: `page`; POST: `CustomerRequest` | `200` liste paginée / `201 Customer` | GET tenant `ADMIN`; POST superuser plateforme | `400/401/403/429` |
| `GET`, `PUT`, `PATCH`, `DELETE /api/customers/{id}/` | `CustomerRequest` pour PUT/PATCH | `200 Customer` ou `204` | GET tenant `ADMIN`; mutations superuser plateforme | `400/401/403/404/429` selon méthode |
| `GET`, `POST /api/users/` | GET: `page`, superuser `customer`; POST: `UserRequest` | `200` liste / `201 User` | JWT, `ADMIN` | GET `401/403/429`; POST `400/401/403/429` |
| `GET`, `PUT`, `PATCH`, `DELETE /api/users/{id}/` | PUT/PATCH: profil, rôle, activation, mot de passe optionnel | `200 User` ou `204` | JWT, `ADMIN` | `400/401/403/404/429` |

### Environnements, machines et prédictions

| Méthode et URL | Paramètres / body | Réponse de succès | Permission | Erreurs documentées |
|---|---|---|---|---|
| `GET`, `POST /api/environments/` | GET: `page`, superuser `customer`; POST: `EnvironmentRequest` | `200` liste / `201 Environment` | Lecture authentifiée; écriture `ADMIN/SUPERVISOR` | GET `401/403/429`; POST `400/401/403/429` |
| `GET`, `PUT`, `PATCH`, `DELETE /api/environments/{id}/` | PUT/PATCH: nom, type, metadata | `200 Environment` ou `204` | Lecture authentifiée; écriture `ADMIN/SUPERVISOR` | `400/401/403/404/429` |
| `POST /api/environments/{id}/enrollment_code/` | `ttl_minutes`, 1 à 1440, défaut 30 | `201` code à usage unique + durée | JWT, `ADMIN/SUPERVISOR` | `400/401/403/404/429` |
| `GET`, `POST /api/machines/` | GET: `page`, superuser `customer`; POST: `MachineRequest` | `200` liste / `201 Machine` | Lecture authentifiée; écriture `ADMIN/SUPERVISOR` | GET `401/403/429`; POST `400/401/403/429` |
| `GET`, `PUT`, `PATCH`, `DELETE /api/machines/{id}/` | PUT/PATCH: environnement, source, identité et metadata | `200 Machine` ou `204` | Lecture authentifiée; écriture `ADMIN/SUPERVISOR` | `400/401/403/404/429` |
| `GET /api/machines/{id}/trends/` | `hours`, entier 1–720, défaut 24 | `200` liste non paginée de tendances explicables | JWT, authentifié | `400/401/403/404/429` |

Il n'existe pas de route artificielle `/api/predictions/`. La fonctionnalité
prédictive réellement disponible est `/api/machines/{id}/trends/`, fondée sur
les métriques normalisées historiques. Le résultat indique notamment pente,
tendance, score de risque, seuil visé, confiance et disclaimer.

### Agents Windows et ingestion

| Méthode et URL | Paramètres / body | Réponse de succès | Permission | Erreurs documentées |
|---|---|---|---|---|
| `GET /api/agents/` | `page`, superuser `customer` | `200` liste paginée | JWT, authentifié | `401/403/429` |
| `GET`, `PATCH /api/agents/{id}/` | PATCH: `enabled`, `version` | `200 Agent` | Lecture authentifiée; PATCH `ADMIN/SUPERVISOR` | GET `401/403/404/429`; PATCH `400/401/403/404/429` |
| `POST /api/agent/enroll/` | code, external ID, hostname, IP, OS, version | `201` agent ID, machine ID et token unique | Code d'enrôlement valide | `400`, `429` |
| `POST /api/agent/heartbeat/` | version optionnelle | `200` statut, heure, IDs | `agentToken` de la machine | `401`, `429` |
| `POST /api/agent/metrics/` | machine ID optionnel + 1 à 5000 métriques avec clé d'idempotence | `202` nombre accepté | `agentToken` de la machine | `400`, `401`, `403`, `429` |

Une métrique d'agent accepte `metric_name` ou son alias `name`,
`metric_value` ou `value`, puis timestamp, unit, status, metadata et
idempotency_key obligatoire. Le normalizer reste l'autorité sur les alias et validations
scientifiques (nombre fini, timestamp ISO-8601, limites de lot).

### Métriques normalisées

| Méthode et URL | Paramètres / body | Réponse de succès | Permission | Erreurs documentées |
|---|---|---|---|---|
| `GET /api/metrics/` | `page`, superuser `customer`, `machine`, `metric_name`, `source_type` | `200` liste paginée | JWT, authentifié, lecture seule | `401/403/429` |
| `GET /api/metrics/{id}/` | ID entier | `200 Metric` | JWT, authentifié, lecture seule | `401/403/404/429` |
| `GET /api/metric-aggregates/` | `page`, superuser `customer` | `200` liste paginée | JWT, authentifié, lecture seule | `401/403/429` |
| `GET /api/metric-aggregates/{id}/` | ID entier | `200 MetricAggregate` | JWT, authentifié, lecture seule | `401/403/404/429` |

### Règles, alertes et anomalies

| Méthode et URL | Paramètres / body | Réponse de succès | Permission | Erreurs documentées |
|---|---|---|---|---|
| `GET`, `POST /api/rules/` | GET: `page`, superuser `customer`; POST: `RuleRequest` | `200` liste / `201 Rule` | Lecture authentifiée; écriture `ADMIN/SUPERVISOR` | GET `401/403/429`; POST `400/401/403/429` |
| `GET`, `PUT`, `PATCH`, `DELETE /api/rules/{id}/` | règle, opérateur, seuil, durée, sévérité, scopes | `200 Rule` ou `204` | Lecture authentifiée; écriture `ADMIN/SUPERVISOR` | `400/401/403/404/429` |
| `POST /api/rules/{id}/toggle/` | Aucun | `200 Rule` avec nouvel état | JWT, `ADMIN/SUPERVISOR` | `401/403/404/429` |
| `GET /api/alerts/` | `page`, superuser `customer`, `status`, `machine` | `200` liste paginée | JWT, authentifié | `401/403/429` |
| `GET`, `PATCH /api/alerts/{id}/` | PATCH: statut du cycle de vie | `200 Alert` | Lecture authentifiée; PATCH `ADMIN/SUPERVISOR` | GET `401/403/404/429`; PATCH `400/401/403/404/429` |
| `GET /api/anomalies/` | `page`, superuser `customer`, `machine` | `200` liste paginée | JWT, authentifié | `401/403/429` |
| `GET`, `PATCH /api/anomalies/{id}/` | PATCH: `acknowledged` | `200 Anomaly` | Lecture authentifiée; PATCH `ADMIN/SUPERVISOR` | GET `401/403/404/429`; PATCH `400/401/403/404/429` |

### Machine Learning

| Méthode et URL | Paramètres / body | Réponse de succès | Permission | Erreurs documentées |
|---|---|---|---|---|
| `GET /api/ml/models/` | `page`, superuser `customer` | `200` versions paginées | JWT, authentifié | `401/403/429` |
| `GET`, `PATCH /api/ml/models/{id}/` | PATCH ne peut modifier que les champs déclarés inscriptibles | `200 MLModel` | Lecture authentifiée; PATCH `ADMIN/SUPERVISOR` | GET `401/403/404/429`; PATCH `400/401/403/404/429` |
| `POST /api/ml/models/train/` | `days` 1–3650, idempotency key optionnelle | `202` tâche planifiée | JWT, `ADMIN/SUPERVISOR`, client requis | `400/401/403/429` |
| `POST /api/ml/models/evaluate/` | `days` 1–3650, idempotency key optionnelle | `202` tâche planifiée | JWT, `ADMIN/SUPERVISOR`, client requis | `400/401/403/429` |

La création directe par `POST /api/ml/models/` est explicitement refusée avec
`405`; elle est exclue du schéma. Une version doit être créée par le pipeline
reproductible `/train/`, et non par insertion manuelle d'un enregistrement.

### VMware et Hyper-V

| Méthode et URL | Paramètres / body | Réponse de succès | Permission | Erreurs documentées |
|---|---|---|---|---|
| `GET`, `POST /api/connectors/` | GET: `page`, superuser `customer`; POST: endpoint, secret_ref, TLS, timeout et config | `200` liste / `201 Connector` | Lecture authentifiée; écriture `ADMIN/SUPERVISOR` | GET `401/403/429`; POST `400/401/403/429` |
| `GET`, `PUT`, `PATCH`, `DELETE /api/connectors/{id}/` | `ConnectorRequest`; le secret est une référence, jamais la valeur | `200 Connector` ou `204` | Lecture authentifiée; écriture `ADMIN/SUPERVISOR` | `400/401/403/404/429` |
| `POST /api/connectors/{id}/collect/` | Aucun | `202` tâche VMware ou Hyper-V | JWT, `ADMIN/SUPERVISOR` | `401/403/404/429` |
| `GET /api/assets/` | `page`, superuser `customer`, `kind=HOST/VM/DATASTORE`, `source=VMWARE/HYPERV` | `200` assets paginés | JWT, authentifié, lecture seule | `401/403/429` |
| `GET /api/assets/{id}/` | UUID | `200 VirtualAsset` | JWT, authentifié, lecture seule | `401/403/404/429` |
| `GET /api/vmware/overview/` | Aucun | `200` connecteurs, hosts, VMs, datastores, partial | JWT, authentifié | `401/403/429` |
| `GET /api/hyperv/overview/` | Aucun | `200` connecteurs, hosts, VMs, datastores, partial | JWT, authentifié | `401/403/429` |
| `GET /api/collection-runs/` | `page`, superuser `customer` | `200` collectes paginées | JWT, authentifié, lecture seule | `401/403/429` |
| `GET /api/collection-runs/{id}/` | ID entier | `200 CollectionRun` | JWT, authentifié, lecture seule | `401/403/404/429` |

Les overviews exposent uniquement les données réellement découvertes et
persistées. Aucun exemple Swagger ne fabrique de host, VM ou datastore.

### Notifications

| Méthode et URL | Paramètres / body | Réponse de succès | Permission | Erreurs documentées |
|---|---|---|---|---|
| `GET`, `POST /api/notifications/preferences/` | GET: `page`, superuser `customer`; POST: user, canal, destination, sévérité, cooldown | `200` liste / `201 Preference` | Lecture authentifiée; écriture `ADMIN/SUPERVISOR` | GET `401/403/429`; POST `400/401/403/429` |
| `GET`, `PUT`, `PATCH`, `DELETE /api/notifications/preferences/{id}/` | `NotificationPreferenceRequest` | `200 Preference` ou `204` | Lecture authentifiée; écriture `ADMIN/SUPERVISOR` | `400/401/403/404/429` |
| `GET /api/notifications/deliveries/` | `page`, superuser `customer` | `200` livraisons paginées | JWT, authentifié, lecture seule | `401/403/429` |
| `GET /api/notifications/deliveries/{id}/` | UUID | `200 NotificationDelivery` | JWT, authentifié, lecture seule | `401/403/404/429` |

### Temps réel, audit, tâches et rapports

| Méthode et URL | Paramètres / body | Réponse de succès | Permission | Erreurs documentées |
|---|---|---|---|---|
| `POST /api/realtime/ticket/` | Aucun | `200` ticket à usage unique, expiration 60 s | JWT, authentifié | `401/403/429` |
| `GET /api/realtime/replay/` | `since`, entier positif, défaut 0 | `200` jusqu'à 500 événements non paginés | JWT, authentifié | `400/401/403/429` |
| `GET /api/audit/` | `action`, `actor`, `target_type`, `target_id`, `ip_address`, `from`, `to`, `search`, `ordering`, `page`, `page_size`; superuser `customer` | `200` audit paginé | JWT, `ADMIN/SUPERVISOR`, lecture seule | `400/401/403/429` |
| `GET /api/audit/{id}/` | ID entier | `200 AuditLog` | JWT, `ADMIN/SUPERVISOR`, lecture seule | `401/403/404/429` |
| `GET /api/tasks/` | `page`, superuser `customer` | `200` tâches paginées | JWT, `ADMIN`, lecture seule | `401/403/429` |
| `GET /api/tasks/{id}/` | ID entier | `200 TaskRun` | JWT, `ADMIN`, lecture seule | `401/403/404/429` |
| `GET /api/reports/` | `page`, superuser `customer` | `200` rapports paginés | JWT, authentifié, lecture seule | `401/403/429` |
| `GET /api/reports/{id}/` | ID entier | `200 Report` | JWT, authentifié, lecture seule | `401/403/404/429` |
| `POST /api/reports/generate/` | kind, idempotency key optionnelle | `202` tâche planifiée | JWT, authentifié, client requis | `400/401/403/429` |

Le transport WebSocket lui-même est décrit dans `docs/REALTIME.md`; OpenAPI
documente les deux opérations HTTP nécessaires à sa sécurisation et au replay.

## Validation et export

Depuis PowerShell à la racine :

```powershell
. .\scripts\common.ps1
Import-DotEnv 'backend\.env'
$env:DATABASE_ENGINE = 'postgresql'
$env:CHANNEL_LAYER = 'memory'

.\.venv\Scripts\python.exe backend\manage.py check
.\.venv\Scripts\python.exe backend\manage.py spectacular `
  --validate --fail-on-warn --file schema.yml
.\.venv\Scripts\python.exe backend\manage.py test common.test_openapi -v 2
```

La suite `common.test_openapi` vérifie :

- l'accès à `/api/schema/` et `/api/docs/` et l'utilisation des assets locaux ;
- l'égalité exacte entre les 59 chemins, les 91 opérations documentées et les
  méthodes réellement acceptées par Django/DRF ;
- la présence systématique du contrat, des erreurs et des permissions ;
- JWT, session, token agent, paramètres, request bodies et statuts principaux ;
- le refus `405` de la création directe d'un modèle ML.

Le schéma exporté sert d'artefact de comparaison. Il n'est pas commité afin que
`/api/schema/` reste la source de vérité générée depuis le code courant.

Le 26 août 2026, la génération complète avec `--validate` a réussi, puis la suite
Django PostgreSQL/Redis a trouvé 191 tests : 188 réussis, 3 ignorés et aucun échec. La validation OpenAPI
prouve la cohérence des routes inspectées; elle ne remplace pas une recette des
services externes VMware, Hyper-V ou SMTP.

Voir aussi l'[index documentaire](README.md), les [métriques](METRICS.md),
l'[analyse prédictive](PREDICTIVE_ANALYSIS.md) et le [temps réel](REALTIME.md).
