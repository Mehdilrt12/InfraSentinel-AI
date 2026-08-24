# Revue stricte de la reconstruction — phases 0 à 17

Date de revue : 24 août 2026

Version applicative : `2.0.0`

Périmètre : phases 0 à 17 uniquement; aucune phase 18 n'a été commencée.

## 1. Executive Summary

La reconstruction forme maintenant une plateforme cohérente et exécutable : API
Django/DRF/Channels, PostgreSQL de référence, Redis/Celery, dashboard React/Vite,
agent Windows, collecteurs VMware/Hyper-V, normalisation, règles, alertes,
Isolation Forest, recommandations, temps réel et notifications email.

L'audit initial a néanmoins trouvé des défauts importants : référence de secret
connecteur trop permissive, fuite inter-client des `TaskRun`, idempotence globale
des tâches et métriques, double envoi possible de notification, verrou PostgreSQL
invalide, queue Hyper-V consommable sous Linux, unités réseau incompatibles,
états de règle non dimensionnés, assets VMware incomplets, stockage ML non partagé,
évaluation/prédiction seulement déclarées et plusieurs écarts code/documentation.
Ces défauts ont été corrigés dans le périmètre 0–17.

La preuve interne finale est positive : 48 tests backend sur PostgreSQL, 45 tests
backend sur SQLite avec 3 scénarios PostgreSQL explicitement ignorés, 8 tests agent,
10 tests frontend, lint/build/audit des dépendances, migration depuis une base
PostgreSQL 17 vide, parcours HTTP/agent/WebSocket réel et exécution via Redis/Celery.
La couverture backend mesurée est de 61 %.

Les limites externes restent explicites : aucun vCenter n'était disponible, Hyper-V
a refusé `Get-VM` faute de permissions, et aucun relais SMTP externe n'était
configuré. Les mocks correspondants ne sont pas comptés comme validation réelle.

## 2. Git Recovery Assessment

### État observé avant correction

- Branche : `main`.
- Aucun commit, remote, reflog ou branche d'origine récupérable.
- 154 fichiers reconstruits non suivis.
- L'identifiant historique mentionné `845f8d7` n'était pas résolvable.
- `git fsck` a retrouvé l'arbre orphelin
  `66c15d7b1b0592ca02f91328761e702e5d6bd080`.
- Le hash de chacun des 154 fichiers de cet arbre correspondait exactement à la
  copie de travail reconstruite.

### Action et conclusion

L'arbre vérifié a été rattaché à `main` dans le commit local `b3ed951`
(`Baseline reconstruite avant revue stricte phases 0-17`). Les réparations sont
conservées dans un second commit de revue. Aucun secret `.env` n'a été inventé ou
versionné.

Git recovery : **PARTIAL**. La baseline reconstruite est désormais traçable, mais
l'historique GitHub d'origine, ses migrations successives et la preuve d'absence de
régression par comparaison de commits sont irrécupérables depuis ce dépôt local.

## 3. Architecture actuelle

```text
                              Utilisateurs
                                  |
                         React 19 / Vite 6
                                  |
                     JWT HTTP + WebSocket ticket
                                  |
                      Django 6 / DRF / Daphne
                                  |
           +----------------------+----------------------+
           |                      |                      |
      Inventory/API         NormalizedMetric        RealtimeEvent
           |                      |                      |
  +--------+--------+       +-----+------+          Channels/Redis
  |        |        |       |            |               |
Windows  VMware  Hyper-V   Rules    IsolationForest   Dashboard
Agent   pyVmomi PowerShell   |            |          + polling fallback
  |        |        |       +------v-----+
  +--------+--------+          Alert/Recommendation
           |                         |
           +---- PostgreSQL 17 ------+---- NotificationEvent/Delivery
                                             |
                                      Celery -> business service
                                             |
                                            Email

Celery Beat -> rules, ML inference, VMware, Hyper-V, notifications, agrégats
Linux worker -> queue celery
Windows worker -> queues celery + hyperv (PowerShell/module/droits requis)
```

Responsabilités réelles :

- `accounts` : customers, utilisateurs, RBAC.
- `inventory` : environnements, machines, agents, enrollment, connecteurs, assets.
- `metrics` : contrat normalisé, ingestion et agrégats.
- `monitoring` : règles, états temporels, alertes, anomalies, recommandations, audit.
- `ml_engine` : dataset, training, holdout, registry, inference, évaluation et tendance.
- `integrations` : orchestration/persistance VMware et Hyper-V.
- `notifications` : préférences, événements durables, livraisons et service d'envoi.
- `realtime` : événement durable, ticket court, replay et groupes tenant.
- `async_tasks` : idempotence tenant, suivi Celery et rapports.

## 4. Phase Matrix

| Phase | Status | Code | Tests | Integration | Notes |
| ----- | ------ | ---- | ----- | ----------- | ----- |
| 0 | PARTIAL | PASS | PASS | PARTIAL | Baseline fiable créée; historique GitHub original absent. |
| 1 | PASS | PASS | PASS | PASS | Responsabilités séparées; dépendances backend mortes retirées. |
| 2 | PASS | PASS | PASS | PASS | PostgreSQL principal; migrations et bootstrap vide vérifiés. |
| 3 | PASS | PASS | PASS | PASS | URLs configurables, multi-source/tenant, trois agents concurrents validés. |
| 4 | PARTIAL | PASS | PASS | NOT TESTED | Agent, spool, reprise et API vérifiés; installation Windows Service non exécutée en Administrateur. |
| 5 | PARTIAL | PASS | PASS | NOT TESTED | Implémentation pyVmomi réelle et mocks; aucun vCenter disponible. |
| 6 | PARTIAL | PASS | PASS | NOT TESTED | PowerShell réel et mocks; accès local Hyper-V refusé par permissions. |
| 7 | PASS | PASS | PASS | PASS | Modèle commun, unités canonisées, métadonnées spécifiques conservées. |
| 8 | PASS | PASS | PASS | PASS | Règles CRUD, durée, scope et dimensions; retraitement évité. |
| 9 | PASS | PASS | PASS | PASS | Cycle, déduplication, résolution et concurrence PostgreSQL vérifiés. |
| 10 | PASS | PASS | PASS | PASS | Isolation Forest reproductible, artifact partagé, version active unique. |
| 11 | PARTIAL | PASS | PASS | NOT TESTED | Holdout et comparaison rules/ML/hybrid réels; aucun label opérationnel réel. |
| 12 | PARTIAL | PASS | PASS | NOT TESTED | Rolling average/pente/risque implémentés; aucune série applicative réelle disponible. |
| 13 | PASS | PASS | PASS | PASS | Recommandations contextuelles et non destructives, y compris hosts virtuels. |
| 14 | PASS | PASS | PASS | PASS | Toutes les routes, états de données, lazy loading, build et HTTP 200. |
| 15 | PASS | PASS | PASS | PASS | WebSocket 101, replay, multi-client, reconnexion et polling fallback. |
| 16 | PARTIAL | PASS | PASS | NOT TESTED | Email interne, anti-spam/retry/recovery/concurrence; SMTP externe absent. |
| 17 | PASS | PASS | PASS | PASS | Redis, worker, Beat, discovery, queues, tâche réelle, retry/idempotence. |

Les statuts PARTIAL/NOT TESTED proviennent de preuves externes indisponibles, pas
d'un mock reclassé abusivement en intégration réelle.

## 5. Dependency Chain

```text
Phase 0 baseline traçable
  -> Phase 1 modules cohérents
  -> Phase 2 PostgreSQL et contraintes
  -> Phase 3 identité tenant/source
  -> Phase 4 agent centralisé
  -> Phases 5/6 collecteurs virtualisation
  -> Phase 7 métrique normalisée
  -> Phase 8 état de règle durable
  -> Phase 9 alerte corrélée
  -> Phase 10 pipeline ML versionné
  -> Phase 11 évaluation sans métrique inventée
  -> Phase 12 estimation temporelle explicitement incertaine
  -> Phase 13 recommandation contextualisée
  -> Phase 14 dashboard complet
  -> Phase 15 événement temps réel + replay/polling
  -> Phase 16 notification durable
  -> Phase 17 tâche Celery mince -> service métier -> PostgreSQL
```

Problèmes de chaîne réparés : anciennes unités VMware/H-V, statut de VM écrasé par
l'ingestion, datastores non persistés, règles mélangeant services/volumes, mesures
rejouées par Beat, artifact ML local au worker, prédiction absente du dashboard,
curseur WebSocket non tenant, tâches et API de suivi non isolées.

## 6. Lost/Missing Components

- Historique GitHub original, tags, branches, remote et reflog : manquants.
- Progression historique des migrations avant les migrations initiales consolidées :
  impossible à comparer; le schéma actuel est toutefois reproductible.
- Secrets locaux/production non versionnés : volontairement absents; configuration
  externe requise.
- Artifacts ML et datasets historiques de l'ancien projet : non récupérés; aucun
  artifact fictif créé.
- Preuve vCenter, Hyper-V autorisé, SMTP externe et installation Windows Service :
  absente, à fournir par les environnements cibles.
- Adaptateurs Teams, Slack et Telegram : seulement réservés, jamais annoncés actifs.

Les dossiers conceptuels `collectors/`, `ml/`, `docker/` n'existent pas sous ces
noms; leurs responsabilités réelles sont dans `vmware_connector/`,
`hyperv_connector/`, `backend/ml_engine/`, `backend/Dockerfile` et
`docker-compose.yml`. Ce n'est pas une perte fonctionnelle.

## 7. Regression Report

| Priorité initiale | Régression/incohérence | État final |
| ----------------- | ---------------------- | ---------- |
| CRITICAL | Un tenant pouvait nommer une variable serveur arbitraire comme secret connecteur. | Corrigé par préfixe tenant dédié et validation endpoint/type. |
| HIGH | `TaskRun` était visible entre tenants et son idempotence était globale. | Corrigé par FK, queryset et contraintes tenant/globales séparées. |
| HIGH | Deux workers pouvaient envoyer la même notification; `SENDING` restait bloqué. | Corrigé et prouvé par concurrence PostgreSQL/recovery. |
| HIGH | Verrou notification avec jointure nullable invalide sous PostgreSQL. | Corrigé après échec réel du test PostgreSQL. |
| HIGH | Une tâche Hyper-V pouvait être consommée par le worker Linux. | Queue `hyperv` dédiée; worker Linux limité à `celery`. |
| HIGH | Artifacts ML absolus/non partagés; évaluation et prédiction incomplètes. | Volume partagé, chemins relatifs, holdout, évaluation et tendances ajoutés. |
| HIGH | États de règles mélangeaient disques/services et rescannaient les mêmes mesures. | Dimension, garde temporelle et résolution automatique ajoutées. |
| HIGH | Unités réseau et idempotence métrique incompatibles/inter-tenant. | `bytes/s`, validation finie et contrainte tenant. |
| MEDIUM | Datastores VMware absents et assets disparus jamais réconciliés. | Discovery datastore et passage `UNAVAILABLE/OFFLINE`. |
| MEDIUM | VM éteinte repassait ONLINE lors de l'ingestion. | Statut source restauré après ingestion. |
| MEDIUM | Refresh JWT non révoqué et échec refresh laissant les tokens. | Blacklist JWT et nettoyage frontend. |
| MEDIUM | Curseur replay invalide renvoyait 500; curseur frontend non tenant. | 400 validé et clé session par client. |
| MEDIUM | Détail asset lançait une requête métriques sans machine. | Hook conditionnel. |
| MEDIUM | Documentation surestimait tests/couverture/intégrations. | Chiffres et limites corrigés. |

Le message historique « serveur API injoignable » n'a pas été reproduit avec le
lanceur complet. Après redémarrage, API, frontend, worker et Beat sont actifs; le
login live a réussi. La capture correspondait à un frontend lancé sans API
joignable, pas à un endpoint de login cassé démontré.

## 8. Fixes Performed

Liste exhaustive par domaine :

- Racine/configuration : `README.md`, `.env.example`, `backend/.env.example`, `backend/requirements.txt`,
  `backend/config/settings.py`, `backend/config/urls.py`, `docker-compose.yml`.
- Async : `backend/async_tasks/{models.py,idempotency.py,tasks.py}` et migrations
  `0002`, `0003`.
- API/sécurité/tests : `backend/common/{api.py,serializers.py,tests.py,
  test_reconstruction.py}`.
- Inventory/intégrations : `backend/inventory/services.py`,
  `backend/integrations/{models.py,services.py,tasks.py}`, migration `0002`,
  `vmware_connector/collector.py`, `hyperv_connector/scripts/collect.ps1`.
- Métriques : `backend/metrics/{models.py,normalization.py,services.py}` et migration
  `0002`.
- Monitoring : `backend/monitoring/{models.py,engine.py,alert_service.py,
  recommendations.py}` et migrations `0003`, `0004`.
- ML : `backend/ml_engine/{models.py,pipeline.py,tasks.py,evaluation.py,
  predictive.py}`, migration `0002`, commande `evaluate_ml`,
  `scripts/evaluate-ml.ps1`.
- Notifications : `backend/notifications/{services.py,tasks.py}`.
- Agent : `agent/tests/test_agent.py`.
- Frontend : `frontend/src/{api.js,auth.jsx,hooks.js,realtime.jsx,
  frontend.test.js,pages/Resources.jsx}`.
- Scripts : `scripts/{start-local.ps1,test-all.ps1}`.
- Documentation : `AGENT.md`, `ALERT_ENGINE.md`, `ARCHITECTURE.md`,
  `ASYNC_TASKS.md`, `BASELINE.md`, `DASHBOARD.md`, `DATABASE.md`, `HYPERV.md`,
  `METRICS.md`, `ML.md`, `ML_EVALUATION.md`, `NOTIFICATIONS.md`, `PREDICTIVE.md`,
  `REALTIME.md`, `RECOMMENDATIONS.md`, `RECONSTRUCTION.md`, `RULE_ENGINE.md`,
  `VMWARE.md` et le présent rapport.

Aucun fichier fonctionnel n'a été supprimé. Les dépendances backend inutilisées
`requests`, `python-decouple` et `psutil` ont été retirées; `requests/psutil`
restent correctement déclarées dans l'agent.

## 9. Test Results

### Résultats automatisés

| Suite | PASS | FAIL | SKIPPED | ERROR | Résultat |
| ----- | ---: | ---: | ------: | ----: | -------- |
| Backend PostgreSQL 17 | 48 | 0 | 0 | 0 | PASS |
| Backend SQLite compatibilité | 45 | 0 | 3 | 0 | PASS |
| Agent Python | 8 | 0 | 0 | 0 | PASS |
| Frontend Vitest | 10 | 0 | 0 | 0 | PASS |
| Total de référence PostgreSQL + agent + frontend | 66 | 0 | 0 | 0 | PASS |

Les trois tests SQLite ignorés sont exactement les scénarios de concurrence
PostgreSQL : deux workers de notification, deux créations d'alerte et trois agents
simultanés. Ils réussissent tous sur PostgreSQL; aucun test fonctionnel n'est caché.

Autres contrôles : Ruff zéro erreur, ESLint zéro avertissement, Vite build succès,
`npm audit` zéro vulnérabilité, `pip check` succès, `makemigrations --check` sans
changement, `check --deploy` sans avertissement avec paramètres production, et
couverture backend 61 %.

### Base vide et intégration live

- Base isolée `infrasentinel_review_blank_20260824` créée sur PostgreSQL 17,
  toutes migrations appliquées, `check` réussi, base supprimée.
- PostgreSQL/Redis healthy et liés uniquement à `127.0.0.1` en local.
- Login, enrollment, heartbeat, métrique PostgreSQL, révocation et nettoyage : PASS.
- 14 endpoints métier et 13 routes frontend : HTTP 200.
- CORS preflight : 200; WebSocket avec ticket/replay : 101.
- Worker : `celery@LEGION pong`; queues `celery` et `hyperv`; tâches attendues
  enregistrées; `metrics.aggregate_history` exécutée via Redis avec résultat réel.
- Beat : processus actif et schedule actualisé après redémarrage.

Commandes principales :

```powershell
./scripts/test-all.ps1
./scripts/test-all.ps1 -Database sqlite
./.venv/Scripts/python.exe backend/manage.py makemigrations --check --dry-run
./.venv/Scripts/python.exe backend/manage.py migrate
./.venv/Scripts/celery.exe -A config --workdir backend inspect ping
./scripts/status-local.ps1
```

## 10. External Integrations

### VMware

`NOT TESTED — REAL VMWARE ENVIRONMENT REQUIRED`

Le code utilise réellement SmartConnect, `vim.HostSystem`, `vim.VirtualMachine`,
`vim.Datastore` et PerformanceManager. Les mocks valident formes, unités, erreurs,
persistance et idempotence, mais aucun connecteur/vCenter réel n'était configuré.

### Hyper-V

`NOT TESTED — REAL HYPER-V ENVIRONMENT REQUIRED`

PowerShell, le module Hyper-V et VMMS sont présents. La tentative locale sur
`LEGION` a échoué avec « You do not have the required permission » lors de
`Get-VM`. Le wrapper, la sécurité du secret, le JSON et les erreurs sont testés,
mais aucune métrique Hyper-V réelle n'a été acceptée.

### SMTP

`NOT TESTED — EXTERNAL SMTP DELIVERY`

Le backend console/locmem et la concurrence d'envoi sont validés. Aucune adresse,
identité ou credential SMTP n'a été inventé; Teams/Slack/Telegram restent inactifs.

### Windows Service

Le code service, auto-start, arrêt et commandes existent. L'installation réelle
avec élévation Administrateur reste à exécuter sur la machine cible.

## 11. Configuration Matrix

| Configuration | Local | Test | Production |
| ------------- | ----- | ---- | ---------- |
| PostgreSQL | Compose 17, env, bind `127.0.0.1` | DB Django temporaire + bootstrap vide; SQLite seulement compatibilité | Service HA, TLS, backup/restore testés |
| Redis | Compose 7.4, env, bind `127.0.0.1` | Redis live pour worker; channel mémoire dans tests Django | Redis protégé/TLS/HA via URL |
| Celery | worker Windows solo `celery,hyperv`, Beat | eager pour unitaires + worker Redis réel | workers Linux `celery` + Windows `hyperv` |
| SMTP | console backend | locmem | variables/coffre; livraison externe à valider |
| Frontend URL | `http://127.0.0.1:5173` configurable | Vite/HTTP live | origine HTTPS autorisée CORS/CSRF |
| Backend URL | `VITE_API_URL`, `VITE_WS_URL`, JSON agent | API locale live | URL HTTPS centrale/reverse proxy |
| VMware | aucun connecteur | mocks pyVmomi | URL HTTPS et secret tenant/coffre dédiés |
| Hyper-V | tentative locale refusée | mocks subprocess/JSON | worker Windows, remoting et droits délégués |

Les secrets applicatifs ne figurent pas dans Git. Les références connecteurs d'un
tenant doivent commencer par `INFRASENTINEL_CUSTOMER_<UUIDHEX>_`; les valeurs sont
injectées dans le worker, jamais retournées par l'API ni écrites dans les logs.

## 12. Remaining Risks

### CRITICAL

Aucun problème critique ouvert identifié.

### HIGH

Aucun problème high ouvert identifié dans le périmètre interne vérifiable.

### MEDIUM

1. L'historique GitHub d'origine empêche de prouver l'absence absolue de perte.
2. VMware réel reste à valider sur vCenter.
3. Hyper-V réel exige les permissions et un worker Windows exploité correctement.
4. SMTP externe reste à valider.
5. La couverture backend de 61 % laisse des branches API/erreur encore peu testées.
6. La table métrique n'a pas encore de politique de partition/rétention à fort volume.
7. Les JWT navigateur utilisent `localStorage`; une politique CSP/reverse proxy et
   une prévention XSS strictes restent indispensables en production.

### LOW

1. Teams, Slack et Telegram sont réservés mais non implémentés.
2. Aucune donnée réelle n'est présente pour entraîner/évaluer un modèle actif.
3. La disponibilité des compteurs vSphere varie selon le niveau statistique vCenter.

Comptage restant : 0 CRITICAL, 0 HIGH, 7 MEDIUM, 3 LOW.

## 13. Verdict

`PHASES 0-17 CONSISTENT AND READY TO CONTINUE`

Ce verdict signifie que la chaîne interne est stable et reproductible. Il ne
transforme pas les trois intégrations externes non testées en PASS et n'autorise
pas implicitement le démarrage de la phase 18.
