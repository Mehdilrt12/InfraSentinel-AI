# InfraSentinel-AI — Controlled local high-load validation

Date d'exécution : 29–30 août 2026

Périmètre : ordinateur local autorisé et API loopback uniquement

## Mise à jour de remédiation — 30 août 2026

Les quatre problèmes confirmés ci-dessous ont été corrigés puis re-testés. Le
détail reproductible, les rapports JSON et les limites se trouvent dans
[STRESS_REMEDIATION_REPORT.md](STRESS_REMEDIATION_REPORT.md).

Verdict actuel : **PARTIAL — la saturation PostgreSQL est corrigée, 250 agents
réalistes passent, les alertes ML récupèrent, mais le débit accéléré plafonne côté
application et les preuves CPU/GPU ML restent partielles.**

| Validation finale | Verdict | Preuve actuelle |
|---|---|---|
| POSTGRESQL SATURATION | PASS | 26 connexions max, 0 erreur jusqu'à 100 agents accélérés |
| HTTP HEAVY LOAD | PARTIAL | 45,2 req/s à 100, p95 2,60 s, gate de latence |
| 250 AGENTS | PASS | intervalle 30 s, 0 erreur, p95 98,1 ms |
| CPU RULE DETECTION | PARTIAL | moteur corrigé/testé ; matériel borné à 76,2 %, seuil 80 % non atteint |
| CPU ML ANOMALY | PARTIAL | stabilité 3/5 validée ; pas de causalité CPU réelle prouvée |
| CPU RECOVERY | PASS | CPU revenu sous 10 % sur plusieurs échantillons, aucune alerte ouverte |
| GPU TELEMETRY | PASS | 65 %, 74 °C, 4 408 213 504 bytes / 51,6 % captés par l'agent |
| GPU ML FEATURE | PASS | utilisation GPU dans le modèle n°8 ; absence distincte de zéro |
| GPU ML ANOMALY | PARTIAL | scores réels sous seuil ; aucune anomalie fabriquée |
| GPU RECOVERY | PASS | 0 %, 0 byte, 52–55 °C, aucune alerte ouverte |
| ML FALSE POSITIVE CONTROL | PARTIAL | 529 fenêtres, FPR non mesurable sans labels, taux stable holdout 4,90 % |
| ML ALERT RECOVERY | PASS | alertes historiques résolues par hystérésis à 10:20:08Z |
| REDIS | PASS | sain durant les campagnes, files revenues à zéro |
| CELERY | PASS | worker/Beat sains et suites d'intégration passantes |
| WEBSOCKET | PASS | tests connexion, clients multiples, replay et sécurité passants |

Résultats finaux :

| Profil | Agents | req/s | p50 | p95 | p99 | erreurs | connexions PG max |
|---|---:|---:|---:|---:|---:|---:|---:|
| réaliste 30 s | 50 | 2,80 | 51,6 ms | 71,6 ms | 198,2 ms | 0 % | 16 |
| réaliste 30 s | 100 | 5,60 | 46,4 ms | 76,2 ms | 103,4 ms | 0 % | 16 |
| réaliste 30 s | 250 | 13,74 | 55,5 ms | 98,1 ms | 114,9 ms | 0 % | 16 |
| accéléré 1 s | 25 | 25,01 | 62,7 ms | 113,1 ms | 150,5 ms | 0 % | 17 |
| accéléré 1 s | 50 | 45,52 | 1 089,0 ms | 1 334,6 ms | 1 438,7 ms | 0 % | 26 |
| accéléré 1 s | 100 | 45,16 | 2 231,3 ms | 2 604,1 ms | 2 699,5 ms | 0 % | 26 |

Le test de contrôle avec le rate limit de production a volontairement reçu des
HTTP 429 ; l'instance Daphne dédiée a ensuite seule reçu
`AGENT_REQUEST_RATE=100000/min`. La pile Docker normale a conservé son quota.

## Rapport initial conservé

Le texte suivant décrit la campagne avant remédiation et reste conservé comme
preuve avant/après.

Verdict de la campagne initiale : **PARTIAL — plateforme stable en charge nominale, plafond PostgreSQL
reproductible en charge accélérée, chaîne ML encore trop sensible pour constituer
une preuve causale fiable.**

## Executive summary

La plateforme a réellement traité :

- 250 agents périodiques, avec 0 % d'erreur ;
- 50 agents accélérés à environ 50,9 requêtes/s, mais avec 2,424 % d'erreurs
  HTTP 500 ;
- une charge CPU réelle jusqu'à 86,3 %, arrêtée automatiquement par le garde de
  sécurité ;
- une charge CUDA réelle jusqu'à 66 % sur la RTX 5070 et 4 204 MiB de VRAM ;
- deux clients WebSocket simultanés avec diffusion, déconnexion, replay et rejet
  d'un ticket réutilisé ;
- une anomalie Isolation Forest non synthétique durant la fenêtre de charge CPU.

Les ressources, l'API et les files asynchrones reviennent à la normale. En
revanche, le modèle ML classe aussi plusieurs fenêtres de faible charge comme
anormales et laisse des alertes ML ouvertes après récupération. La détection ML
CPU est donc **PARTIAL**, et non PASS causal.

## Contraintes de sécurité appliquées

- cible HTTP limitée par le code à `localhost`, `127.0.0.1` ou `::1` ;
- concurrence maximale du banc API : 500 ;
- warmup maximal : 15 s ; mesure maximale : 60 s ; cooldown maximal : 30 s ;
- CPU : priorité `BELOW_NORMAL`, 24 workers max, 45 s max, abort à 85 %,
  RAM disponible minimale 2 GiB ;
- GPU : baseline froide et inactive obligatoire, durée CUDA 30 s max, duty-cycle
  75 % max, VRAM artificielle 50 % max, abort thermique à 78 °C durant les runs ;
- protections Windows, Intel et NVIDIA laissées actives ; aucun changement de
  fréquence, voltage, fan curve ou limite de puissance ;
- le palier CPU 90–100 % et le combiné CPU+GPU n'ont pas été exécutés, car la
  température package CPU n'est pas exposée sur cette machine.

La température CPU est **UNAVAILABLE** : aucun capteur ACPI/WMI exploitable,
aucun provider HWiNFO/OpenHardwareMonitor/CoreTemp et aucune API `psutil`
Windows ne donnent la température package. Cela impose les runs CPU courts et
conservateurs utilisés ici.

## Isolation, sauvegarde et nettoyage

Avant le nettoyage, une sauvegarde PostgreSQL custom a été produite et vérifiée
avec `pg_restore --list` :

```text
runtime/backups/infrasentinel-controlled-prestress-20260828T105610Z.dump
size: 539628 bytes
SHA-256: B731311A00FB1CD3A452B5C6EC0AF088B5DB0D249DEEDC1C01D35BDDB5B333ED
TOC entries: 349
```

Les tenants, environnements, machines et métriques générés portent
`CONTROLLED_TEST`, `load_test`, `load_run_id`, `load_stage` et `load_phase`.
Après chaque run, la suppression cible l'UUID exact du tenant et suit l'ordre
Machine → Environment → Customer sous verrou transactionnel. Vérification finale :

```text
controlled-test-* customers remaining: 0
final-ws-* customers remaining: 0
```

LEGION et ses données réelles n'ont pas été supprimés.

## Environnement validé

| Élément | Valeur observée |
|---|---|
| OS | Microsoft Windows 11 Pro 10.0.26200, build 26200 |
| CPU | Intel Core i9-14900HX, 24 cœurs / 32 processeurs logiques |
| RAM | 34 070 192 128 octets, soit 31,73 GiB |
| GPU | NVIDIA GeForce RTX 5070 Laptop GPU |
| VRAM | 8 151 MiB |
| Pilote NVIDIA | 616.56 |
| PyTorch | 2.11.0+cu128, CUDA disponible, device réel RTX 5070 |
| Docker | client/server 29.6.2 |
| Django / Python | 6.0.8 / 3.14.6 |
| PostgreSQL | 17.11, `max_connections=100` |
| Redis | 7.4.11 |

Les six services `frontend`, `api`, `db`, `redis`, `worker` et `beat` sont
restés `healthy`. Après reprise de la session, Docker Desktop était arrêté ; son
redémarrage a restauré les six services sans perte de données.

L'agent Windows utilisé est le vrai collecteur du repository, lancé comme
processus local avec la configuration et le secret DPAPI de
`runtime/real-agent-legion`. Il n'est pas installé en Windows Service sur ce
portable ; ce point n'est donc pas validé par cette campagne.

## Baseline

Baseline système initiale, 12 échantillons sur 60 s :

| Mesure | Résultat |
|---|---:|
| CPU moyen / max | 6,8 % / 18,7 % |
| RAM moyenne | 50,7 % |
| GPU utilisation | 0 % |
| GPU température max | 51 °C |
| GPU puissance max | 12,77 W |
| API health | 12/12 HTTP 200 |
| API p50 / p95 | 20,0 ms / 142,4 ms |

Baseline GPU dédiée, 12 échantillons sur 60 s : 0 % d'utilisation, 0 MiB VRAM,
53,7 °C en moyenne, 56 °C max, 15,23 W max, aucun throttling.

## Charge HTTP/ingestion accélérée

Profil : lots de 12 métriques, une émission par agent et par seconde, heartbeat
60 s, warmup 15 s, mesure 60 s, cooldown 30 s. C'est un profil de capacité
accéléré, pas l'intervalle opérationnel normal de l'agent.

| Agents | Requêtes | req/s | p50 | p90 | p95 | p99 | max | erreurs |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 612 | 10,199 | 62,7 ms | 95,2 ms | 107,2 ms | 142,5 ms | 179,7 ms | 0 % |
| 25 | 1 526 | 25,416 | 60,6 ms | 79,3 ms | 84,3 ms | 106,0 ms | 237,8 ms | 0 % |
| 50 | 3 053 | 50,868 | 92,9 ms | 141,1 ms | 203,2 ms | 474,2 ms | 584,2 ms | **2,424 %** |

Au palier 50 :

- 74 réponses HTTP 500 ;
- PostgreSQL atteint exactement 100 connexions ;
- les logs montrent `FATAL: sorry, too many clients already` ;
- 35 148 métriques acceptées ;
- débit d'insertion mesuré : 586,2 lignes métriques/s ;
- latence de traitement métrique p95 : 113,3 ms ;
- backend : 261,8 MiB RSS max et 122,7 % CPU process moyen (`psutil` autorise
  plus de 100 % pour un processus multithread) ;
- Redis : 397 ops/s max, 7,50 MiB max ;
- file Celery : pic 3, puis retour à 0 ;
- aucun deadlock PostgreSQL et cache hit proche de 100 %.

Le gate a arrêté la progression. Les paliers accélérés 100, 250 et 500 ne sont
pas exécutés, conformément à la règle « continuer seulement sans erreur ».

Débit maximal observé : **50,868 req/s avec 2,424 % d'erreurs**.

Débit maximal sans erreur : **25,416 req/s**.

## Flood d'agents au rythme opérationnel

Profil : intervalle métriques 30 s, heartbeat 60 s, identités et tokens uniques,
warmup 15 s, mesure 60 s, cooldown 30 s.

| Agents | Requêtes | req/s | p50 | p90 | p95 | p99 | erreurs | métriques acceptées |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 50 | 150 | 2,500 | 56,7 ms | 76,1 ms | 86,5 ms | 95,5 ms | 0 % | 1 200 |
| 100 | 300 | 4,999 | 55,6 ms | 73,3 ms | 78,8 ms | 95,1 ms | 0 % | 2 400 |
| 250 | 750 | 12,497 | 58,7 ms | 80,3 ms | 86,2 ms | 98,7 ms | 0 % | 6 000 |

Au palier 250 :

- latence traitement métrique p95 : 64,6 ms ;
- backend CPU moyen/max : 30,6 % / 74,8 % ;
- backend RSS max : 250,7 MiB ;
- PostgreSQL : 81 connexions max, 100,6 métriques insérées/s, cache hit 99,999 % ;
- Redis : 149 ops/s max, 3,46 MiB max ;
- file Celery : 0.

250 agents réalistes sont donc validés. 500 reste **NOT TESTED** : ce palier est
optionnel et le générateur actuel utilise un thread Windows par agent, ce qui
risque de mesurer le générateur plutôt que la plateforme.

## Sonde API représentative

La sonde réseau réelle sur `127.0.0.1:8000` observe :

| Cas | Résultat |
|---|---:|
| Login admin | 200 |
| Liste machines paginée | 200 |
| Détail cross-tenant | 404 |
| Query d'injection | 200, aucune fuite inter-tenant |
| Viewer vers users | 403 |
| JWT invalide | 401 |
| Payload machine invalide | 400, aucun traceback |
| Enrôlement / heartbeat / métriques | 201 / 200 / 202 |
| Publication agent cross-tenant | 403 |
| Token agent révoqué | 401 |
| Login navigateur sans CSRF | 403 |

Les en-têtes CSP, `nosniff`, `DENY` et `Referrer-Policy` sont présents.

## CPU réel, télémétrie, règles et ML

| Palier | Durée | CPU moyen | CPU max | Résultat sécurité |
|---|---:|---:|---:|---|
| modéré | 45 s | 54,5 % | 61,6 % | terminé normalement |
| élevé | ~19 s | 77,3 % | 86,3 % | abort automatique à 85 % |
| règle, répétition 1 | 45 s | 53,7 % | 62,7 % | terminé normalement |
| règle, répétition 2 | 45 s | 53,0 % | 58,5 % | terminé normalement |

Pendant ces runs, tous les healthchecks API réussissent, la RAM disponible ne
descend pas sous 13,9 GiB, et aucun service Docker ne devient unhealthy. Le
palier élevé est un arrêt de garde attendu, pas un échec logiciel.

### Télémétrie agent réelle

Extraits PostgreSQL de LEGION :

```text
23:20:58Z CPU 55.5 %
23:22:58Z CPU 84.3 %
23:25:58Z CPU 56.6 %
23:27:58Z CPU 53.8 %
23:46:28Z CPU 10.3 %
23:46:58Z CPU 4.6 %
```

Les valeurs corrèlent avec le banc local, puis reviennent à la baseline. Le
heartbeat continue et LEGION reste `ONLINE`.

### Règle CPU et recommandation

La règle configurée est `CPU > 40 % pendant 30 s`, sévérité CRITICAL, cooldown
300 s. Aucun nouvel alert `RULE_THRESHOLD` n'est créé durant cette campagne.
Avec un agent à intervalle 30 s et des runs limités à 45 s, une seule mesure
haute par run a été observée par le moteur ; l'état est ensuite revenu inactif.

Résultat : **FAIL pour la nouvelle alerte de règle dans cette campagne**, avec
cause connue liée à l'échantillonnage et à l'évaluation périodique. L'ancienne
alerte CPU résolue du 27 août ne constitue pas une preuve pour ce test. La
recommandation CPU spécifique n'est donc pas régénérée ici.

### Isolation Forest

Une anomalie non synthétique est créée pour la fenêtre 23:20Z :

```text
stress start: 23:20:42Z
anomaly detected: 23:21:30Z
detection latency: ~48 s
score: 0.027621
threshold: 3.469446951953614e-17
window CPU feature: 21.47 %
model: iforest-20260827T234946-0dbe1975 (#6)
```

Le flux réel Metric → PostgreSQL → features → Isolation Forest → Anomaly →
alerte ML → recommandation générique → notification est observé. Cependant le
modèle marque aussi anormales des fenêtres CPU à 2,2 %, 5 % ou 7,7 %. Seulement
35 fenêtres ont servi à son entraînement et il n'existe pas de vérité terrain.
La causalité « CPU élevé → anomalie ML » reste donc **PARTIAL**.

Un autre défaut scientifique est observé : les analyses rescannent une journée,
et une exécution peut créer plusieurs événements `alert.updated`. Le premier
email est `SENT` via le backend console ; les suivants sont `SUPPRESSED` par le
cooldown. `SENT` ne prouve pas une livraison SMTP externe.

### Tendance

L'analyse 2 h retourne pour le CPU :

```text
trend: INCREASING
sample_count: 90
rolling_average: 18.36 %
rate_of_change_per_hour: +14.36
risk_score: 70
estimated threshold breach: 2026-08-30T00:59:40Z
confidence: LOW
is_estimate: true
```

La fonctionnalité travaille sur les données réelles et présente correctement le
résultat comme une estimation. La confiance faible doit rester visible.

## RTX 5070 réelle

Le collecteur Windows utilise `nvidia-smi` et envoie
`system.gpu.utilization`; la VRAM utilisée/totale est conservée dans metadata.
La température et la puissance ne sont pas envoyées par l'agent, mais ont été
surveillées directement par le garde du banc.

### Charge CUDA

| Duty cible | Utilisation max | VRAM | Température max | Puissance max | API | Throttling |
|---:|---:|---:|---:|---:|---:|---|
| 40 % | 35 % | 254 MiB | 66 °C | 50,25 W | 37/37 | aucun |
| 70 % | 66 % | 254 MiB | 74 °C | 74,0 W | 38/38 | aucun |

Au second palier, l'agent réel écrit :

```text
23:35:28Z system.gpu.utilization = 63 %
memory_used_mib = 254
memory_total_mib = 8151
```

Après arrêt : GPU 0 %, VRAM 0 MiB et aucun ralentissement thermique.

### VRAM

| Fraction | VRAM max | Température max | API | Libération finale |
|---:|---:|---:|---:|---|
| 25 % | 2 174 MiB | 54 °C | 11/11 | 0 MiB après exit |
| 50 % | 4 204 MiB | 53 °C | 11/11 | 0 MiB après exit |

70 % VRAM n'est pas exécuté : la limite volontaire du banc est 50 % afin de
laisser une marge au display Windows.

Le pipeline Isolation Forest n'utilise pas GPU. Résultat strict :

```text
GPU TELEMETRY: PASS pour utilisation + VRAM
GPU TEMPERATURE/POWER IN AGENT: NOT IMPLEMENTED
GPU ML FEATURE: NOT IMPLEMENTED
```

## WebSocket sous charge

Pendant 10 agents accélérés (10,18 req/s, p95 85,7 ms, 0 % d'erreur), la sonde
réelle observe :

```json
{
  "multiple_clients": 2,
  "broadcast_sequence_match": true,
  "replay_after_disconnect": true,
  "reused_ticket_http_status": 403
}
```

Cela valide deux clients, diffusion live, replay après déconnexion et ticket
one-shot. Ce n'est pas un benchmark WebSocket de centaines de clients ; le
replay reste plafonné à 500 événements.

## PostgreSQL, Redis et Celery

- PostgreSQL : PASS nominal à 250 agents ; PARTIAL en capacité accélérée à cause
  de `max_connections=100` atteint à 50 agents.
- Redis : reste sain ; 397 ops/s et 7,50 MiB max au run accéléré ; aucune
  éviction ou erreur observée.
- Celery : worker et Beat restent healthy ; file max 3 au run accéléré, puis 0.
  L'ingestion métrique est majoritairement synchrone : cette campagne ne prouve
  ni un restart worker sous charge ni les retries d'une tâche défaillante.

## Récupération

Après arrêt des charges :

- API : 12/12 HTTP 200, p50 19,61 ms, p95/max 152,98 ms ;
- CPU : moyenne 11,8 %, max 20 % sur le cooldown, puis dernière mesure agent à 6,6 % ;
- RAM : 51,5 % sur la dernière mesure agent ;
- GPU : 0 %, VRAM 0 MiB, 52 °C ;
- LEGION : `ONLINE`, heartbeat et métriques continuent ;
- PostgreSQL : 10 connexions dont 1 active ;
- files `celery`, `ml`, `notifications`, `vmware`, `hyperv`, `reports` : toutes 0 ;
- six conteneurs : `healthy`.

Le moteur de règles CPU revient inactif. En revanche trois alertes ML HIGH
restent ouvertes, dont une créée à 23:31Z et encore mise à jour par des fenêtres
de CPU faible. La récupération infrastructure est PASS, mais la récupération
de classification ML est **FAIL/PARTIAL** : le risque de faux incident permanent
est réel.

## Défauts trouvés pendant le test

1. **HIGH — saturation PostgreSQL** : 74 HTTP 500 au run final de 50 agents
   accélérés, connexions 100/100. Ajouter un pooler (PgBouncer), réduire la
   durée de vie des connexions et dimensionner workers/connexions ensemble avant
   d'augmenter `max_connections`.
2. **HIGH — faux positifs ML et récupération** : seuil presque nul, 35 fenêtres
   seulement, alertes ouvertes sur faible charge. Recalibrer avec dataset réel
   plus long, vérité terrain, validation temporelle et métriques de faux positifs.
3. **HIGH — règle de durée dépendante du sampling** : les pics réels courts ne
   satisfont pas la règle 30 s avec collecte 30 s + évaluation 60 s. Évaluer la
   durée sur l'historique des métriques plutôt que seulement l'état périodique.
4. **MEDIUM — événementiel ML bruyant** : une analyse peut produire de nombreux
   `alert.updated`; l'anti-spam email fonctionne, mais DB/WebSocket reçoivent les
   événements. Corréler par run/fenêtre et limiter les mises à jour durables.
5. **MEDIUM — télémétrie GPU incomplète** : température, puissance, clocks et
   throttling ne sont pas normalisés ; GPU absent du modèle ML.
6. **MEDIUM — portabilité modèle** : l'artefact actif existe dans le volume
   worker Docker mais pas dans le `model_store` local de l'hôte.
7. **MEDIUM — service Windows non validé** : l'agent réel tourne comme processus,
   pas comme Windows Service installé sur ce laptop.
8. **LOW — limite du générateur** : un thread OS par agent peut fausser un test
   500 agents. Une future version devrait utiliser un client asynchrone borné.

Deux bugs du banc ont été trouvés et corrigés pendant l'exécution : variable de
stage incorrecte dans le gate, puis cleanup non transactionnel/incompatible avec
les FK protégées et les `TaskRun` concurrents. Le rapport est désormais persisté
après chaque palier et le cleanup ordonné est verrouillé.

## Matrice finale

| Validation | Verdict | Preuve / limite |
|---|---|---|
| HTTP HEAVY LOAD | PARTIAL | 25 agents accélérés sans erreur ; 50 à 2,424 % d'erreurs |
| 50 AGENTS | PASS | profil 30 s, 0 %, p95 86,5 ms |
| 100 AGENTS | PASS | profil 30 s, 0 %, p95 78,8 ms |
| 250 AGENTS | PASS | profil 30 s, 0 %, p95 86,2 ms |
| 500 AGENTS | NOT TESTED | optionnel ; générateur thread-per-agent |
| CPU TELEMETRY REAL | PASS | agent : 55,5 %, 84,3 %, puis 4,6 % |
| CPU HIGH LOAD | PARTIAL | 77,3 % moyen, guard à 86,3 % ; température CPU indisponible |
| CPU ML ANOMALY | PARTIAL | anomalie réelle en 48 s, mais faux positifs au repos |
| CPU TREND/PREDICTION | PARTIAL | trend/risk/ETA réels, confiance LOW |
| RTX 5070 TELEMETRY | PARTIAL | utilisation + VRAM PASS ; température/puissance agent absentes |
| GPU LOAD | PASS | 66 %, 74 °C, aucun throttling |
| GPU VRAM | PASS | 4 204 MiB, libération à 0 MiB |
| GPU ML ANOMALY | NOT IMPLEMENTED | GPU absent des features Isolation Forest |
| CPU + GPU COMBINED | NOT TESTED | température CPU non disponible |
| API + SYSTEM COMBINED LOAD | NOT TESTED | 50 agents accélérés déjà en erreur ; pas d'escalade sûre |
| WEBSOCKET UNDER LOAD | PASS | deux clients, broadcast, replay, ticket rejeté |
| POSTGRESQL UNDER LOAD | PARTIAL | nominal PASS ; 100 connexions atteintes en accéléré |
| REDIS UNDER LOAD | PASS | sain, files drainées |
| CELERY UNDER LOAD | PARTIAL | file 3→0 ; restart/retry défaillant non testé ici |
| RECOVERY | PARTIAL | ressources/API PASS ; alertes ML persistantes |

Valeurs de synthèse demandées :

```text
Maximum API throughput observed: 50.868 req/s
p50: 92.942 ms
p95: 203.233 ms
p99: 474.213 ms
error rate: 2.424 %

Maximum zero-error API throughput: 25.416 req/s

Maximum CPU: 86.3 %
Maximum CPU temperature: UNAVAILABLE

Maximum GPU utilization: 66 %
Maximum GPU temperature: 74 °C
Maximum VRAM usage: 4204 MiB
```

## Commandes reproductibles

```powershell
# Capacité accélérée
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\run-performance-test.ps1 `
  -Stages '10,25,50' -DurationSeconds 60 -WarmupSeconds 15 `
  -IntervalSeconds 1 -HeartbeatIntervalSeconds 60 -CooldownSeconds 30

# Agents périodiques
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\run-performance-test.ps1 `
  -Stages '50,100,250' -DurationSeconds 60 -WarmupSeconds 15 `
  -IntervalSeconds 30 -HeartbeatIntervalSeconds 60 -CooldownSeconds 30

# CPU borné
.\.venv\Scripts\python.exe .\tests\load\controlled_cpu_load.py `
  --workers 16 --duration 45 --label CONTROLLED_TEST_CPU_STAGE_1 `
  --output runtime\performance\controlled-cpu-stage-1.json

# GPU CUDA borné — utiliser le Python système qui possède torch CUDA
python.exe .\tests\load\controlled_gpu_load.py `
  --mode compute --duration 20 --duty-cycle .70 --stop-temperature 78 `
  --label CONTROLLED_TEST_GPU_COMPUTE_70 `
  --output runtime\performance\controlled-gpu-compute-70.json

# Validation Django/scripts
. .\scripts\common.ps1
Import-DotEnv 'backend\.env'
.\.venv\Scripts\python.exe backend\manage.py check
.\.venv\Scripts\python.exe -m py_compile `
  scripts\performance\load_test.py `
  tests\load\controlled_cpu_load.py `
  tests\load\controlled_gpu_load.py
git diff --check
```

Rapports JSON bruts : `runtime/performance/` (répertoire runtime, non destiné au
commit). Les principales preuves sont `P2420260830001012.json` pour la capacité,
`P2420260830004108.json` pour 250 agents, ainsi que les fichiers
`controlled-cpu-*` et `controlled-gpu-*`.
