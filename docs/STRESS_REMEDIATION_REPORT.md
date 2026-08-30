# InfraSentinel-AI — Rapport de remédiation du stress test local

Date : 30 août 2026

Périmètre : poste local autorisé, API loopback, PostgreSQL et Redis Docker

Rapport source : [HEAVY_LOCAL_STRESS_TEST_REPORT.md](HEAVY_LOCAL_STRESS_TEST_REPORT.md)

## Verdict exécutif

**PARTIAL.** La cause des erreurs HTTP 500 a été corrigée : PostgreSQL ne sature
plus ses 100 connexions, aucun HTTP 500 n'a été observé pendant les nouvelles
campagnes, et 250 agents au rythme réaliste passent avec un p95 de 98,1 ms. Le
profil artificiel à une requête par seconde révèle cependant un plafond
applicatif proche de 45 requêtes/s et dépasse la limite de sécurité de 2 s de p95
à 100 agents.

Le pipeline Isolation Forest a été rendu reproductible, temporel et conscient de
l'absence de données. Les trois alertes ML signalées par le rapport initial, ainsi
qu'une alerte corrélée ouverte pendant l'observation corrective, ont été résolues
automatiquement après trois fenêtres normales. Le taux de faux positifs
ne peut pas être affirmé sans vérité terrain annotée : le taux de signalement
stable observé sur le holdout est de 4,90 %, ce qui reste une mesure différente.

La télémétrie GPU réelle est validée. La détection d'une anomalie GPU par le ML
reste **PARTIAL**, car les charges autorisées ont produit des scores sous le seuil.
La règle CPU est testée unitairement, mais son déclenchement réel à plus de 80 %
n'a pas été reproduit pendant la remédiation sans dépasser le cadre thermique
sûr du poste.

## 1. Corrections réalisées

### 1.1 PostgreSQL

Cause avant correction : chaque requête pouvait conserver sa connexion Django
pendant 60 secondes, sans pool borné. Sous charge accélérée, PostgreSQL atteignait
`max_connections=100`, puis renvoyait des erreurs HTTP 500.

Correction :

- passage à `psycopg[binary,pool] 3.3.4` ;
- pool Django borné et configurable par variables d'environnement ;
- `CONN_MAX_AGE=0` lorsqu'un pool est actif ;
- vérification de santé des connexions ;
- refus au démarrage d'une combinaison pool + `CONN_MAX_AGE` non nul ;
- valeurs locales testées : minimum 0, maximum 20, timeout 10 s,
  `max_idle` 60 s ;
- documentation et exemples d'environnement mis à jour.

La limite PostgreSQL est restée à 100 connexions. Aucun PgBouncer ni relèvement
artificiel de `max_connections` n'a été nécessaire.

### 1.2 Isolation Forest et récupération des alertes

Le pipeline utilise maintenant :

- des fenêtres complètes d'une minute ;
- au moins 200 fenêtres réelles pour entraîner ;
- un split chronologique 60/20/20 entraînement/calibration/évaluation ;
- imputation médiane, indicateurs de valeurs manquantes et `RobustScaler` ;
- `IsolationForest(n_estimators=200, contamination=0.02,
  random_state=42, n_jobs=-1)` ;
- un seuil égal au maximum des quantiles 99 % entraînement/calibration ;
- une confirmation temporelle de 3 fenêtres anormales parmi les 5 dernières,
  avec la plus récente anormale ;
- une récupération après 3 fenêtres normales consécutives ;
- une clé de source stable `ml:active` pour éviter les doublons de modèle ;
- une validation explicite du contrat de features et de sa version ;
- l'exclusion par défaut des données `CONTROLLED_TEST`, synthétiques et de
  démonstration.

Les jeux de démonstration doivent demander explicitement
`include_controlled=True`. Les 486 anciennes métriques contrôlées ont été
étiquetées puis exclues des futurs entraînements réels.

Modèle réel validé :

| Champ | Valeur observée |
|---|---|
| version | `iforest-20260830T101505-3d2d89e3` |
| fenêtres réelles | 529 |
| split | 317 / 106 / 106 |
| schéma | 2.0 |
| features | 6 de base + utilisation GPU |
| seuil | 0,041742357465 |
| taux brut holdout | 10,377 % |
| taux stable 3/5 holdout | 4,902 % |
| vérité terrain | indisponible |
| FPR prouvé | non mesurable |

Une anomalie temporelle réelle a été produite sur la fenêtre 10:16 UTC, avec un
score 0,054299 supérieur au seuil. Elle a été persistée à 10:17:08 UTC, soit une
latence bout-en-bout observée de 68 secondes, cohérente avec la fenêtre et la
cadence Celery d'une minute. Après récupération, l'inférence a évalué 133
fenêtres, produit zéro nouvelle anomalie et laissé zéro alerte ML ouverte. Les
alertes historiques ont été résolues à `2026-08-30 10:20:08Z` avec la raison
`ml_recovery_hysteresis`.

### 1.3 Règles CPU

`RuleState` conserve maintenant le dernier instant correspondant, le nombre de
correspondances consécutives et le nombre de mesures normales consécutives. Pour
une règle avec durée :

- au moins deux observations consécutives sont exigées ;
- un trou supérieur à `max(120 s, durée × 2)` remet l'évidence à zéro ;
- une alerte active est résolue après deux observations normales ;
- les règles sans durée restent immédiates.

La règle réelle a été conservée à `CPU > 80 % pendant 30 s`, cooldown 300 s. Les
runs sûrs ont atteint 58,9 %, 69,3 %, puis 76,2 %. Le seuil n'a donc pas été
franchi pendant cette campagne et aucune alerte n'était attendue.

### 1.4 GPU

L'agent NVIDIA collecte maintenant :

- `system.gpu.utilization` en pourcentage ;
- `system.gpu.memory.used` en octets ;
- `system.gpu.memory.utilization` en pourcentage ;
- `system.gpu.temperature` en degrés Celsius.

Une valeur `N/A`, non finie ou absente n'est jamais remplacée par zéro. Les
features GPU sont optionnelles et ne rejoignent un modèle qu'avec au moins 200
fenêtres et 50 % de couverture. La mémoire GPU utilise le maximum de la fenêtre,
pas une somme de jauges.

Preuves réelles :

| Charge | Utilisation max | VRAM max | Température max | Puissance max |
|---|---:|---:|---:|---:|
| modérée | 39 % | 254 MiB | 70 °C | 51,09 W |
| élevée | 65 % | 254 MiB | 74 °C | 80,46 W |
| allocation VRAM | 25–41 % | 4 204 MiB | 55–57 °C | 19,40 W |

L'agent a persisté 4 408 213 504 octets, soit 51,6 % de VRAM. Après arrêt de la
charge : utilisation 0 %, mémoire 0 octet, température 52–55 °C et aucune alerte
ouverte. Les fenêtres contrôlées ont été étiquetées et ne contamineront pas un
réentraînement réel.

## 2. Résultats PostgreSQL avant/après

| Campagne | Agents | Débit | p95 | p99 | Erreurs | Connexions PG max |
|---|---:|---:|---:|---:|---:|---:|
| avant, accéléré | 50 | 50,868 req/s | 203,2 ms | 474,2 ms | 2,424 %, 74 HTTP 500 | 100 |
| après, accéléré | 25 | 25,014 req/s | 113,1 ms | 150,5 ms | 0 % | 17 |
| après, accéléré | 50 | 45,525 req/s | 1 334,6 ms | 1 438,7 ms | 0 % | 26 |
| après, accéléré | 100 | 45,158 req/s | 2 604,1 ms | 2 699,5 ms | 0 % | 26 |
| après, accéléré exploratoire | 250 | 55,071 req/s | 5 210,2 ms | 5 283,5 ms | 0 % | 24 |

La correction est prouvée par l'absence d'erreur et le plafond de 26 connexions,
pas par une hausse du débit. Le nouveau goulet est le traitement applicatif
synchrone des lots et événements temps réel. La campagne finale s'est arrêtée à
100 agents accélérés lorsque p95 a dépassé 2 000 ms. Le palier exploratoire 250
provient du premier re-test post-correction et démontre seulement l'absence de
saturation PostgreSQL, pas une latence acceptable.

## 3. Capacité au rythme réaliste

Profil : intervalle métriques 30 s, heartbeat 60 s, 12 métriques par lot, jitter
initial aléatoire, 30 s de mesure après 10 s de warmup.

| Agents | Débit | p50 | p95 | p99 | Erreurs | Latence traitement p95 | PG max | File Celery fin |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 50 | 2,801 req/s | 51,6 ms | 71,6 ms | 198,2 ms | 0 % | 46,2 ms | 16 | 0 |
| 100 | 5,596 req/s | 46,4 ms | 76,2 ms | 103,4 ms | 0 % | 48,0 ms | 16 | 0 |
| 250 | 13,742 req/s | 55,5 ms | 98,1 ms | 114,9 ms | 0 % | 66,3 ms | 16 | 0 |

Au palier 250, 3 000 métriques ont été acceptées, le backend a atteint 64,5 % CPU
pour son processus, PostgreSQL 16 connexions, Redis 101 clients et la file Celery
est revenue à zéro. Aucun deadlock ni fichier temporaire PostgreSQL n'a été
observé.

Un premier contrôle contre la pile Docker normale a reçu des HTTP 429 attendus :
le quota agent de production était actif. La mesure finale a utilisé une instance
Daphne locale dédiée sur le port 8010 avec uniquement
`AGENT_REQUEST_RATE=100000/min`. Le quota de la pile Docker normale n'a pas été
modifié.

## 4. Validation et régression

| Domaine | Commande | Résultat observé |
|---|---|---|
| backend PostgreSQL | `python backend/manage.py test --verbosity 1` avec variables PostgreSQL/Redis de test | 203 tests, OK, 6 skipped, 135,150 s |
| agent | depuis `agent`, `python -m unittest discover -s tests -v` | 26/26 PASS |
| frontend | `npm test -- --run` | 40/40 PASS |
| lint frontend | `npm run lint` | PASS |
| build frontend | `npm run build` | PASS, 2 386 modules, 12,46 s |
| qualité Python | `ruff check backend agent scripts` | PASS |
| Django | `python backend/manage.py check` | PASS |
| migrations | `python backend/manage.py makemigrations --check --dry-run` | aucune modification |
| démonstration | `python backend/manage.py prepare_pfe_demo --customer-slug infrasentinel-demo --reset` | 200 fenêtres d'entraînement synthétiques marquées, 1 anomalie de démonstration |
| vérification démo | même commande avec `--verify-only` | PASS |
| Docker | `docker compose build` puis recréation de la pile | build et migrations PASS |

Contrôle live final à 17:18 (+01:00) : les six services applicatifs étaient
`healthy`, le conteneur de migration était sorti avec le code 0, les healthchecks
API direct et via le frontend répondaient HTTP 200, Redis répondait `PONG` et le
worker Celery répondait `pong` avec les files `celery` et `hyperv`. Le worker
avait traité 198 tâches et n'en avait aucune active au relevé. Beat était actif,
sans redémarrage, et publiait les tâches notifications, règles, ML, VMware et
Hyper-V aux cadences configurées. Cette photographie live complète les tests ;
elle ne prouve pas à elle seule chaque effet downstream.

La première exécution backend avec `API_DOCS_PUBLIC=false` a correctement reçu un
HTTP 401 sur un test qui attend une documentation publique. Le profil de test a
ensuite explicitement utilisé `API_DOCS_PUBLIC=true` et toute la suite a passé.
Il ne s'agit pas d'un contournement d'authentification : la configuration locale
protège volontairement la documentation.

## 5. Matrice finale demandée

| Contrôle | Verdict | Justification |
|---|---|---|
| POSTGRESQL SATURATION | **PASS** | 0 erreur, 26 connexions max sous charge accélérée |
| HTTP HEAVY LOAD | **PARTIAL** | débit plafonné à ~45 req/s ; p95 2,60 s à 100 accélérés |
| 250 AGENTS | **PASS** | profil réaliste, p95 98,1 ms, 0 % erreur |
| CPU RULE DETECTION | **PARTIAL** | logique et tests PASS ; seuil réel >80 % non atteint |
| CPU ML ANOMALY | **PARTIAL** | temporalité validée, causalité CPU non prouvée |
| CPU RECOVERY | **PASS** | retour durable sous 10 %, aucune alerte ouverte |
| GPU TELEMETRY | **PASS** | métriques agent réelles, dont 4,41 GB de VRAM |
| GPU ML FEATURE | **PASS** | feature optionnelle dans le modèle n°8, absence ≠ zéro |
| GPU ML ANOMALY | **PARTIAL** | scores de charge sous le seuil, aucune donnée inventée |
| GPU RECOVERY | **PASS** | 0 % / 0 byte et aucune alerte ouverte |
| ML FALSE POSITIVE CONTROL | **PARTIAL** | signalement stable 4,90 %, FPR impossible sans labels |
| ML ALERT RECOVERY | **PASS** | résolution automatique après 3 normales |
| REDIS | **PASS** | fonctionnement et files contrôlés pendant les runs |
| CELERY | **PASS** | worker/Beat et tests d'intégration passants |
| WEBSOCKET | **PASS** | connexion, multi-client, replay et sécurité testés |

## 6. Artefacts et reproductibilité

Rapports bruts locaux, volontairement ignorés par Git :

```text
runtime/performance/P24-remediation-realistic-rate-limit-control.json
runtime/performance/P24-remediation-realistic.json
runtime/performance/P24-remediation-accelerated-final.json
runtime/performance/controlled-cpu-moderate-remediation.json
runtime/performance/controlled-cpu-elevated-remediation.json
runtime/performance/controlled-cpu-high-remediation.json
runtime/performance/controlled-gpu-moderate-remediation.json
runtime/performance/controlled-gpu-elevated-remediation.json
runtime/performance/controlled-gpu-vram-agent-capture2-remediation.json
```

Sauvegarde préalable au travail ML :

```text
runtime/backups/infrasentinel-pre-ml-remediation-20260830T110942.dump
size: 1 120 553 bytes
SHA-256: 911A4E3D74ADB4F499FD65CBD571118B34CCF5C9FBF67E29046C4108B9193CE9
```

Commandes principales :

```powershell
# Validation de la configuration PostgreSQL
python backend/manage.py check
python backend/manage.py migrate --check

# Charge réaliste
./scripts/run-performance-test.ps1 `
  -Stages '50,100,250' -IntervalSeconds 30 `
  -DurationSeconds 30 -WarmupSeconds 10

# Charge accélérée
./scripts/run-performance-test.ps1 `
  -Stages '25,50,100' -IntervalSeconds 1 `
  -DurationSeconds 30 -WarmupSeconds 10

# Étiquetage contrôlé, aperçu avant application
python scripts/performance/label_controlled_metrics.py `
  --machine-id <uuid> `
  --reports runtime/performance/<controlled-report>.json

# Régression
python backend/manage.py test --verbosity 1
Push-Location agent
../.venv/Scripts/python.exe -m unittest discover -s tests -v
Pop-Location
Set-Location frontend
npm test -- --run
npm run lint
npm run build
```

Les options exactes disponibles sont celles de `--help`; les scripts imposent
leurs propres limites loopback, durée, concurrence et sécurité matérielle.

## 7. Risques résiduels et suite recommandée

### HIGH

1. Profiler l'ingestion métrique et la diffusion temps réel au-delà de 25 req/s,
   puis tester un déploiement multi-processus ASGI avant d'annoncer une capacité
   accélérée supérieure.
2. Constituer une vérité terrain annotée normale/anormale. Sans elle, précision,
   rappel, F1 et faux positifs restent inconnus.

### MEDIUM

1. Refaire une preuve CPU >80 % uniquement avec température package disponible,
   sur une durée suffisante pour la règle, sans désactiver les protections.
2. Collecter au moins 200 fenêtres couvrant mémoire et température GPU afin que
   ces features rejoignent scientifiquement un prochain modèle.
3. Évaluer une anomalie GPU réelle annotée avant de déclarer ce scénario PASS.

### LOW

1. Conserver les rapports JSON hors Git ou dans un stockage d'artefacts dédié.
2. Répéter les tests sur une durée de plusieurs heures et un hôte distinct pour
   mesurer la dérive, les reconnexions longues et la croissance PostgreSQL.
