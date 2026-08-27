# Sécurité du staging Azure

**Portée :** architecture mono-VM temporaire
**Principe :** exposition minimale, secrets hors Git, TLS obligatoire, destruction contrôlée

## Modèle d'exposition réseau

| Port | Source | Destination | Usage | Décision |
|---|---|---|---|---|
| 80/TCP | Internet | Caddy | challenge ACME et redirection HTTPS | ALLOW |
| 443/TCP et UDP | Internet | Caddy | dashboard, API HTTPS et WebSocket | ALLOW |
| 22/TCP | adresse IP publique de l'administrateur uniquement | SSH VM | administration initiale | ALLOW TEMPORAIRE |
| 5432/TCP | aucune source publique | PostgreSQL conteneur | base interne | DENY PUBLIC |
| 6379/TCP | aucune source publique | Redis conteneur | cache/broker interne | DENY PUBLIC |
| autres entrants | aucune | VM | non requis | DENY |

Le NSG doit être créé avec les seules règles ci-dessus. La composition de production supprime déjà les publications de ports PostgreSQL, Redis et API. Le proxy est l'unique point d'entrée applicatif.

## Identité et administration

- authentification SSH par clé, jamais par mot de passe ;
- clé privée conservée uniquement sur le poste administrateur, permissions locales restrictives ;
- aucun secret dans cloud-init, historique shell, URL Git ou journal partagé ;
- rôle Owner existant utilisé uniquement pour le provisionnement ; aucun nouveau rôle large ;
- SSH fermé après validation si Azure Run Command suffit, sinon règle limitée à une IP source unique ;
- Trusted Launch et Secure Boot conservés si compatibles avec le SKU.

## Secrets applicatifs

Les valeurs suivantes sont générées aléatoirement sur la VM et stockées dans un fichier `.env.production` non suivi, lisible uniquement par l'administrateur :

- `DJANGO_SECRET_KEY` ;
- `JWT_SIGNING_KEY`, indépendante de la précédente ;
- `POSTGRES_PASSWORD` ;
- éventuels identifiants SMTP ;
- credentials VMware/Hyper-V et tokens d'enrollment.

Le dépôt contient uniquement des placeholders. Les logs Docker et applicatifs ne doivent jamais afficher ces valeurs. Une rotation est obligatoire si une valeur apparaît dans un terminal partagé, une capture ou un commit.

## TLS et URL publique

La cible est un nom DNS Azure associé à l'IP publique, ou un domaine fourni par l'utilisateur, avec certificat Let's Encrypt géré par Caddy. Avant disponibilité du certificat :

- aucun agent réel ne doit transmettre de secret ;
- `SECURE_SSL_REDIRECT`, cookies Secure et hôtes de confiance restent activés en production ;
- `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS` et `FRONTEND_URL` doivent contenir uniquement le nom final HTTPS ;
- `API_DOCS_PUBLIC=false` et `PUBLIC_REGISTRATION_ENABLED=false`.

## Durcissement conteneurs et hôte

- appliquer les mises à jour de sécurité Ubuntu et Docker avant déploiement ;
- utiliser Docker Compose avec images épinglées lorsque le projet le prévoit ;
- conserver `no-new-privileges`, `cap_drop`, filesystems read-only et limites de processus définis dans les manifests ;
- journaux rotatifs ;
- volumes PostgreSQL, Redis et Caddy non exposés ;
- sauvegarde PostgreSQL chiffrée ou immédiatement supprimée après restauration de test ;
- aucun mode debug, aucune source map frontend, aucun endpoint de documentation public.

## Contrôles post-déploiement

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api python manage.py check --deploy
curl -fsSI https://<nom-dns>/login
curl -fsS https://<nom-dns>/api/health/
ss -lntup
```

Vérifications applicatives obligatoires : JWT invalide 401, endpoint protégé sans token 401/403, cross-tenant 404, token agent révoqué 401, CORS externe refusé, WebSocket sans ticket refusé et absence de secret dans les logs.

## Limites

- Defender for Cloud payant n'est pas activé automatiquement ;
- l'hôte unique reste un point de défaillance ;
- un nom DNS Azure public n'est pas un domaine de production gouverné par l'organisation ;
- la signature de l'installateur Windows reste hors du périmètre Azure.
