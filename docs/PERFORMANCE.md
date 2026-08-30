# Tests de charge et scalabilité
## Statut

La Phase 24 a été exécutée localement le 25 août 2026. Une remédiation ciblée des
connexions PostgreSQL a ensuite été validée le 30 août 2026. Deux profils initiaux
ont été mesurés avec le même banc reproductible :

- un profil nominal avec 100 agents, une collecte toutes les 30 secondes et un
  heartbeat toutes les 60 secondes ;
- un profil de stress progressif avec 1, 10, 25, 50 puis 100 agents et une collecte
  par seconde.

Le profil nominal atteint **5,00 requêtes/s, 82,17 ms de latence p95 et 0 %
d'erreur**. Le profil accéléré reste sans erreur jusqu'au palier court de 25
agents (25,82 requêtes/s), puis sature les 100 connexions PostgreSQL : 9,35 %
d'erreurs à 50 agents et 69,92 % à 100 agents.

Ces mesures initiales qualifient l'environnement local testé. Elles ne constituent
pas une certification de capacité de production. Aucune optimisation applicative
ou d'infrastructure n'avait été appliquée pendant la Phase 24 initiale. La section
« Remédiation PostgreSQL » isole les mesures prises après l'activation du pool.

## Environnement mesuré

| Composant | Configuration réellement testée |
|---|---|
| Hôte | Lenovo 83LY, Windows 11 Pro build 26200, 32 CPU logiques, 31,73 Gio RAM |
| Backend | un processus Daphne dédié, `DEBUG=False`, Python 3.14.6, Django 6.0.8 |
| PostgreSQL | 17.11 Alpine dans Docker, `max_connections=100`, aucune limite CPU/RAM Docker |
| Connexions Django initiales | `POSTGRES_CONN_MAX_AGE=60`, sans pool borné |
| Connexions Django après remédiation | `POSTGRES_CONN_MAX_AGE=0`, pool psycopg `min_size=0`, `max_size=20` |
| Redis | 7.4.11 Alpine dans Docker, aucune limite CPU/RAM Docker |
| Celery | worker et Beat existants connectés au Redis partagé |
| Réseau | boucle locale HTTP, sans TLS, reverse proxy, DNS ni latence WAN |

PostgreSQL et Redis étaient partagés avec les processus locaux déjà actifs de
la plateforme. Les connexions et quelques tâches Celery de fond font donc partie
du bruit de base mesuré. Le backend de charge, lui, était un nouveau processus
Daphne, chauffé par le healthcheck avant le premier palier.

## Banc de test

Les fichiers suivants rendent le test reproductible :

- `scripts/performance/load_test.py` : provisionnement, charge HTTP, mesures et
  nettoyage ;
- `scripts/run-performance-test.ps1` : chargement de la configuration, démarrage
  du Daphne dédié, healthcheck et arrêt garanti du processus ;
- les rapports JSON bruts sont générés sous `runtime/performance/`. Ce répertoire
  est volontairement ignoré par Git.

### Charge produite

Le banc crée un customer et un environnement isolés, puis de vrais enregistrements
Agent/Machine avec identité et jeton distincts. Le jeton reste en mémoire et n'est
pas écrit dans le rapport. Chaque source appelle les vrais endpoints :

- `POST /api/agent/heartbeat/` ;
- `POST /api/agent/metrics/`.

Chaque lot contient 12 mesures Windows normalisées : CPU, RAM, occupation et
espace disque libre, lectures/écritures disque, réseau entrant/sortant, latence,
uptime, nombre de processus et état du service `W32Time`. Les valeurs suivent des
plages, vagues et variations déterministes plausibles. Ce sont des **données
synthétiques**, pas des observations provenant d'hôtes réels.

Le modèle est fermé : un agent ne garde qu'une requête en vol et attend sa réponse.
Le démarrage est réparti aléatoirement sur un intervalle de collecte pour éviter
une rafale artificielle unique. Les clés d'idempotence sont uniques par exécution,
palier, agent, séquence et métrique.

### Throttle du benchmark

`AgentRequestThrottle` utilise actuellement l'adresse IP et la limite par défaut
est `120/min`. Les 100 agents locaux partagent `127.0.0.1`; garder cette limite
aurait mesuré des réponses 429 du throttle au lieu de la capacité d'ingestion.
Seul le processus Daphne dédié a donc reçu `AGENT_REQUEST_RATE=100000/min`.

Cette valeur n'est pas une recommandation de production et ne doit pas être copiée
dans un déploiement. Le serveur applicatif normal n'a pas été reconfiguré.

### Mesures collectées

- débit HTTP, statuts, taux d'erreur et latences p50/p95/p99 ;
- latence de traitement des métriques, calculée dans PostgreSQL par
  `received_at - timestamp` ;
- CPU, RSS et nombre de threads du processus backend ;
- CPU et mémoire globaux de l'hôte ;
- transactions, insertions, connexions totales/actives, cache, fichiers temporaires,
  deadlocks et croissance de PostgreSQL ;
- commandes, mémoire et clients Redis ;
- longueurs des files Redis `celery` et `hyperv`.

Le pourcentage CPU d'un processus peut dépasser 100 % sur une machine multicœur :
146 % correspond approximativement à l'utilisation de 1,46 cœur, pas à 146 %
de la machine entière.

## Résultat à cadence nominale

Rapport de référence local : `runtime/performance/P2420260825025603.json`.

| Agents | Intervalle métriques | Requêtes | Débit | Erreurs | p50 | p95 | p99 | Métriques acceptées |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | 30 s | 300 | 5,00 req/s | 0,00 % | 57,93 ms | 82,17 ms | 104,69 ms | 2 400 |

Les 300 requêtes comprennent 100 heartbeats en HTTP 200 et 200 lots de métriques
en HTTP 202. La durée réelle du palier est de 60,04 secondes.

| Mesure de ressource | Valeur |
|---|---:|
| Latence de traitement des métriques p95 / p99 | 61,73 / 69,66 ms |
| CPU backend moyen / p95 | 11,86 / 24,60 % |
| RSS backend maximale | 244,19 Mio |
| CPU hôte moyen | 5,28 % |
| Lignes de métriques PostgreSQL | 39,97/s |
| Transactions PostgreSQL | 36,03/s |
| Connexions PostgreSQL totales / actives max | 40 / 2 |
| Croissance DB pendant le palier | 1,016 Mio |
| Cache PostgreSQL / temp / deadlocks | 100 % / 0 octet / 0 |
| Commandes Redis / pic instantané | 36,53/s / 76/s |
| Mémoire Redis maximale | 4,275 Mio |
| Clients Redis maximum | 71 |
| File Celery maximum / Hyper-V maximum | 4 / 0 |

La file Celery observée correspond aux tâches périodiques de la plateforme, pas
à l'ingestion HTTP, qui reste synchrone. Les files `celery` et `hyperv` ont toutes
deux été vérifiées à 0 après le test.

## Résultats du stress progressif

Rapport de référence local : `runtime/performance/P2420260825025812.json`.
Chaque agent envoie ici un lot de 12 métriques par seconde pendant 30 secondes,
soit une fréquence 30 fois supérieure à la configuration nominale de l'agent.

| Agents | Requêtes | Débit | Erreurs | HTTP 500 | p50 | p95 | p99 | Traitement p95 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 31 | 1,03/s | 0,00 % | 0 | 63,48 ms | 81,89 ms | 92,49 ms | 68,02 ms |
| 10 | 310 | 10,33/s | 0,00 % | 0 | 57,11 ms | 81,30 ms | 94,29 ms | 63,56 ms |
| 25 | 775 | 25,82/s | 0,00 % | 0 | 62,88 ms | 87,34 ms | 98,77 ms | 66,47 ms |
| 50 | 1 541 | 51,22/s | 9,35 % | 144 | 113,05 ms | 333,12 ms | 481,14 ms | 178,92 ms |
| 100 | 2 031 | 65,42/s | 69,92 % | 1 420 | 1 460,89 ms | 2 259,02 ms | 2 648,25 ms | 803,82 ms |

Le débit constaté à 100 agents n'est pas un débit utile : la majorité des
requêtes échoue. Le dernier palier court sans erreur est 25 agents/25,82 req/s ;
cela ne prouve pas que ce niveau soit soutenable sur une longue durée.

### Ressources pendant le stress

| Agents | CPU backend | RSS max | CPU hôte | Conn. PG totales/actives | Métriques/s | Cmd Redis/s | Redis max | Clients Redis | File Celery max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 2,93 % | 241,79 Mio | 4,06 % | 29 / 1 | 12,00 | 15,17 | 4,04 Mio | 54 | 0 |
| 10 | 23,95 % | 243,68 Mio | 5,70 % | 37 / 3 | 119,99 | 70,83 | 4,40 Mio | 70 | 1 |
| 25 | 59,23 % | 249,47 Mio | 8,62 % | 83 / 3 | 299,87 | 162,30 | 5,33 Mio | 122 | 0 |
| 50 | 126,88 % | 261,83 Mio | 17,26 % | 100 / 3 | 539,69 | 301,85 | 8,40 Mio | 187 | 2 |
| 100 | 146,67 % | 321,68 Mio | 17,95 % | 100 / 5 | 206,40 | 303,52 | 14,98 Mio | 482 | 6 |

Le recul des insertions à 100 agents provient des requêtes rejetées, pas d'une
amélioration de rendement. La mémoire Redis et ses commandes restent faibles dans
le contexte de l'hôte testé, mais le nombre de clients Redis passe de 54 à 482 et
devra être surveillé lors d'un dimensionnement multi-worker.

## Bottleneck démontré

Les 1 564 réponses HTTP 500 des paliers 50 et 100 correspondent exactement à
1 564 traces `django.db.utils.OperationalError` dans le journal du Daphne de test.
Elles se terminent toutes par :

```text
FATAL: sorry, too many clients already
```

Les éléments convergents sont :

- PostgreSQL est configuré à 100 connexions maximum ;
- le maximum observé atteint 100 connexions à 50 et 100 agents ;
- seules 3 puis 5 connexions sont actives au pic mesuré ;
- Django conserve les connexions jusqu'à 60 secondes ;
- le processus atteint 88 threads à 50 agents et 185 à 100 agents ;
- le CPU global de l'hôte reste sous 18 %, le cache PostgreSQL reste à 100 %, et
  aucun deadlock ni fichier temporaire n'est observé.

Le premier plafond initial était donc le **budget de connexions PostgreSQL**, en particulier
l'accumulation de connexions persistantes dans les threads synchrones, et non la
puissance CPU globale, Redis ou la file Celery. Le test en escalier réutilise le
même processus backend entre les paliers : il montre le comportement cumulatif
d'un service chauffé, mais ne donne pas la capacité isolée d'un processus neuf pour
chaque palier.

Un deuxième risque de configuration existe : le throttle IP `120/min` peut regrouper
des agents distincts derrière le même NAT. Cent agents nominaux représentent environ
300 requêtes/minute ; ils pourraient donc être limités bien avant la base si leur IP
publique est commune.

## Remédiation PostgreSQL — 30 août 2026

La remédiation remplace les connexions persistantes par thread par le pool intégré
à psycopg :

```dotenv
POSTGRES_CONN_MAX_AGE=0
POSTGRES_CONN_HEALTH_CHECKS=true
POSTGRES_POOL_ENABLED=true
POSTGRES_POOL_MIN_SIZE=0
POSTGRES_POOL_MAX_SIZE=20
POSTGRES_POOL_TIMEOUT=10
POSTGRES_POOL_MAX_IDLE=60
```

La dépendance installée est `psycopg[binary,pool]==3.3.4`. Le pool est borné par
processus Django. Le total global doit donc toujours être dimensionné en fonction
du nombre de processus API, de workers Celery et des autres consommateurs.

### Mesures brutes avant/après

Le profil est accéléré à un lot de métriques par seconde. Le rapport « avant » a
mesuré chaque palier pendant environ 60 secondes. Les rapports « après » utilisent
30 secondes de mesure après 10 secondes de chauffe. Les résultats ne constituent
donc pas une comparaison de durée strictement identique ; ils démontrent en
revanche le comportement de connexion et d'erreur à la même cadence par agent.

| État | Rapport | Agents | Débit | p50 | p95 | p99 | Erreurs | Connexions PG max | Actives max |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Avant | `P2420260830001012.json` | 10 | 10,199 req/s | 62,708 ms | 107,247 ms | 142,499 ms | 0 % | 54 | 3 |
| Avant | `P2420260830001012.json` | 25 | 25,416 req/s | 60,559 ms | 84,280 ms | 106,049 ms | 0 % | 80 | 3 |
| Avant | `P2420260830001012.json` | 50 | 50,868 req/s | 92,942 ms | 203,233 ms | 474,213 ms | **2,424 %** | **100** | 4 |
| Après | `P2420260830104017.json` | 25 | 25,071 req/s | 56,113 ms | 88,803 ms | 101,825 ms | 0 % | 11 | 2 |
| Après | `P2420260830104017.json` | 50 | 50,042 req/s | 195,354 ms | 446,830 ms | 536,551 ms | 0 % | 24 | 3 |
| Après | `P2420260830104017.json` | 100 | 52,372 req/s | 1 920,482 ms | 2 230,941 ms | 2 396,287 ms | 0 % | 24 | 6 |
| Après | `P2420260830104422.json` | 250 | 55,071 req/s | 4 734,565 ms | 5 210,206 ms | 5 283,541 ms | 0 % | 24 | 3 |

Au palier de 50 agents avant correction, 74 requêtes ont reçu HTTP 500 lorsque
PostgreSQL a atteint 100 connexions. Après correction, aucune requête n'échoue sur
les quatre paliers rejoués et le maximum reste à 24 connexions. L'épuisement des
connexions est donc corrigé dans cet environnement.

Le débit utile plafonne toutefois entre 52,372 et 55,071 requêtes/s aux paliers de
100 et 250 agents, tandis que le p95 monte respectivement à 2 230,941 ms et
5 210,206 ms. Le pool applique désormais une contre-pression au lieu de laisser
PostgreSQL épuiser ses connexions ; la concurrence ASGI et la latence deviennent
les prochaines limites à traiter. Ces paliers accélérés ne sont pas une cadence
agent recommandée.

## Volume et rétention

Au profil nominal, 100 agents produisent environ 3 456 000 lignes de métriques par
jour (12 métriques toutes les 30 secondes). La croissance courte observée, 1,016
Mio pour 2 400 lignes et les événements associés, extrapole grossièrement à 1,4 Gio
par jour.

Cette extrapolation n'est pas une prévision de stockage : elle ne couvre ni vacuum,
fragmentation, compression, variation des metadata, rétention, agrégation ni
croissance des index sur une longue période. Elle justifie toutefois de tester une
politique de rétention avant un déploiement prolongé.

## Recommandations après remédiation

1. **Dimensionner le budget de connexions avant toute montée en charge.** Définir
   explicitement la somme des connexions API, Daphne, Celery, Beat, outils
   d'administration et marge de secours. Ne pas se limiter à augmenter
   `max_connections`.
2. **Conserver et surveiller le pool psycopg borné.** Le couple
   `CONN_MAX_AGE=0`/pool max 20 a supprimé l'épuisement local. Mesurer le temps
   d'attente d'acquisition et recalculer le budget pour chaque nouvelle réplique.
   PgBouncer ne devient pertinent qu'après une validation dédiée d'une architecture
   multi-processus ou multi-hôte.
3. **Borner la concurrence applicative.** Aligner threads/processus Daphne et workers
   Celery sur le pool DB, ajouter une contre-pression, et renvoyer un 503 contrôlé
   avec retry plutôt qu'un 500 lorsque la DB est temporairement indisponible.
4. **Rendre le throttle agent compatible avec le NAT.** Après authentification,
   envisager une clé par agent et/ou customer tout en conservant une protection IP
   pour enrollment et attaques non authentifiées. Cette modification doit avoir ses
   propres tests de sécurité et de charge.
5. **Surveiller les clients Redis.** Vérifier la réutilisation des connexions du
   channel layer et dimensionner les limites de descripteurs avant d'ajouter des
   processus API ou WebSocket.
6. **Définir rétention et agrégation des métriques.** Tester partitionnement temporel,
   purge, agrégats et sauvegardes sur un jeu de plusieurs jours avant de choisir une
   solution.
7. **Compléter la campagne avant production.** Exécuter un soak test de 2 à 24 h,
   isoler chaque palier avec un processus neuf, distribuer les générateurs sur
   plusieurs hôtes, ajouter TLS/reverse proxy/WAN, plusieurs tenants, clients
   WebSocket, collectes VMware/Hyper-V et charges ML/notifications concurrentes.
8. **Fixer des SLO.** Définir le p95/p99 maximal, le taux d'erreur acceptable et le
   retard maximum de traitement avant de déclarer une capacité supportée.

Le découplage systématique de l'ingestion vers Celery n'est pas recommandé sur la
base de ces seuls résultats : Redis et la file ne sont pas le plafond observé, et
une file introduirait de nouveaux compromis de durabilité et de latence. Le budget
de connexions est maintenant borné et re-mesuré ; la prochaine validation doit
cibler la contre-pression et la concurrence ASGI.

## Limites de la campagne

- durée courte, sans endurance, fuite lente ni comportement après plusieurs jours ;
- un seul hôte physique pour générateur, API et Docker ;
- pas de TLS, proxy, latence réseau, perte de paquets ni bande passante contrainte ;
- un seul tenant et des sources Windows synthétiques ;
- VMware, Hyper-V, entraînement ML, notifications massives, rapports et WebSocket
  ne sont pas chargés simultanément ;
- CPU/RAM internes des conteneurs PostgreSQL et Redis non profilés séparément ; leur
  charge est décrite par les compteurs PostgreSQL/Redis et le CPU global de l'hôte ;
- services locaux existants partageant DB/Redis, donc bruit de fond non nul ;
- limite IP agent relevée uniquement dans le processus de benchmark ;
- le palier accéléré est une contrainte artificielle de 30 fois la cadence nominale.

Un contrôle préliminaire a été écarté parce que son chronomètre incluait une
attente après la fin du palier. Le banc a été corrigé pour borner cette attente par
la deadline, puis les profils nominal et progressif ont été rejoués. Seuls les
deux rapports de référence cités ci-dessus alimentent les conclusions.

## Reproduction

Prérequis : `.venv` installé, `backend/.env` configuré pour PostgreSQL et Redis,
conteneurs DB/Redis sains, et port 8010 libre.

La configuration de reproduction doit inclure les variables du pool listées dans
la section « Remédiation PostgreSQL » et la dépendance `psycopg[binary,pool]`.

```powershell
docker compose up -d db redis

# Profil de stress progressif, 30 fois la cadence nominale
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts\run-performance-test.ps1 `
  -Stages 1,10,25,50,100 `
  -DurationSeconds 30 `
  -IntervalSeconds 1 `
  -HeartbeatIntervalSeconds 60 `
  -CooldownSeconds 5 `
  -Port 8010

# Contrôle à la cadence nominale de l'agent
powershell -NoProfile -ExecutionPolicy Bypass `
  -File scripts\run-performance-test.ps1 `
  -Stages 100 `
  -DurationSeconds 60 `
  -IntervalSeconds 30 `
  -HeartbeatIntervalSeconds 60 `
  -CooldownSeconds 0 `
  -Port 8010
```

Le runner refuse SQLite, chauffe l'API, mesure le vrai PID à l'écoute et arrête
le processus Daphne même en cas d'échec. Sauf utilisation directe de
`load_test.py --keep-data`, le tenant et toutes les données de charge sont supprimés
en fin d'exécution. La vérification finale a trouvé 0 customer `perf-*` restant et
aucun listener sur le port 8010.
