# Intégration frontend — API et WebSocket

## 1. Source de vérité

Cette documentation décrit les appels réellement effectués par `frontend/src`. Le contrat backend complet a été vérifié séparément dans `docs/FRONTEND_BACKEND_API_AUDIT.md`. Le frontend ne reconstruit pas de ressources absentes du schéma.

## 2. Configuration du transport

`src/api/client.ts` choisit la base dans cet ordre :

1. `VITE_API_BASE_URL` ;
2. `VITE_API_URL` ;
3. `/api`.

Le slash final est supprimé. Les clients Axios envoient du JSON, acceptent du JSON, incluent les cookies (`withCredentials`) et expirent après 15 secondes.

En production Docker, `/api` est relayé par Nginx vers `api:8000`. En développement séparé, l'URL peut être absolue, à condition que Django autorise exactement l'origine frontend.

## 3. Authentification navigateur

| Étape                      | Requête frontend              | Donnée conservée côté navigateur                             |
| -------------------------- | ----------------------------- | ------------------------------------------------------------ |
| Initialisation CSRF        | `GET /auth/browser/csrf/`     | Jeton CSRF en mémoire et cookie serveur.                     |
| Connexion                  | `POST /auth/browser/login/`   | Access JWT en mémoire ; refresh HttpOnly inaccessible au JS. |
| Profil                     | `GET /auth/me/`               | Objet `User` dans le contexte React.                         |
| Renouvellement             | `POST /auth/browser/refresh/` | Nouvel access en mémoire ; refresh roté par le serveur.      |
| Déconnexion                | `POST /auth/browser/logout/`  | Aucun jeton ; cache et séquence temps réel purgés.           |
| Inscription conditionnelle | `POST /auth/register/`        | Aucun secret persistant ; connexion ensuite.                 |

L'intercepteur ajoute `Authorization: Bearer …` aux appels métier. À la première réponse `401`, il lance une seule rotation partagée, rejoue la requête une fois, puis marque la session expirée si la rotation échoue. Les routes d'authentification ne sont pas prises dans une boucle de refresh.

Les appels de refresh et logout comportent `X-CSRFToken`. Aucun JWT n'est écrit dans Web Storage.

## 4. Conventions de données

- Listes : `{count, next, previous, results}`. Le helper `asPage` tolère aussi une liste brute pour les contrats non paginés.
- Pagination ordinaire : `page`, 100 objets par page côté backend.
- Audit : `page_size=50` envoyé par la page, maximum backend 200.
- Erreurs : `apiProblem` convertit les erreurs Axios en `status`, `title`, `detail` et erreurs de champs.
- Codes attendus : `400`, `401`, `403`, `404`, `405`, `429` et erreurs réseau.
- Multi-tenant : aucun identifiant de client n'est déduit côté frontend. Django filtre les querysets et doit retourner `404` pour un objet hors tenant.

## 5. Endpoints consommés par page

### Session et shell

| Méthode | Route                       | Usage                                                                 |
| ------- | --------------------------- | --------------------------------------------------------------------- |
| GET     | `/auth/browser/csrf/`       | Initialiser le CSRF.                                                  |
| POST    | `/auth/browser/login/`      | Ouvrir une session navigateur.                                        |
| POST    | `/auth/browser/refresh/`    | Rotation après bootstrap ou `401`.                                    |
| POST    | `/auth/browser/logout/`     | Révoquer le refresh.                                                  |
| GET     | `/auth/me/`                 | Charger le profil et le rôle.                                         |
| POST    | `/auth/register/`           | Inscription si les deux configurations frontend/backend l'autorisent. |
| POST    | `/realtime/ticket/`         | Obtenir un ticket à usage unique.                                     |
| GET     | `/realtime/replay/?since=N` | Rattraper les événements manqués.                                     |

### Dashboard

| Méthode | Route                             | Usage/limite                               |
| ------- | --------------------------------- | ------------------------------------------ |
| GET     | `/dashboard/`                     | KPIs consolidés.                           |
| GET     | `/machines/?page=1`               | Inventaire partiel et scope des tendances. |
| GET     | `/metrics/?page=1`                | Activité récente, 100 points maximum.      |
| GET     | `/alerts/?page=1`                 | Priorités actives de la page.              |
| GET     | `/anomalies/?page=1`              | État secondaire et compteur chargé.        |
| GET     | `/machines/{id}/trends/?hours=24` | Risques de huit machines au maximum.       |

### Machines

| Méthode          | Route                                     | Usage                                    |
| ---------------- | ----------------------------------------- | ---------------------------------------- |
| GET/POST         | `/machines/`                              | Liste et création manager.               |
| GET/PATCH/DELETE | `/machines/{id}/`                         | Dossier, édition et suppression manager. |
| GET              | `/environments/` et `/environments/{id}/` | Libellés et formulaire.                  |
| GET              | `/metrics/?machine={id}&page=1`           | Dernières mesures et graphiques.         |
| GET              | `/alerts/?machine={id}&page=1`            | Incidents liés.                          |
| GET              | `/anomalies/?machine={id}&page=1`         | Anomalies liées.                         |
| GET              | `/machines/{id}/trends/?hours=24`         | Tendances et risques.                    |
| GET              | `/agents/`                                | Jointure locale agent/machine.           |

Le backend ne filtre pas la liste machine par texte, statut ou source. L'interface précise que ces filtres s'appliquent à la page chargée.

### Agents Windows

| Méthode | Route                                 | Usage                                                          |
| ------- | ------------------------------------- | -------------------------------------------------------------- |
| GET     | `/agents/?page=N`                     | Liste des identités agent.                                     |
| PATCH   | `/agents/{id}/`                       | Basculer `enabled` et donc accepter/refuser le token existant. |
| GET     | `/machines/`                          | Joindre état, IP et source.                                    |
| GET     | `/environments/`                      | Sélectionner un environnement Windows/Mixte.                   |
| POST    | `/environments/{id}/enrollment_code/` | Générer un secret temporaire affiché une fois.                 |

Les routes publiques agent `/agent/enroll/`, `/agent/heartbeat/` et `/agent/metrics/` sont destinées à l'agent Windows, pas au dashboard.

### Alertes, anomalies et recommandations

| Méthode   | Route                      | Usage                                                                              |
| --------- | -------------------------- | ---------------------------------------------------------------------------------- |
| GET       | `/alerts/?page=N&status=…` | Liste ; `status` et `machine` sont les seuls filtres métier utilisés côté serveur. |
| GET/PATCH | `/alerts/{id}/`            | Détail et changement de cycle de vie.                                              |
| GET       | `/anomalies/?page=N`       | Liste des anomalies.                                                               |
| PATCH     | `/anomalies/{id}/`         | Basculer `acknowledged`.                                                           |
| GET       | `/machines/`               | Résoudre les noms dans les pages de liste.                                         |

La sévérité et la recherche d'alertes sont locales à la page chargée. Les recommandations sont lues dans `recommendation` et `structured_recommendation` de l'alerte. Il n'existe aucun appel `/recommendations/`.

### Prédictions et ML

| Méthode | Route                            | Usage                                        |
| ------- | -------------------------------- | -------------------------------------------- |
| GET     | `/machines/?page=N`              | Page DRF fixe de 100 machines, découpée en lots UI de 20. |
| GET     | `/machines/{id}/trends/?hours=N` | Estimations temporelles avec `N` parmi 6, 24, 72, 168 ou 720. |
| GET     | `/ml/models/`                    | Versions, paramètres, dataset et évaluation. |
| POST    | `/ml/models/train/`              | Planifier l'entraînement Celery.             |
| POST    | `/ml/models/evaluate/`           | Planifier l'évaluation Celery.               |
| GET     | `/anomalies/`                    | Anomalies associées au modèle.               |
| GET     | `/tasks/`                        | Journal admin des exécutions persistées.     |

La pagination prédictive ne transmet pas de faux `page_size=20` : les pages UI 1 à 5 découpent la page DRF 1, les pages UI 6 à 10 la page DRF 2, etc. Le fan-out est ainsi limité à 20 appels de tendances simultanés sans rendre les machines 21 à 100 inaccessibles. Le corps des actions ML contient `days` et une `idempotency_key` générée pour l'action UI. Le `task_id` Celery retourné n'est pas utilisable dans `/tasks/{id}/`, qui attend une clé numérique persistée. Il n'existe pas de `/predictions/` global.

### VMware et Hyper-V

| Méthode | Route                       | Usage                                                  |
| ------- | --------------------------- | ------------------------------------------------------ |
| GET     | `/vmware/overview/`         | Connecteurs, hosts, VMs, datastores et état `partial`. |
| GET     | `/hyperv/overview/`         | Connecteurs, hosts, VMs et état `partial`.             |
| GET     | `/collection-runs/`         | Historique de collecte affiché par source.             |
| GET     | `/machines/`                | Correspondance asset/machine.                          |
| POST    | `/connectors/{id}/collect/` | Planifier une collecte réelle.                         |
| GET     | `/machines/{id}/`           | Ouvrir la machine normalisée liée à un asset.          |

Les pages ne génèrent pas d'assets de démonstration. Le statut `partial`, l'absence de connecteur ou l'absence d'asset sont présentés tels quels. Une infrastructure VMware/Hyper-V externe reste nécessaire pour valider le collecteur réel de bout en bout.

### Utilisateurs et audit

| Méthode      | Route          | Usage                                          |
| ------------ | -------------- | ---------------------------------------------- |
| GET/POST     | `/users/`      | Liste/création par administrateur.             |
| PATCH/DELETE | `/users/{id}/` | Modification/suppression avec confirmation UI. |
| GET          | `/audit/`      | Liste immuable filtrée et paginée.             |

La page audit envoie les filtres non vides parmi `action`, `actor`, `target_type`, `target_id`, `ip_address`, `from`, `to`, `search`, `ordering`, `page` et `page_size`. Les dates saisies représentent le début ou la fin de la journée locale choisie, puis sont converties en ISO UTC ; la borne `to` inclut donc toute la journée. Le frontend n'offre aucune mutation d'audit.

### Rapports

| Méthode | Route                | Usage/limite                                                           |
| ------- | -------------------- | ---------------------------------------------------------------------- |
| GET     | `/reports/?page=N`   | Historique paginé des rapports persistés du tenant.                    |
| POST    | `/reports/generate/` | Planifier une synthèse réelle avec `kind` et une clé d'idempotence UI. |

Après le `202`, la page affiche la mise en file et rafraîchit la liste pendant au plus deux minutes. Le `task_id` Celery retourné n'est ni une clé de `/tasks/{id}/` ni relié au rapport créé ; l'interface n'attribue donc pas un nouveau rapport à cette tâche en cas de concurrence. `artifact_path` signale uniquement un stockage serveur : aucun lien n'est construit, car le backend n'expose pas d'endpoint authentifié de téléchargement.

### Configuration

| Ressource         | Appels                                                                                  |
| ----------------- | --------------------------------------------------------------------------------------- |
| Règles            | GET/POST `/rules/`, PATCH/DELETE `/rules/{id}/`, POST `/rules/{id}/toggle/`             |
| Préférences       | GET/POST `/notifications/preferences/`, PATCH/DELETE `/notifications/preferences/{id}/` |
| Livraisons        | GET `/notifications/deliveries/` uniquement                                             |
| Environnements    | GET/POST `/environments/`, PATCH/DELETE `/environments/{id}/`                           |
| Connecteurs       | GET/POST `/connectors/`, PATCH/DELETE `/connectors/{id}/`                               |
| Machines de scope | GET `/machines/`                                                                        |

Le formulaire connecteur envoie `secret_ref`, jamais le mot de passe lui-même. En édition, un champ secret vide est omis et les objets backend `config`/`metadata` non édités ne sont pas remplacés par `{}`. Le champ secret n'est renvoyé ni conservé par l'interface. La notification créée par l'UI utilise actuellement le canal `EMAIL`, seul adaptateur fonctionnel.

## 6. WebSocket

L'URL est `VITE_WS_URL` si elle existe. Sinon elle est dérivée de l'origine en remplaçant HTTP par WS et en utilisant `/ws/events/`. L'image Nginx finale applique `connect-src 'self'` : le proxy même origine `/ws` est la configuration de production recommandée ; une URL WebSocket externe demande une CSP dédiée au déploiement.

```text
POST /api/realtime/ticket/
GET  /api/realtime/replay/?since=<sequence>
WS   /ws/events/?ticket=<ticket>&since=<sequence>
```

Événements pris en charge :

- `machine.online` ;
- `machine.offline` ;
- `metric.update` ;
- `alert.created` ;
- `alert.updated` ;
- `anomaly.detected`.

La déduplication utilise `sequence`. La dernière séquence est stockée sous `infrasentinel.realtime.<tenant>.sequence`. Le cache métier est invalidé ; l'événement n'est pas interprété comme une nouvelle source de vérité complète.

En cas de socket indisponible, le client :

- passe visiblement en mode polling/offline ;
- rejoue les événements disponibles ;
- invalide dashboard, machines, alertes et anomalies toutes les 30 secondes par défaut ;
- retente la connexion avec backoff et jitter.

## 7. Mapping des erreurs vers l'interface

| Situation                    | Comportement                                                         |
| ---------------------------- | -------------------------------------------------------------------- |
| `400`                        | Message de validation et, si fourni, erreurs de champs.              |
| `401`                        | Une rotation silencieuse, puis retour login si échec.                |
| `403`                        | Mutation refusée ou redirection `/forbidden` pour une page protégée. |
| `404`                        | État introuvable ; peut aussi signifier objet hors tenant.           |
| `429`                        | Erreur API visible ; aucune boucle de retry Query.                   |
| Réseau/timeout               | État erreur avec réessai ; temps réel bascule en mode résilient.     |
| Requête secondaire en erreur | `PartialState` si la vue principale reste exploitable.               |

## 8. Invariants de sécurité

- ne jamais ajouter un stockage persistant de JWT ;
- ne jamais placer un ticket WebSocket ou code d'enrôlement dans les logs ;
- ne jamais exposer de secret de connecteur dans une variable `VITE_*` ;
- ne jamais considérer le masquage d'un bouton comme une autorisation ;
- ne pas transformer un `404` en indication de l'existence d'un objet hors tenant ;
- purger le Query Cache lorsqu'une identité disparaît ;
- garder HTTP et WebSocket sous HTTPS/WSS en production.

## 9. Limites contractuelles affichées honnêtement

- L'historique métrique est limité à la page réelle disponible et n'est pas un agrégat arbitraire.
- Les filtres locaux ne couvrent pas les objets non chargés.
- Les tendances sont des estimations et conservent le disclaimer backend.
- L'évaluation ML n'invente ni précision ni rappel lorsque les labels sont absents.
- Une tâche « mise en file » n'est pas présentée comme terminée.
- Un chemin d'artefact de rapport n'est jamais présenté comme une URL de téléchargement.
- L'adaptateur Email est implémenté, mais la livraison SMTP de bout en bout n'a pas été vérifiée par la suite frontend ; les autres canaux restent non implémentés.
- Une page VMware/Hyper-V vide n'est pas remplacée par un scénario fictif.
