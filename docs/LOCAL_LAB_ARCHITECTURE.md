# Architecture du laboratoire local InfraSentinel AI

## Référence officielle

InfraSentinel AI est validé sans dépendance à un fournisseur cloud. Le poste
hôte exécute la plateforme, tandis que les collecteurs autorisés la rejoignent
sur loopback ou sur le réseau local.

```text
Windows Agent ───────────────┐
Hyper-V Collector ──────────┤
VMware Connector ───────────┼── HTTP(S) / LAN ──> Django ASGI API
Simulated Agents ───────────┘                         │
                                                     ├── PostgreSQL
React Dashboard <── HTTP + WebSocket ────────────────┤
                                                     └── Redis
                                                          │
                                             Celery Worker + Beat
                                                          │
                                             Rules / ML / Alerts /
                                             Notifications / History
```

## Déploiements locaux pris en charge

### Développement hybride Windows

PostgreSQL et Redis s'exécutent dans Docker. Django/Daphne, Vite, Celery Worker
et Celery Beat utilisent l'environnement Python local. Les scripts sont :

```powershell
./scripts/start-local.ps1
./scripts/status-local.ps1
./scripts/stop-local.ps1
```

Ce mode est adapté au développement de l'agent et du collecteur Hyper-V sous
Windows. Les journaux de processus sont écrits dans `runtime/`, ignoré par Git.

### Stack Docker complète

`docker-compose.yml` contient PostgreSQL, Redis, migrations, API, worker, Beat
et frontend. Le fichier `.env` racine doit définir trois secrets indépendants :
`DJANGO_SECRET_KEY`, `JWT_SIGNING_KEY` et `POSTGRES_PASSWORD`.

```powershell
docker compose --env-file .env up -d --build --wait
docker compose --env-file .env ps -a
```

La présence d'un conteneur ne suffit pas : `/api/health/` doit confirmer la base
et Redis, et les healthchecks API, worker, Beat et frontend doivent être sains.

## Mode réseau local

Les valeurs de développement restent limitées à `127.0.0.1`. Pour autoriser un
réseau local de confiance, déterminer d'abord l'adresse du poste sans la coder
dans le dépôt :

```powershell
Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.IPAddress -notmatch '^(127|169\.254)\.' }
```

Configurer ensuite les valeurs locales non versionnées. Exemple conceptuel si
l'adresse observée est `192.168.x.x` :

```dotenv
API_BIND_ADDRESS=0.0.0.0
FRONTEND_BIND_ADDRESS=0.0.0.0
ALLOWED_HOSTS=127.0.0.1,localhost,192.168.x.x
FRONTEND_URL=http://192.168.x.x:5173
CORS_ALLOWED_ORIGINS=http://192.168.x.x:5173
CSRF_TRUSTED_ORIGINS=http://192.168.x.x:5173
VITE_API_URL=http://192.168.x.x:8000/api
VITE_WS_URL=ws://192.168.x.x:8000/ws/events/
```

L'agent utilise la même origine via `backend_url` ou
`INFRASENTINEL_SERVER_URL`. Ne jamais ouvrir PostgreSQL (5432) ou Redis (6379)
sur le LAN. Le pare-feu Windows doit limiter 5173/8000 au réseau de laboratoire.
Sur un réseau non maîtrisé, utiliser HTTPS derrière le reverse proxy générique
ou un tunnel/VPN privé; ne pas exposer directement Daphne/Vite à Internet.

## Identités et isolation

- chaque agent possède une identité et un jeton opaque révocable;
- chaque machine appartient à un environnement et à un client;
- les métriques normalisées conservent le type de source et les métadonnées
  spécifiques Windows, VMware ou Hyper-V;
- les APIs, tickets WebSocket, alertes et tâches asynchrones appliquent la portée
  tenant côté serveur;
- un worker Windows distinct consomme la queue `hyperv` lorsqu'une collecte
  Hyper-V réelle est autorisée.

## Données et persistance

PostgreSQL est la base de référence. Redis sert de broker, cache et couche
Channels; il ne remplace jamais la persistance métier. Le volume `model_store`
conserve les artefacts ML et `celerybeat_data` l'état du planificateur. Les
volumes doivent survivre à un redémarrage Compose, puis être couverts par les
tests de sauvegarde/restauration.

## Limites de validation

Une connexion à un vrai vCenter, un hôte Hyper-V autorisé, une livraison SMTP
externe, un poste Windows distant ou un tunnel WAN sont des validations
distinctes. Les mocks prouvent les contrats logiciels mais ne constituent pas
une preuve d'intégration réelle.
