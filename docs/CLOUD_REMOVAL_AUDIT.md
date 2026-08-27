# Audit de retrait des travaux cloud

**Date :** 27 août 2026

**Checkpoint :** `f65647517fab5ca3fd0e1baca44bdb5941fb9830`

**Tag de récupération :** `pre-local-only-cleanup`

## Portée et méthode

L'inventaire a été réalisé avant toute suppression avec `git status`, `git log`,
`git tag`, `git ls-files`, `git grep` et `rg`. Les recherches ont couvert le code,
les scripts, les exemples d'environnement, Docker, la documentation et les
fichiers suivis par Git pour Azure, Google Cloud/GCP, Oracle Cloud/OCI et leurs
outils ou services spécifiques.

Le dépôt était propre au début de l'opération, sur la branche
`codex/azure-staging`. Aucun secret cloud, SDK cloud, manifeste ARM/Bicep,
Terraform, commande `az`, commande `gcloud`, pipeline de déploiement provider ou
URL cloud codée dans l'application n'a été trouvé.

## Inventaire et décision

| Fichier ou composant | Cloud | Objet | Décision | Motif |
|---|---|---|---|---|
| `docs/AZURE_PREDEPLOYMENT_AUDIT.md` | Azure | Audit préparatoire Azure | CLOUD-SPECIFIC - REMOVE | Rapport exclusivement lié à un abonnement Azure et devenu obsolète pour le laboratoire local. |
| `docs/AZURE_STUDENT_ACCOUNT_AUDIT.md` | Azure | Audit Azure for Students | CLOUD-SPECIFIC - REMOVE | État d'un compte externe, sans rôle dans l'exécution locale. |
| `docs/AZURE_ARCHITECTURE_DECISION.md` | Azure | Décision de staging sur VM Azure | CLOUD-SPECIFIC - REMOVE | Architecture remplacée par la référence locale Docker/LAN. |
| `docs/AZURE_SECURITY.md` | Azure | Sécurité du staging Azure | CLOUD-SPECIFIC - REMOVE | Mesures spécifiques à une VM/réseau Azure non déployés. |
| `docs/AZURE_COST_GUARDRAILS.md` | Azure | Budget et coûts Azure | CLOUD-SPECIFIC - REMOVE | Garde-fous propres à Azure for Students. |
| `docs/CLOUD_PREDEPLOYMENT_AUDIT.md` | Google Cloud | Audit et étude de coût GCP | CLOUD-SPECIFIC - REMOVE | Rapport exclusivement GCP, sans composant réutilisable par le laboratoire. |
| Ligne Azure dans `docs/README.md` | Azure | Liens vers les cinq rapports Azure | CLOUD-SPECIFIC - REMOVE | Les documents cibles sont retirés. |
| `docker-compose.yml` | Aucun | Stack PostgreSQL, Redis, Django, Celery, Beat, React | REUSABLE DOCKER CONFIG - KEEP | Infrastructure locale de référence demandée. |
| `docker-compose.prod.yml` | Aucun | Overlay HTTPS et durcissement | GENERIC PRODUCTION CONFIG - KEEP | Ne contient aucune API ni ressource provider; utile sur LAN/VPS futur. |
| `deploy/Caddyfile` | Aucun | Reverse proxy HTTPS | GENERIC DEPLOYMENT - KEEP | Caddy est indépendant du fournisseur. |
| `docs/DEPLOYMENT.md` | Aucun | Déploiement VPS Docker générique | GENERIC DEPLOYMENT - KEEP | Ne dépend ni d'Azure ni de GCP; peut servir de référence future optionnelle. |
| `.env.production.example` | Aucun | Contrat de variables de production | GENERIC PRODUCTION CONFIG - KEEP | Variables génériques, valeurs d'exemple sans secret. |
| `scripts/backup-postgres.sh` | Aucun | Sauvegarde PostgreSQL | GENERIC DEPLOYMENT - KEEP | Nécessaire à la validation locale de sauvegarde/restauration. |
| `backend/config/settings.py` | Aucun | Paramétrage Django/Redis/Celery | GENERIC PRODUCTION CONFIG - KEEP | URLs et hôtes sont fournis par variables d'environnement. |
| `frontend/src/api.js` et `frontend/src/realtime.jsx` | Aucun | API et WebSocket configurables | GENERIC PRODUCTION CONFIG - KEEP | Valeur par défaut same-origin, surcharge possible par variables Vite. |
| Exemples `localhost`/`127.0.0.1` | Aucun | Valeurs de développement | KEEP | Acceptables pour le développement; aucune adresse LAN actuelle n'est codée durablement. |

## Dépendances applicatives

Les dépendances Python et JavaScript ne contiennent aucun SDK Azure, Google Cloud
ou OCI. Les chemins applicatifs utilisent les contrats génériques suivants :

- `FRONTEND_URL`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS` et
  `CSRF_TRUSTED_ORIGINS` côté Django;
- variables PostgreSQL et `REDIS_URL`/`CELERY_*` pour les services;
- `VITE_API_URL` et `VITE_WS_URL` côté navigateur;
- `INFRASENTINEL_SERVER_URL` ou `backend_url` côté agent Windows.

## Ressources externes hors dépôt

Un groupe de ressources Azure de staging vide et un budget d'alerte avaient été
créés lors d'une tentative antérieure. Ils ne constituent pas une dépendance du
code local. Leur suppression est une action externe et potentiellement
destructive; elle n'est pas réalisée par cette campagne sans autorisation
explicite. Aucun travail supplémentaire ne sera effectué dans Azure ou GCP.

## Conclusion de l'audit préalable

La suppression peut être limitée aux six documents exclusivement cloud et au
lien Azure de l'index. Les composants génériques Docker, production, réseau,
HTTPS, base de données, Redis, Celery et sauvegarde doivent être conservés.
