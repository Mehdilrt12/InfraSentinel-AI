# Audit du contrat backend pour le frontend

**Projet :** InfraSentinel AI

**Date de vérification :** 30 août 2026

**Portée :** contrat HTTP/WebSocket réellement exposé par le backend courant
**Sources de vérité :** `backend/config/urls.py`, `backend/common/urls.py`, `backend/common/api.py`, sérialiseurs, permissions, modèles, tests et schéma OpenAPI généré.

## Résumé exécutif

Le backend expose actuellement **63 chemins HTTP et 95 opérations OpenAPI**. La commande suivante a validé le schéma sans erreur ni avertissement :

```powershell
docker compose exec -T api python manage.py spectacular --validate --file /tmp/frontend-backend-audit.yaml
```

Le frontend doit uniquement consommer les contrats décrits ici. Il ne doit pas inventer d'OTP, de route `/api/predictions/`, de CRUD autonome de recommandations, de métriques d'intégration ou de données de démonstration. Les prédictions sont disponibles uniquement par machine. Les recommandations structurées sont imbriquées dans les alertes.

Le backend applique une isolation multi-client côté serveur. Un objet appartenant à un autre client est normalement invisible et produit un `404`. Le superutilisateur plateforme peut traverser les clients et utiliser `?customer=<uuid>` sur les viewsets tenant compatibles.

## Authentification navigateur

Le flux recommandé pour React est le flux navigateur sécurisé :

1. `GET /api/auth/browser/csrf/` pose le cookie CSRF et renvoie `csrf_token`.
2. `POST /api/auth/browser/login/` avec `email`, `password` et `X-CSRFToken` renvoie l'access JWT en mémoire ; le refresh est posé dans un cookie HttpOnly.
3. Les appels métier utilisent `Authorization: Bearer <access>`.
4. Après un `401`, `POST /api/auth/browser/refresh/` effectue une rotation du refresh et renvoie un nouvel access.
5. `POST /api/auth/browser/logout/` révoque le refresh et supprime le cookie.

L'access JWT ne doit pas être placé dans `localStorage` ou `sessionStorage`. Le refresh est HttpOnly, `SameSite=Strict`, sécurisé hors mode debug. Durées actuelles : access 15 minutes, refresh 1 jour, rotation et blacklist activées.

| Méthode | Route | Auth | Corps | Réponse principale |
|---|---|---|---|---|
| GET | `/api/auth/browser/csrf/` | Public | — | `{csrf_token}` |
| POST | `/api/auth/browser/login/` | Public + CSRF, throttlé IP/compte | `{email,password}` | `{access,expires_in}` + cookie refresh |
| POST | `/api/auth/browser/refresh/` | Cookie refresh + CSRF | — | `{access,expires_in}` + rotation cookie |
| POST | `/api/auth/browser/logout/` | CSRF | — | `204` |
| POST | `/api/auth/token/` | Public, throttlé IP/compte | `{email,password}` | `{access,refresh}` |
| POST | `/api/auth/refresh/` | Refresh dans le corps | `{refresh}` | paire renouvelée |
| POST | `/api/auth/logout/` | Refresh dans le corps | `{refresh}` | `200` |
| POST | `/api/auth/register/` | Public seulement si activé | `{organization,email,password}` | IDs user/customer/environment |
| GET | `/api/auth/me/` | Principal actif | — | profil courant |

Fonctions **absentes** : OTP, MFA/2FA, vérification email, mot de passe oublié, réinitialisation de mot de passe et verrouillage durable. Aucune UI ne doit laisser croire qu'elles existent.

## Rôles et matrice RBAC

Rôles réellement présents : `ADMIN`, `SUPERVISOR`, `TECHNICIAN`, `CLIENT`, `VIEWER`, auxquels s'ajoute le drapeau plateforme `is_superuser`.

| Zone | Lecture | Mutation |
|---|---|---|
| Ressources tenant ordinaires | Tous les rôles actifs | `ADMIN`, `SUPERVISOR` |
| Utilisateurs | `ADMIN` | `ADMIN` |
| Client courant | `ADMIN` | Superutilisateur seulement |
| Audit | `ADMIN`, `SUPERVISOR` | Aucune |
| Tâches Celery | `ADMIN` | Aucune |
| Préférences notification | Tous | `ADMIN`, `SUPERVISOR` |
| Documentation API | Public si configuré, sinon `ADMIN` | Aucune |

`TECHNICIAN`, `CLIENT` et `VIEWER` sont actuellement équivalents en permissions API : lecture seule. Le frontend peut utiliser des libellés distincts, mais ne doit pas inventer des capacités distinctes.

## Conventions transversales

- Corps métier : JSON uniquement.
- Listes DRF : `{count,next,previous,results}`.
- Pagination globale : 100 éléments par page avec `page`; pas de `page_size` global.
- Audit : 50 par page, `page_size` autorisé jusqu'à 200.
- Throttling global : utilisateur 2 000/h, anonyme 100/h, avec quotas plus stricts sur auth et agent.
- Erreurs habituelles : `400` validation, `401` non authentifié/token invalide, `403` permission/tenant inactif, `404` absent ou hors tenant, `405` méthode interdite, `429` quota.
- Les listes n'offrent pas toutes recherche, tri ou filtres. Le frontend doit filtrer localement seulement ce qu'il a réellement chargé et l'indiquer clairement.

## Inventaire complet par domaine

### Santé et dashboard

| Opération | Permission | Réponse/limites |
|---|---|---|
| `GET /api/health/` | Public | `status`, version, heure, état PostgreSQL/Redis ; ne valide pas workers, Beat, SMTP ou connecteurs |
| `GET /api/dashboard/` | Tous rôles actifs | `total_assets`, `online`, `offline`, `critical`, `warning`, `anomalies`, `vmware_hosts`, `hyperv_hosts`, `active_alerts` |

`total_assets` compte actuellement les machines et non tous les `VirtualAsset`. `anomalies` compte tout l'historique. L'activité et les séries du dashboard nécessitent des appels séparés à Metrics, Alerts et Anomalies.

### Clients et utilisateurs

| Opération | Permission | Contrat |
|---|---|---|
| `GET /api/customers/`, `GET /api/customers/{id}/` | `ADMIN` | Client courant ; tous les clients pour superuser |
| `POST/PUT/PATCH/DELETE /api/customers[/id]/` | Superuser | `name`, `slug`, `active` |
| `GET/POST /api/users/` | `ADMIN` | Liste/création tenant |
| `GET/PUT/PATCH/DELETE /api/users/{id}/` | `ADMIN` | Consultation et gestion tenant |

User expose `id`, email, username, nom, prénom, rôle, client, actif et superuser. Le mot de passe est write-only et validé par Django. Aucun filtre/recherche/tri API n'est fourni. Un admin peut actuellement se rétrograder, se désactiver ou se supprimer : l'UI doit prévenir explicitement, sans prétendre empêcher un appel direct.

### Environnements, machines et prédictions

| Opération | Permission | Filtres/corps |
|---|---|---|
| CRUD `/api/environments/` et `/{id}/` | Lecture tous ; mutation managers | Type, nom et configuration d'environnement |
| `POST /api/environments/{id}/enrollment_code/` | Managers | `{ttl_minutes:1..1440}` → code affiché une seule fois |
| CRUD `/api/machines/` et `/{id}/` | Lecture tous ; mutation managers | `environment`, source, external ID, hostname, IP, OS, état, version, metadata |
| `GET /api/machines/{id}/trends/?hours=N` | Tous | `N=1..720`; tableau non paginé de tendances |

La liste machines n'a aucun filtre serveur par statut, source, environnement ou recherche. Une prédiction expose métrique/unité, échantillons, fenêtre, dernière valeur, moyenne, variation/h, tendance, risque, règle/seuil, franchissement estimé, confiance et disclaimer. Il n'existe **pas** de route `/api/predictions/`.

### Agents Windows

| Opération | Permission | Contrat |
|---|---|---|
| `GET /api/agents/`, `GET /api/agents/{id}/` | Tous | Lecture paginée |
| `PATCH /api/agents/{id}/` | Managers | `enabled`, `version` |
| `POST /api/agent/enroll/` | Code d'enrôlement, public throttlé | Identité machine → IDs + token opaque retourné une fois |
| `POST /api/agent/heartbeat/` | Token agent | Version optionnelle → statut/heure |
| `POST /api/agent/metrics/` | Token agent | Batch 1..5 000, clé d'idempotence → `{accepted}` |

Le token est hashé en base. L'agent ne peut écrire que pour sa machine. Il n'existe pas d'action distincte `rotate`/`revoke`; la révocation passe par `PATCH enabled=false`. La liste Agent ne contient pas l'état/IP de la machine : l'UI doit joindre les machines.

### Métriques et agrégats

| Opération | Permission | Filtres |
|---|---|---|
| `GET /api/metrics/`, `GET /api/metrics/{id}/` | Tous | `machine`, `metric_name`, `source_type` |
| `GET /api/metric-aggregates/`, `GET /api/metric-aggregates/{id}/` | Tous | Aucun filtre métier disponible |

Ces ressources sont read-only. Une métrique normalisée expose timestamp, environnement, machine, type de source, nom canonique, valeur, unité, état, metadata et date de réception. Limites structurantes : aucun filtre temporel, aucun multi-metric, aucun tri ou bucket configurable ; une page ne contient que 100 points. Les agrégats ne contiennent pas d'unité ni de source et ne peuvent pas être filtrés par machine/métrique.

### Règles

| Opération | Permission | Contrat |
|---|---|---|
| CRUD `/api/rules/`, `/{id}/` | Lecture tous ; mutation managers | nom, métrique, opérateur, seuil, durée, sévérité, scopes, cooldown, actif |
| `POST /api/rules/{id}/toggle/` | Managers | Inverse `enabled` |

Opérateurs : `>`, `<`, `>=`, `<=`, `==`, `!=`. Aucun filtre de liste, endpoint de simulation ou validation d'unité/métrique n'est disponible.

### Alertes et recommandations

| Opération | Permission | Filtres/corps |
|---|---|---|
| `GET /api/alerts/`, `GET /api/alerts/{id}/` | Tous | `status`, `machine` |
| `PATCH /api/alerts/{id}/` | Managers | `status` |

États : `NEW`, `ACKNOWLEDGED`, `IN_PROGRESS`, `RESOLVED`. La réponse inclut identifiant, machine/hostname, timestamps, type, sévérité, source, message, contexte, score anomalie, statut, occurrences, escalade et recommandation structurée.

Il n'existe pas de CRUD `/api/recommendations/`. `structured_recommendation` est imbriquée et contient diagnostic, actions, justification et `destructive=false`. Les paramètres severity/type/source/date/search ne sont pas implémentés côté backend, même si une ancienne documentation suggère `severity`.

### Anomalies

| Opération | Permission | Filtres/corps |
|---|---|---|
| `GET /api/anomalies/`, `GET /api/anomalies/{id}/` | Tous | `machine` |
| `PATCH /api/anomalies/{id}/` | Managers | `acknowledged` seulement |

Réponse : machine/hostname, métrique, détection/fenêtre, score, seuil, version modèle, explication, acquittement. Aucun filtre par acquittement, modèle, score ou date.

### Machine Learning

| Opération | Permission | Contrat |
|---|---|---|
| `GET /api/ml/models/`, `GET /api/ml/models/{id}/` | Tous | Versions réelles, artifact path masqué |
| `PATCH /api/ml/models/{id}/` | Managers | Présent mais actuellement sans champ writable effectif |
| `POST /api/ml/models/train/` | Managers | `{days:1..3650,idempotency_key?}` → `202 {task_id,status}` |
| `POST /api/ml/models/evaluate/` | Managers | Même enveloppe asynchrone |

Isolation Forest réelle : 200 estimateurs, contamination 0,02, random state 42, RobustScaler, split chronologique et au moins 200 fenêtres. Les données demo/synthetic/controlled sont exclues de l'entraînement normal. L'évaluation actuelle mesure le chevauchement alertes/anomalies ; sans labels, précision et rappel restent `null`. Le frontend doit présenter cela sans revendiquer une validation supervisée.

### VMware et Hyper-V

| Opération | Permission | Contrat |
|---|---|---|
| CRUD `/api/connectors/`, `/{id}/` | Lecture tous ; mutation managers | VMware/Hyper-V, endpoint, username, `secret_ref`, TLS, timeout, config |
| `POST /api/connectors/{id}/collect/` | Managers | `202 {task_id,status}` |
| `GET /api/assets/`, `GET /api/assets/{id}/` | Tous | filtres `kind=HOST|VM|DATASTORE`, `source=VMWARE|HYPERV` |
| `GET /api/collection-runs/`, `GET /api/collection-runs/{id}/` | Tous | historique paginé |
| `GET /api/vmware/overview/` | Tous | connecteurs, hosts, VMs, datastores, partial |
| `GET /api/hyperv/overview/` | Tous | connecteurs, hosts, VMs, partial |

Les collecteurs utilisent réellement pyVmomi et PowerShell/CIM/WMI. Les données d'une infrastructure externe n'ont pas été validées pendant cet audit : **NOT TESTED — environnement réel requis**. Les pages doivent afficher l'absence de configuration ou l'état partiel, jamais générer de hosts/VMs fictifs. Hyper-V nécessite un worker Windows consommant la queue `hyperv`; le worker Docker Linux courant ne le remplace pas.

### Notifications

| Opération | Permission | Contrat |
|---|---|---|
| CRUD `/api/notifications/preferences/`, `/{id}/` | Lecture tous ; mutation managers | user, channel, destination, sévérité min., actif, cooldown |
| `GET /api/notifications/deliveries/`, `/{id}/` | Tous | Livraisons read-only, tentatives, dates, état, erreur publique |

Email est le seul canal avec un adaptateur implémenté. Une livraison SMTP externe nécessite une configuration et un test de bout en bout séparés ; elle n'est pas prouvée par cet audit frontend. Teams, Slack et Telegram sont réservés dans le modèle mais non implémentés. Aucun filtre deliveries par canal/statut/date. La destination email n'est pas un `EmailField` côté API ; l'UI doit la valider, tout en considérant le serveur comme autorité.

### Audit, tâches et rapports

| Opération | Permission | Contrat |
|---|---|---|
| `GET /api/audit/`, `GET /api/audit/{id}/` | `ADMIN`, `SUPERVISOR` | Read-only, immuable |
| `GET /api/tasks/`, `GET /api/tasks/{id}/` | `ADMIN` | État Celery read-only |
| `GET /api/reports/`, `GET /api/reports/{id}/` | Tous | Rapports tenant read-only |
| `POST /api/reports/generate/` | Tous | `{kind,idempotency_key?}` → `202` |

Audit accepte `action`, `actor`, `target_type`, `target_id`, `ip_address`, `from`, `to`, `search`, `ordering`, `page`, `page_size`. Les autres listes ci-dessus n'ont pas de filtres métiers. Attention : le `task_id` renvoyé par Celery n'est pas la clé numérique utilisée dans `/api/tasks/{id}/`; il n'existe pas de suivi REST direct par ID Celery.

## Temps réel

Flux réel :

1. `POST /api/realtime/ticket/` avec JWT/session → ticket signé à usage unique, valable 60 s.
2. Connexion `ws[s]://<host>/ws/events/?ticket=<ticket>&since=<sequence>`.
3. En cas de trou ou d'indisponibilité : `GET /api/realtime/replay/?since=<sequence>`.

Événements produits :

- `machine.online`
- `machine.offline`
- `metric.update`
- `alert.created`
- `alert.updated`
- `anomaly.detected`

Enveloppe :

```json
{
  "sequence": 123,
  "event_type": "alert.created",
  "aggregate_id": "uuid",
  "payload": {},
  "created_at": "2026-08-30T20:00:00Z"
}
```

Le replay renvoie au maximum 500 événements. Le client doit dédupliquer par `sequence`, persister seulement la dernière séquence non sensible, reboucler le replay si nécessaire, rafraîchir les queries concernées et conserver un polling de secours. `metric.update` représente actuellement seulement la dernière métrique d'un batch avec le nombre `accepted`, pas chaque mesure.

## États UI obligatoires dérivés du contrat

Chaque page de données doit distinguer :

- chargement initial ;
- aucune donnée réelle ;
- erreur HTTP avec action de réessai ;
- accès interdit ;
- session expirée ;
- données partielles (`partial`, requête secondaire en erreur, WS indisponible) ;
- mode temps réel connecté, reconnexion ou fallback polling ;
- action asynchrone mise en file, sans prétendre qu'elle a terminé.

## Écarts backend à ne pas masquer

1. Les données analytiques longues sont contraintes par la pagination et l'absence de filtres temporels.
2. Ingestion métrique et heartbeat peuvent laisser une alerte offline ouverte dans un ordre précis.
3. Les listes Alerts, Anomalies, Rules, Agents et Notifications ont peu de filtres serveur.
4. `PATCH` ML est exposé mais sans mutation effective.
5. Évaluation ML non supervisée : aucune précision/rappel sans labels.
6. Suivi d'une tâche par ID Celery absent.
7. Intégrations réelles non vérifiées dans cet environnement.
8. La documentation OpenAPI Customer annonce encore imparfaitement la différence admin tenant/superuser.
9. Les rôles lecture seule ne sont pas fonctionnellement différenciés.
10. Aucune rétention des événements temps réel n'a été identifiée.

## Décisions frontend issues de l'audit

- Base API relative `/api` par défaut et configurable par `VITE_API_BASE_URL`.
- Access JWT uniquement en mémoire ; refresh cookie HttpOnly.
- Query cache vidé au logout et au changement d'identité.
- Matrice des routes/actions centralisée sur les permissions réelles.
- Adaptateurs de réponse paginée centralisés.
- Aucune donnée mock/fake/demo dans le bundle de production.
- Prédictions chargées par `/machines/{id}/trends/`.
- Recommandations rendues depuis l'alerte.
- Rapports consommés depuis `/reports/` et générés via `/reports/generate/`, sans inventer de téléchargement d'artefact.
- Une seule connexion WebSocket partagée, replay/déduplication/backoff et polling de secours.
- Les tableaux montrent les filtres serveur réellement supportés ; une recherche locale est explicitement limitée aux lignes chargées.
- VMware/Hyper-V affichent `non configuré`, `partiel` ou erreur réelle, jamais un succès déduit de zéro asset.

## Verdict du contrat backend

**PASS avec réserves documentées pour l'intégration frontend reconstruite.** Le contrat principal est authentifié, multi-tenant, documenté automatiquement et suffisamment stable pour le dashboard livré. Les limites analytiques, RBAC et intégrations externes ci-dessus restent visibles et ne sont pas compensées par des données inventées.
