# Déploiement d'InfraSentinel AI

## Stratégie retenue

La stratégie retenue est un **VPS Docker mono-hôte** avec un domaine public et Caddy comme terminaison HTTPS :

```text
Agents Windows ───────────────────────────────┐
Navigateurs ──────────────────────────────────┤ HTTPS 443
                                              v
Internet -> DNS -> VPS -> Caddy -> Nginx/React -> Django/Channels
                                          |              |
                                          |              +-> PostgreSQL
                                          |              +-> Redis
                                          |              +-> Celery Worker / Beat
                                          +-> WebSocket
```

Cette stratégie réutilise les images de la Phase 21, conserve l'API et le WebSocket sous le même domaine que le dashboard et évite de multiplier les fournisseurs, les règles CORS et les chemins réseau. Elle est adaptée à un PFE et à une première production de taille modérée.

Ce déploiement reste mono-hôte : le VPS est un point unique de défaillance. Une évolution à haute disponibilité devra déplacer PostgreSQL vers un service managé, externaliser Redis et les modèles ML, utiliser un registre d'images et placer plusieurs API/workers derrière un load balancer.

## Composants de production

- `docker-compose.yml` : services applicatifs communs ;
- `docker-compose.prod.yml` : overlay de production, Caddy, HTTPS et durcissement ;
- `deploy/Caddyfile` : certificat automatique, redirection HTTPS et reverse proxy ;
- `.env.production.example` : contrat de configuration sans secret ;
- `scripts/backup-postgres.sh` : dump PostgreSQL atomique avec checksum ;
- `docs/DOCKER.md` : fonctionnement détaillé des conteneurs.

Seuls les ports 80/TCP, 443/TCP et 443/UDP sont publiés. Django, Nginx, PostgreSQL et Redis ne sont pas directement accessibles depuis Internet.

## Prérequis du VPS

Dimension de départ raisonnable pour un environnement PFE : 4 vCPU, 8 Go de RAM et 80 Go de SSD. La rétention des métriques et les entraînements ML peuvent imposer davantage de stockage ou de mémoire.

Le VPS doit disposer de :

- Linux 64 bits maintenu ;
- Docker Engine et Docker Compose v2 ;
- Git et un client SSH ;
- horloge synchronisée ;
- sauvegarde externe ou stockage objet distinct du VPS.

Pare-feu recommandé :

| Port | Source | Usage |
|---|---|---|
| 22/TCP | adresses administrateur/VPN uniquement | administration SSH |
| 80/TCP | Internet | validation ACME et redirection HTTPS |
| 443/TCP | Internet et réseaux agents | dashboard, API et WebSocket |
| 443/UDP | Internet et réseaux agents | HTTP/3, facultatif |

Ne pas ouvrir 5173, 8000, 5432 ou 6379.

## Domaine et DNS

Exemple de domaine : `monitoring.example.com`.

1. créer un enregistrement `A` vers l'IPv4 publique du VPS ;
2. créer un enregistrement `AAAA` seulement si IPv6 est correctement filtré et routé ;
3. utiliser temporairement un TTL de 300 secondes pendant la mise en service ;
4. vérifier que les ports 80 et 443 atteignent directement le VPS ;
5. ne pas placer de proxy CDN devant Caddy lors de la première validation.

Contrôles possibles :

```bash
dig +short A monitoring.example.com
dig +short AAAA monitoring.example.com
curl -I http://monitoring.example.com
curl -fsS https://monitoring.example.com/api/health/
```

Caddy obtient et renouvelle automatiquement le certificat public. `ACME_EMAIL` doit être une adresse réellement surveillée. Les volumes `caddy_data` et `caddy_config` conservent les certificats et l'état ACME.

## Variables d'environnement

Créer le fichier local non versionné :

```bash
cp .env.production.example .env.production
chmod 600 .env.production
python3 -c 'import secrets; print(secrets.token_urlsafe(64))'
python3 -c 'import secrets; print(secrets.token_urlsafe(64))'
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Utiliser des valeurs indépendantes pour `DJANGO_SECRET_KEY`, `JWT_SIGNING_KEY` et `POSTGRES_PASSWORD`. Ne jamais copier le fichier rempli dans Git, une image Docker, un ticket ou un journal.

### Variables obligatoires

| Variable | Exemple non secret | Rôle |
|---|---|---|
| `APP_DOMAIN` | `monitoring.example.com` | domaine servi par Caddy |
| `ACME_EMAIL` | `admin@example.com` | compte ACME/certificats |
| `DJANGO_SECRET_KEY` | valeur aléatoire | signatures Django |
| `JWT_SIGNING_KEY` | valeur aléatoire indépendante | signatures JWT |
| `POSTGRES_PASSWORD` | valeur aléatoire indépendante | rôle PostgreSQL |
| `ALLOWED_HOSTS` | `monitoring.example.com` | hôtes publics Django ; `api` est ajouté par l'overlay |
| `FRONTEND_URL` | `https://monitoring.example.com` | URL canonique du dashboard |
| `CORS_ALLOWED_ORIGINS` | même origine HTTPS | requêtes navigateur autorisées |
| `CSRF_TRUSTED_ORIGINS` | même origine HTTPS | origine CSRF de confiance |
| `DEFAULT_FROM_EMAIL` | adresse du service | expéditeur des notifications |
| `EMAIL_HOST` | serveur SMTP | livraison email réelle |

### Base, asynchrone et exploitation

| Variable | Valeur conseillée | Remarque |
|---|---|---|
| `POSTGRES_DB` | `infrasentinel` | volume PostgreSQL interne |
| `POSTGRES_USER` | `infrasentinel` | rôle applicatif |
| `POSTGRES_SSLMODE` | `disable` | acceptable uniquement sur le réseau Docker privé mono-hôte |
| `CELERY_WORKER_CONCURRENCY` | `2` | adapter à la RAM et aux traitements ML |
| `LOG_LEVEL` | `INFO` | éviter `DEBUG` en production |
| `LOG_MAX_SIZE` / `LOG_MAX_FILES` | `10m` / `5` | rotation du driver Docker `local` |
| `CONNECTOR_ALLOWED_HOSTS` | liste explicite | destinations vCenter/Hyper-V autorisées |
| `PUBLIC_REGISTRATION_ENABLED` | `false` | activation temporaire uniquement pour le bootstrap |
| `VITE_PUBLIC_REGISTRATION_ENABLED` | `false` | affiche la route d'inscription au build du dashboard |

L'overlay impose `DJANGO_DEBUG=false`, cookies Secure, redirection HTTPS, HSTS, documentation privée, TLS connecteurs vérifié et deux proxies de confiance correspondant à Caddy puis Nginx.

`SECURE_HSTS_INCLUDE_SUBDOMAINS` et `SECURE_HSTS_PRELOAD` restent désactivés par défaut. Les activer uniquement lorsque tous les sous-domaines utilisent définitivement HTTPS et, pour le preload, après vérification des contraintes du navigateur. Django `check --deploy` signale volontairement ces deux choix prudents.

## Installation initiale

Depuis le répertoire du projet sur le VPS :

```bash
docker compose \
  --env-file .env.production \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -p infrasentinel config --quiet

docker compose \
  --env-file .env.production \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -p infrasentinel pull db redis proxy

docker compose \
  --env-file .env.production \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -p infrasentinel up -d --build --wait --wait-timeout 300
```

Ordre réel : PostgreSQL/Redis sains → migrations terminées → API/worker/Beat → frontend → Caddy. Un échec de migration empêche le démarrage applicatif.

Vérifier :

```bash
docker compose --env-file .env.production \
  -f docker-compose.yml -f docker-compose.prod.yml \
  -p infrasentinel ps -a

docker compose --env-file .env.production \
  -f docker-compose.yml -f docker-compose.prod.yml \
  -p infrasentinel logs migrate proxy

curl -fsS https://monitoring.example.com/api/health/
```

Le healthcheck doit renvoyer `status=ok`, `database=ok` et `redis=ok`. Le conteneur `migrate` doit être `Exited (0)` et tous les services durables `healthy`.

## Premier client administrateur

L'inscription est fermée par défaut. Pour une base vide :

1. mettre temporairement `PUBLIC_REGISTRATION_ENABLED=true` et
   `VITE_PUBLIC_REGISTRATION_ENABLED=true` ;
2. limiter provisoirement 443 à l'adresse IP administrateur si possible ;
3. reconstruire `frontend`, puis recréer `api` et `frontend` avec la commande
   Compose ;
4. créer le premier client depuis `/register` ;
5. remettre immédiatement les deux variables à `false` ;
6. reconstruire `frontend`, recréer `api` et `frontend`, puis vérifier que toute
   nouvelle inscription reçoit HTTP 403 et que `/register` redirige vers `/login`.

Cette procédure crée simultanément le tenant, son administrateur et l'environnement Windows initial, contrairement à un simple `createsuperuser` global.

## Agents Windows distants

Configuration attendue sur chaque agent :

```json
{
  "backend_url": "https://monitoring.example.com",
  "verify_tls": true,
  "allow_insecure_tls": false,
  "latency_host": "monitoring.example.com",
  "latency_port": 443
}
```

Le réseau Windows doit autoriser DNS et HTTPS sortant vers le domaine. Aucun accès entrant vers l'agent n'est nécessaire. Le certificat doit être émis par une autorité publique reconnue par Windows ; ne jamais désactiver la validation TLS pour contourner un problème DNS/certificat.

L'enrôlement utilise un code temporaire créé pour le bon client/environnement. Le jeton agent retourné une seule fois est ensuite utilisé pour heartbeat et métriques. Il ne doit apparaître ni dans les journaux ni dans les outils de ticketing.

## Fichiers statiques et WebSocket

L'entrypoint API exécute `collectstatic` avant Daphne. Les fichiers sont conservés dans `static_data`; Nginx relaie `/static/` vers l'API. Le frontend Vite utilise `/api` et `/ws` en même origine.

Caddy transmet le schéma HTTPS à Nginx, qui le conserve vers Django. Cette chaîne est nécessaire pour les cookies Secure, les URL CSRF et l'absence de boucle avec `SECURE_SSL_REDIRECT=true`.

## Sauvegarde PostgreSQL

Créer un dossier local protégé hors du dépôt :

```bash
sudo install -d -m 700 -o "$USER" -g "$USER" /srv/infrasentinel-backups
BACKUP_DIR=/srv/infrasentinel-backups sh scripts/backup-postgres.sh
```

Le script :

- lit `.env.production` sans intégrer les secrets au nom du fichier ;
- exécute `pg_dump --format=custom` dans le conteneur DB ;
- n'expose pas PostgreSQL sur l'hôte ;
- publie le dump seulement après succès ;
- produit un fichier SHA-256 associé.

Exemple cron quotidien :

```cron
15 2 * * * cd /srv/infrasentinel && BACKUP_DIR=/srv/infrasentinel-backups sh scripts/backup-postgres.sh >> /var/log/infrasentinel-backup.log 2>&1
```

Copier ensuite les dumps chiffrés vers un stockage hors VPS et appliquer une rétention documentée. Une sauvegarde présente uniquement sur le VPS ne protège pas contre la perte de ce VPS.

Avant toute restauration, arrêter les écritures, sauvegarder l'état actuel et tester d'abord sur une base séparée. Validation d'un dump sans restauration destructive :

```bash
docker compose --env-file .env.production \
  -f docker-compose.yml -f docker-compose.prod.yml -p infrasentinel \
  exec -T db pg_restore --list < /srv/infrasentinel-backups/infrasentinel-AAAAmmjjTHHMMSSZ.dump
```

## Logs et supervision

Tous les services écrivent sur stdout/stderr. Le driver Docker `local` applique `LOG_MAX_SIZE` et `LOG_MAX_FILES`. Caddy émet des accès structurés JSON; Django utilise le filtre de secrets de la Phase 19.

```bash
docker compose --env-file .env.production \
  -f docker-compose.yml -f docker-compose.prod.yml -p infrasentinel \
  logs --since 30m api worker beat proxy
```

Ne jamais activer `DJANGO_DEBUG` en production et ne pas journaliser fichiers `.env`, headers Authorization, tickets WebSocket ou jetons agent. Pour une conservation longue, expédier les logs vers un système distant avec contrôle d'accès et rétention.

## Mise à jour et retour arrière

Avant une mise à jour : sauvegarde PostgreSQL vérifiée, tag applicatif immuable et lecture des migrations.

```bash
git fetch --all --tags
git checkout <version-validée>
BACKUP_DIR=/srv/infrasentinel-backups sh scripts/backup-postgres.sh
docker compose --env-file .env.production \
  -f docker-compose.yml -f docker-compose.prod.yml -p infrasentinel \
  up -d --build --wait --wait-timeout 300
```

Le retour au code précédent n'implique pas automatiquement que les migrations sont réversibles. En cas d'incompatibilité de schéma, restaurer le dump validé dans une fenêtre de maintenance.

## Validation réalisée pour la Phase 22

Le 25 août 2026, l'overlay de production a été testé localement avec `APP_DOMAIN=localhost`, un certificat Caddy interne et des ports isolés 18080/18443 :

| Contrôle | Résultat |
|---|---|
| Fusion Compose et variables obligatoires | réussie |
| Build production backend/frontend | réussi |
| PostgreSQL/Redis/migrations | sains, migration `Exited (0)` |
| API, worker, Beat, frontend, Caddy | tous `healthy` |
| HTTPS de bout en bout | HTTP 200, DB et Redis `ok` |
| HTTP vers HTTPS | redirection 308 |
| Cookies/headers | HSTS présent, CSP présente, `DEBUG=false` |
| Exposition réseau | aucun port publié pour API, frontend, DB ou Redis |
| Logs | driver `local`, rotation 10 MiB × 5 |
| Sauvegarde | dump custom non vide et lisible par `pg_restore --list` |
| Agent simulé via HTTPS | enrôlement, heartbeat et une métrique acceptés |
| `manage.py migrate --check` | réussi |
| `manage.py check --deploy` | uniquement les deux avertissements HSTS subdomains/preload documentés |

Cette preuve valide la configuration et le chemin HTTPS local. Elle **ne prouve pas** un déploiement distant : aucun VPS, DNS public, certificat ACME public, SMTP externe ni agent situé sur un autre réseau n'a été fourni ou testé pendant cette phase. Ces vérifications restent obligatoires lors de la mise en service réelle.
