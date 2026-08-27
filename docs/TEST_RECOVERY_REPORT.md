# Phase 17.5 — Reconstruction et renforcement de la suite de tests

## 1. Verdict exécutif

Statut de la suite interne : **PASS**.

La suite de non-régression des fonctionnalités réellement présentes dans les phases
0 à 17 contient désormais :

- 161 tests Django découverts ;
- 158 PASS, 0 FAIL et 3 SKIPPED lors de l'exécution PostgreSQL finale avec
  intégration Redis activée ;
- 17 tests agent Windows, tous PASS ;
- 18 tests frontend Vitest, tous PASS ;
- couverture backend stricte de 92,9 %, branches incluses.

Le nombre de tests n'a pas été choisi pour reproduire un ancien total. Les tests ont
été ajoutés par responsabilité, risque métier et comportement effectivement
implémenté.

## 2. Méthode et base de référence

PostgreSQL 17 est la base de référence. La dernière exécution a créé la base Django
temporaire `test_infrasentinel`, appliqué toutes les migrations depuis zéro, exécuté
la découverte globale sans label de module, puis supprimé la base.

Redis 7.4 était réellement disponible sur `127.0.0.1:6379`. Les tests Redis ont été
activés explicitement afin de ne pas rendre la suite unitaire dépendante d'un service
externe.

La couverture comparable a été mesurée avec la même configuration sur :

- le commit initial de cette phase `33c18fa` ;
- le code final de la Phase 17.5.

Tests, migrations et fixtures sont exclus de la couverture. Les branches, les
connecteurs VMware/Hyper-V et le code d'infrastructure Django sont inclus.

## 3. État initial

| Suite | Tests | PASS | FAIL | SKIPPED | Status |
| --- | ---: | ---: | ---: | ---: | --- |
| Backend Django/PostgreSQL | 48 | 48 | 0 | 0 | PASS |
| Agent Python | 8 | 8 | 0 | 0 | PASS |
| Frontend Vitest | 10 | 10 | 0 | 0 | PASS |

Les 48 tests Django étaient concentrés dans :

- `backend/common/tests.py` : 24 tests ;
- `backend/common/test_reconstruction.py` : 24 tests.

Les applications `accounts`, `inventory`, `metrics`, `monitoring`, `ml_engine`,
`integrations`, `notifications`, `realtime` et `async_tasks` ne possédaient aucun
fichier de tests local.

Lacunes initiales principales :

- absence de tests directs du modèle, serializer et API `Anomaly` ;
- cycle JWT et RBAC incomplets ;
- CRUD users/customers/machines incomplet ;
- inférence ML sauvegarde → chargement → score → persistance non testée ;
- agrégation historique et tâches ML/reporting peu ou pas testées ;
- aucun test Python direct avec Redis réel ;
- couverture faible des erreurs API, notifications et collecteurs ;
- aucune mesure de couverture reproductible excluant tests et migrations.

## 4. Structure finale

Les tests historiques ont été conservés pour éviter un déplacement aveugle et la
perte de régressions déjà prouvées. Aucun test existant n'a été supprimé ou déplacé.
Les nouvelles suites spécifiques ont été créées près des applications responsables.

```text
backend/
  accounts/tests/
  async_tasks/tests/
  common/test_api_contracts.py
  integrations/tests/
  inventory/tests/
  metrics/tests/
  ml_engine/tests/
  monitoring/tests/
  notifications/tests/
  realtime/tests/
agent/tests/
frontend/src/frontend.test.js
```

Tests ajoutés :

- Django : 113 ;
- agent : 9 ;
- frontend : 8.

Tests déplacés : 0.

## 5. Matrice finale par emplacement

La colonne SKIPPED représente le résultat de l'exécution finale avec Redis réel
activé. Les tests Redis sont donc comptés PASS dans `async_tasks`.

| Domain | Tests | PASS | FAIL | SKIPPED | Coverage | Status |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| accounts / authentication / users / customers / RBAC | 18 | 18 | 0 | 0 | 96,8 % | PASS |
| async_tasks / Celery / Redis | 9 | 9 | 0 | 0 | 95,3 % | PASS |
| common / API et régressions transversales | 55 | 55 | 0 | 0 | 91,5 % | PASS |
| integrations | 12 | 10 | 0 | 2 | 99,2 % | PARTIAL |
| inventory / agents / machines | 11 | 11 | 0 | 0 | 98,6 % | PASS |
| metrics | 9 | 9 | 0 | 0 | 97,8 % | PASS |
| ml_engine / training / inference / predictive | 15 | 15 | 0 | 0 | 86,5 % | PASS |
| monitoring / rules / alerts / anomalies / recommendations | 16 | 16 | 0 | 0 | 94,4 % | PASS |
| notifications | 11 | 10 | 0 | 1 | 95,6 % | PARTIAL |
| realtime | 5 | 5 | 0 | 0 | 96,7 % | PASS |
| **Backend total** | **161** | **158** | **0** | **3** | **92,9 %** | **PASS** |

Couverture des collecteurs hors applications Django :

| Domain | Coverage | Status |
| --- | ---: | --- |
| VMware connector | 83,3 % | PASS |
| Hyper-V connector | 100 % | PASS |

## 6. Couverture avant/après

| Application | Before (`33c18fa`) | After | Status |
| --- | ---: | ---: | --- |
| accounts | 96,8 % | 96,8 % | PASS |
| async_tasks | 86,0 % | 95,3 % | PASS |
| common | 64,4 % | 91,5 % | PASS |
| config | 87,8 % | 87,8 % | PASS |
| integrations | 87,0 % | 99,2 % | PASS |
| inventory | 94,4 % | 98,6 % | PASS |
| metrics | 76,0 % | 97,8 % | PASS |
| ml_engine | 64,0 % | 86,5 % | PASS |
| monitoring | 76,3 % | 94,4 % | PASS |
| notifications | 76,2 % | 95,6 % | PASS |
| realtime | 89,1 % | 96,7 % | PASS |
| VMware connector | 35,3 % | 83,3 % | PASS |
| Hyper-V connector | 95,3 % | 100 % | PASS |
| **Global strict** | **73,3 %** | **92,9 %** | **PASS** |

Le rapport historique de reconstruction indiquait 61 %. Cette valeur utilisait une
ancienne méthode. La comparaison 73,3 % → 92,9 % est celle obtenue avec la même
configuration stricte sur les deux états Git.

Fichiers encore sous 80 % :

- `config/wsgi.py` : 0 %, chemin de démarrage WSGI non utilisé par les tests ASGI ;
- `ml_engine/management/commands/evaluate_ml.py` : 0 %, commande CLI non couverte ;
- `config/celery.py` : 71 % ;
- `ml_engine/predictive.py` : 79 %.

Ces fichiers ne font pas descendre une application métier critique sous l'objectif
de 80 %.

## 7. Couverture fonctionnelle reconstruite

### Accounts, authentication et RBAC

**PASS** : login valide/invalide, utilisateur désactivé, access JWT, refresh et
rotation, blacklist, logout, token invalide/expiré, endpoints protégés,
registration, CRUD users/customers, doublons, isolation Customer A/B et matrice des
cinq rôles réellement présents : ADMIN, SUPERVISOR, TECHNICIAN, CLIENT et VIEWER.

### Agents et inventory

**PASS** : enrollment, heartbeat, ingestion, token invalide/révoqué, payload
malformé, multi-agent, tenant, idempotence, reconnexion, transitions online/offline,
CRUD machines/environments et types Windows/VMware/Hyper-V.

**PARTIAL** : aucun endpoint de rotation du token agent n'existe actuellement ; il
n'a pas été inventé pour cette phase.

### Metrics, rules et alerts

**PASS** : ingestion, normalisation, unités, timestamps ISO et `datetime`, futur,
données anciennes, lots invalides, valeurs non finies, metadata, idempotence,
concurrence PostgreSQL, agrégation historique, six opérateurs, durée, scopes,
règles simultanées, transitions, offline, cooldown, escalation, réouverture et 100
métriques identiques produisant une seule alerte durable.

### Anomalies, ML et prédictif

**PASS** : modèle/serializer/API Anomaly, score, timestamp, métrique source,
machine, tenant et acknowledgement. Le chemin ML complet artefact → load → input →
score → classification → Anomaly → Alert → événement realtime est couvert, ainsi
que dataset insuffisant, modèle absent, artefact manquant, artefact corrompu,
données normales/extrêmes/incomplètes, paramètres scientifiques, contrainte du
modèle actif, évaluation sans vérité terrain et tendances.

**PARTIAL** : un artefact corrompu échoue explicitement mais le pipeline ne possède
pas encore de fallback contrôlé ou de statut automatique FAILED pour cette erreur.

### Recommendations

**PASS** : CPU, RAM, disque, réseau, machine offline, service Windows, host/VM
VMware et host/VM Hyper-V produisent toujours des recommandations explicables et
non destructives. Les recommandations host VMware/Hyper-V sont contextualisées.

**PARTIAL** : certains cas VM/offline utilisent encore le fallback générique plutôt
qu'un catalogue spécialisé.

### VMware et Hyper-V

**PASS** pour les tests unitaires/mocks : secrets, erreurs de connexion,
timeouts, découverte, hosts, VM, datastore, métriques, normalisation, persistance,
retry et idempotence.

**NOT TESTED** : environnement VMware réel.

**NOT TESTED** : environnement Hyper-V réel.

### Realtime

**PASS** : ticket authentifié, utilisateur désactivé, isolation client, livraison,
reconnexion, replay HTTP/WebSocket, plusieurs clients, déconnexion et conservation
durable lorsque le channel layer échoue. Le polling frontend reste présent comme
fallback.

### Notifications

**PASS** : INFO, WARNING, HIGH, CRITICAL, préférences, minimum de sévérité,
anti-spam, cooldown, déduplication, escalation CRITICAL, retry exponentiel,
récupération d'un worker interrompu, succès, échec, concurrence et isolation.

**PARTIAL** : LOW et MEDIUM ne sont pas des sévérités du modèle actuel. Slack,
Teams et Telegram sont déclarés mais aucun adapter fonctionnel n'est implémenté ;
les tests vérifient qu'ils ne sont jamais présentés comme envoyés.

**NOT TESTED** : livraison SMTP externe.

### Celery et Redis

**PASS** : autodiscovery, enqueue, exécution eager, retry/failure via services,
idempotence, double exécution, `transaction.on_commit`, reprise de tâche stale,
notifications, ML, VMware, Hyper-V, règles et rapports.

**PASS** avec Redis réel : PING, set/get, reconnexion après fermeture du pool,
aller-retour Kombu sur une file isolée et panne rapide sur un port indisponible.

**PASS** avec worker réel : `celery@LEGION` a répondu `pong`; la tâche
`metrics.aggregate_history` a transité via Redis et retourné `{'aggregates': 0}`.

**PARTIAL** : un redémarrage destructif du worker local en cours d'utilisation n'a
pas été effectué. La sémantique de récupération stale est couverte en test.

### Frontend et agent

**PASS** : 17 tests agent couvrent config, HTTPS, cache SQLite, client HTTP,
réponses invalides, retry, collecte, credentials de test, enrollment, reconnexion et
arrêt propre.

**PASS** : 18 tests frontend couvrent normalisation API, JWT/interceptors refresh,
états loading/empty/error/offline/partial, composants de supervision et import des
pages critiques. ESLint et le build Vite sont PASS.

**PARTIAL** : les routes protégées ne sont pas montées dans un navigateur DOM par
une bibliothèque de type Testing Library ; elles sont validées par import/build et
par les tests des mécanismes JWT.

## 8. Correctifs révélés par les tests

Les tests ont découvert quatre défauts fonctionnels réels, corrigés sans refonte :

1. un email dupliqué avec une casse différente provoquait une erreur PostgreSQL 500
   au lieu d'une validation API 400 ;
2. un timestamp futur fourni comme objet `datetime` et une metadata `[]`
   contournaient le normaliseur ;
3. les actions ML `train` et `evaluate` existaient mais POST était interdit par le
   ViewSet, donnant toujours 405 ;
4. un timeout PowerShell Hyper-V remontait hors du type d'erreur du connecteur et ne
   pouvait pas suivre la politique de retry uniforme.

L'infrastructure de test a aussi été corrigée afin d'utiliser un fichier Coverage
unique, d'arrêter le script au premier code de sortie non nul et d'activer Redis via
un switch explicite.

## 9. Tests externes non exécutés

| Test | Status | Condition d'activation |
| --- | --- | --- |
| vCenter/VMware réel | NOT TESTED | `INFRASENTINEL_RUN_REAL_VMWARE=1` et credentials réels |
| Hyper-V réel | NOT TESTED | `INFRASENTINEL_RUN_REAL_HYPERV=1` et permissions réelles |
| SMTP externe | NOT TESTED | `INFRASENTINEL_RUN_EXTERNAL_SMTP=1` et relais réel |
| Installation Windows Service | NOT TESTED | Session Windows administrateur |

Ces tests ne sont pas remplacés par des mocks dans le rapport.

## 10. Risques restants

### Critical gaps

**PASS** : aucune lacune critique connue dans la suite interne PostgreSQL des
fonctionnalités actuellement implémentées.

### High gaps

**PARTIAL** : rotation de token agent absente, fallback d'artefact ML corrompu à
formaliser, redémarrage live du worker non exécuté, environnements VMware/Hyper-V et
SMTP externes indisponibles.

### Medium gaps

**PARTIAL** : tests frontend sans DOM, recommandations spécifiques VM encore
génériques, sévérités LOW/MEDIUM absentes et querysets paginés sans ordering
explicite signalés par DRF pendant les tests.

## 11. Commandes de validation

Validation complète PostgreSQL avec Redis réel :

```powershell
cd C:\xampp\htdocs\InfraSentinel-AI
.\scripts\test-all.ps1 -Database postgresql -RedisIntegration
```

Backend seul :

```powershell
cd C:\xampp\htdocs\InfraSentinel-AI\backend
. ..\scripts\common.ps1
Import-DotEnv '.env'
$env:INFRASENTINEL_RUN_REDIS_INTEGRATION='1'
..\.venv\Scripts\python.exe manage.py test --verbosity 1
```

Redis isolé :

```powershell
$env:INFRASENTINEL_RUN_REDIS_INTEGRATION='1'
..\.venv\Scripts\python.exe manage.py test async_tasks.tests.test_redis_integration -v 2
```

Agent et frontend :

```powershell
$env:PYTHONPATH=(Resolve-Path '.\agent').Path
.\.venv\Scripts\python.exe -m unittest discover agent\tests -v
cd frontend
npm run test
npm run lint
npm run build
```

## 12. Résultat final demandé

```text
PHASE 17.5 TEST RECOVERY

Backend tests: 161 — 158 PASS / 0 FAIL / 3 SKIPPED
Agent tests: 17 — 17 PASS / 0 FAIL / 0 SKIPPED
Frontend tests: 18 — 18 PASS / 0 FAIL / 0 SKIPPED

Backend coverage: 92.9% — PASS

PostgreSQL: PASS
Redis: PASS
Celery: PASS

Critical gaps: PASS
High gaps: PARTIAL
Medium gaps: PARTIAL

FINAL VERDICT:
TEST SUITE READY FOR PHASE 18
```

La Phase 18 n'a pas été commencée.
