# Dockerisation d'InfraSentinel AI

## Objectif et périmètre

La plateforme complète s'exécute avec Docker Compose sans dépendre d'un PostgreSQL, d'un Redis, d'un Node.js ou d'un Python installés sur l'hôte. Les données persistantes restent dans des volumes Docker. Aucun secret n'est présent dans les images, le fichier Compose ou le fichier d'exemple.

Versions de base verrouillées par digest au 24 août 2026 : Python 3.13 slim, Node.js 22 Alpine, Nginx unprivileged 1.29 Alpine, PostgreSQL 17 Alpine et Redis 7.4 Alpine. Une montée de version doit modifier volontairement le tag et son digest, puis refaire toutes les validations de ce document.

## Architecture

```text
Navigateur
   |
   | http(s), /api et /ws
   v
frontend (Nginx non-root, réseau edge)
   |
   v
api (Django/DRF/Channels/Daphne, réseaux edge + backend)
   |                         |
   v                         v
PostgreSQL                Redis
   ^                    broker/cache/channels/results
   |                         ^
   +---------+---------------+
             |
      worker Celery + Beat

migrate : tâche one-shot exécutée avant api/worker/beat
```

| Service | Responsabilité | Exposition | Persistance | Santé |
|---|---|---|---|---|
| `frontend` | Build React/Vite et service SPA via Nginx | `127.0.0.1:5173` par défaut | aucune | HTTP `/` |
| `api` | API, WebSocket et fichiers statiques | `127.0.0.1:8000` par défaut | modèles ML, statiques | `/api/health/` + DB + Redis |
| `migrate` | `manage.py migrate --noinput` | aucune | PostgreSQL | doit sortir avec le code 0 |
| `db` | PostgreSQL principal | réseau `backend` uniquement | `postgres_data` | `pg_isready` |
| `redis` | broker, résultats, cache et Channels | réseau `backend` uniquement | `redis_data` (AOF + snapshot) | `redis-cli ping` |
| `worker` | Tâches Celery, files `celery` et `hyperv` | réseau `backend` uniquement | modèles ML | `celery inspect ping` |
| `beat` | Planification Celery Beat | réseau `backend` uniquement | `celerybeat_data` | PID actif |

Les réseaux sont séparés : seul le frontend et l'API rejoignent `edge`; PostgreSQL, Redis, worker et Beat restent sur `backend`. PostgreSQL et Redis ne publient aucun port hôte. Les conteneurs applicatifs sont non-root, en lecture seule, sans capacités Linux et avec `no-new-privileges`. Les répertoires réellement écrits utilisent des volumes ou des `tmpfs`.

## Prérequis

- Docker Engine 24+ avec le plugin Docker Compose v2 ;
- au moins 4 Go de mémoire disponibles pour le premier build ML ;
- ports 5173 et 8000 libres, ou ports alternatifs dans `.env`.

Vérification :

```powershell
docker version
docker compose version
```

## Configuration sans secrets dans Git

Copier le modèle racine, jamais le fichier backend de développement :

```powershell
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(64))"
python -c "import secrets; print(secrets.token_urlsafe(64))"
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Reporter les trois valeurs indépendantes dans `DJANGO_SECRET_KEY`, `JWT_SIGNING_KEY` et `POSTGRES_PASSWORD`. `.env` est ignoré par Git. En production, injecter ces valeurs depuis le gestionnaire de secrets de la plateforme plutôt que de conserver un fichier sur disque.

Variables indispensables :

| Variable | Rôle |
|---|---|
| `DJANGO_SECRET_KEY` | signature cryptographique Django, obligatoire |
| `JWT_SIGNING_KEY` | signature JWT indépendante, obligatoire |
| `POSTGRES_PASSWORD` | mot de passe du rôle PostgreSQL, obligatoire |
| `POSTGRES_DB`, `POSTGRES_USER` | base et rôle, valeurs par défaut `infrasentinel` |
| `FRONTEND_URL`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS` | origines exactes du dashboard |
| `ALLOWED_HOSTS` | noms acceptés par Django |
| `API_PORT`, `FRONTEND_PORT` | ports hôte, 8000 et 5173 par défaut |
| `CONNECTOR_ALLOWED_HOSTS` | destinations VMware/Hyper-V autorisées |

Le frontend produit utilise `VITE_API_URL=/api`. Nginx relaie `/api/`, `/ws/` et `/static/` vers l'API : le navigateur n'a donc aucune dépendance à `localhost:8000` et WebSocket reste de même origine.

## Démarrage propre

Valider d'abord l'interpolation, construire, puis attendre tous les healthchecks :

```powershell
docker compose config --quiet
docker compose build
docker compose up -d --wait --wait-timeout 300
docker compose ps
docker compose logs migrate
```

Résultat attendu :

- `migrate` est `Exited (0)` ;
- `db`, `redis`, `api`, `worker`, `beat` et `frontend` sont `healthy` ;
- dashboard : `http://127.0.0.1:5173/` ;
- API : `http://127.0.0.1:8000/api/health/` ;
- Swagger : `http://127.0.0.1:5173/api/docs/` pour un administrateur.

Les migrations sont réexécutables et précèdent automatiquement l'API et les workers. Un échec de migration bloque leur démarrage au lieu de lancer l'application avec un schéma incomplet.

## Création initiale du premier client

L'inscription publique est désactivée par défaut. Sur une installation vide, la procédure contrôlée est :

1. mettre temporairement `PUBLIC_REGISTRATION_ENABLED=true` et
   `VITE_PUBLIC_REGISTRATION_ENABLED=true` dans `.env` ;
2. reconstruire le dashboard avec `docker compose build frontend` ;
3. recréer l'API et le dashboard avec
   `docker compose up -d --force-recreate --wait api frontend` ;
4. créer le premier client administrateur depuis la page d'inscription ;
5. remettre immédiatement les deux variables à `false` ;
6. reconstruire le dashboard puis recréer `api` et `frontend` avec les mêmes
   commandes.

Ne pas laisser l'inscription ouverte sur une plateforme exposée.

## Exploitation

```powershell
# Suivre les composants applicatifs
docker compose logs -f api worker beat frontend

# Vérifier le schéma sans le modifier
docker compose exec -T api python manage.py migrate --check

# Vérifier PostgreSQL et Redis sans publier leurs ports
docker compose exec -T db pg_isready -U infrasentinel -d infrasentinel
docker compose exec -T redis redis-cli ping

# Redémarrer un worker et attendre son retour en santé
docker compose restart worker
docker compose up -d --wait worker

# Arrêter en conservant les données
docker compose down
```

`docker compose down -v` supprime définitivement la base, le cache persistant, les modèles et le calendrier Beat. Cette commande est réservée aux environnements jetables après vérification exacte du projet Compose ciblé.

Les sauvegardes et restaurations PostgreSQL sont détaillées dans `docs/DATABASE.md`. Une sauvegarde de production doit être testée par restauration, stockée hors de l'hôte Docker et chiffrée.

## HTTPS et production

En développement, les ports du frontend, de l'API, de PostgreSQL et de Redis sont
liés à `127.0.0.1` par défaut. Cela permet aux processus Python lancés par
`scripts/start-local.ps1` de joindre les conteneurs DB/Redis sans les exposer au
réseau. L'overlay `docker-compose.prod.yml` supprime explicitement les publications
5432 et 6379. Pour une exposition applicative, placer un reverse proxy TLS devant
le frontend et configurer au minimum :

```dotenv
FRONTEND_URL=https://infrasentinel.example
ALLOWED_HOSTS=infrasentinel.example
CORS_ALLOWED_ORIGINS=https://infrasentinel.example
CSRF_TRUSTED_ORIGINS=https://infrasentinel.example
SESSION_COOKIE_SECURE=true
CSRF_COOKIE_SECURE=true
JWT_REFRESH_COOKIE_SECURE=true
SECURE_SSL_REDIRECT=true
TRUST_X_FORWARDED_PROTO=true
SECURE_HSTS_SECONDS=31536000
```

Ne publier directement ni PostgreSQL ni Redis. Restreindre `CONNECTOR_ALLOWED_HOSTS`, conserver `ALLOW_INSECURE_CONNECTOR_TLS=false` et utiliser un backend SMTP réel pour les notifications.

## Validation automatisée

Suite backend complète sur PostgreSQL Docker, avec les fonctions publiques et l'origine du scénario activées seulement dans le processus de test :

```powershell
docker compose exec -T `
  -e PUBLIC_REGISTRATION_ENABLED=true `
  -e API_DOCS_PUBLIC=true `
  -e CHANNEL_LAYER=memory `
  -e CELERY_TASK_ALWAYS_EAGER=true `
  -e CORS_ALLOWED_ORIGINS=http://127.0.0.1:5173,http://localhost:5173 `
  api python manage.py test --verbosity 1
```

Frontend :

```powershell
Set-Location frontend
npm ci
npm test -- --run
npm run lint
npm run build
```

Contrôles fonctionnels minimaux :

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health/
Invoke-RestMethod http://127.0.0.1:5173/api/health/
Invoke-WebRequest http://127.0.0.1:5173/login -UseBasicParsing
docker compose exec -T api python manage.py migrate --check
docker compose exec -T redis redis-cli ping
docker compose exec -T worker celery -A config inspect active_queues --timeout=10
```

## Preuve de validation de la Phase 21

Validation réalisée les 24, 25 et 26 août 2026 avec Docker Engine 29.6.2 et Compose 5.3.1 sur un projet et des volumes neufs, avec des ports de test isolés `15173/18000` :

| Contrôle | Résultat |
|---|---|
| Construction backend + frontend depuis zéro | réussie |
| Démarrage `up -d --wait` | 6 services durables `healthy`, migration `Exited (0)` |
| Migrations PostgreSQL vides | 50 migrations appliquées, `migrate --check` réussi |
| API directe et via Nginx | HTTP 200, `database=ok`, `redis=ok` |
| Résilience du healthcheck | 70 appels consécutifs HTTP 200, sans throttle métier |
| Dashboard `/login` | HTTP 200, SPA chargée |
| Redis | `PONG` |
| Celery | tâche réelle réussie, résultat `{'triggered': 0}` |
| Files worker | `celery` et `hyperv` actives |
| Redémarrage worker | retour à `healthy` réussi |
| Backend PostgreSQL/Redis | 186 découverts : 183 réussis, 3 ignorés, 0 échec |
| Intégration Redis/broker | 3 tests supplémentaires réussis |
| Frontend | 18 tests réussis |
| ESLint | réussi, zéro avertissement |
| Utilisateurs runtime | API/worker UID 10001, frontend UID 101 |

Les six tests ignorés dans le passage global sont les deux collectes externes VMware/Hyper-V, la livraison SMTP externe et trois scénarios Redis conditionnels. Ces trois scénarios Redis ont ensuite été activés séparément contre le conteneur réel et ont tous réussi (connexion/reconnexion, aller-retour broker et indisponibilité temporaire). Aucun environnement VMware, Hyper-V ou SMTP réel n'était fourni et aucune donnée de ces systèmes n'a été inventée.
