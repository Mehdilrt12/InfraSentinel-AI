# Base de données PostgreSQL

PostgreSQL est la base principale. SQLite reste disponible uniquement avec
`DATABASE_ENGINE=sqlite` pour une importation contrôlée ou un diagnostic local; le
chemin normal, Docker et la suite de validation utilisent PostgreSQL.

## Modèle relationnel

```mermaid
erDiagram
  CUSTOMER ||--o{ USER : possède
  CUSTOMER ||--o{ ENVIRONMENT : possède
  ENVIRONMENT ||--o{ MACHINE : contient
  MACHINE ||--o| AGENT : supervisee_par
  CUSTOMER ||--o{ INTEGRATION_ENDPOINT : configure
  INTEGRATION_ENDPOINT ||--o{ VIRTUAL_ASSET : découvre
  MACHINE ||--o{ NORMALIZED_METRIC : produit
  MONITORING_RULE ||--o{ RULE_STATE : mémorise
  MACHINE ||--o{ RULE_STATE : évalue
  MACHINE ||--o{ ALERT : déclenche
  ALERT ||--o| RECOMMENDATION : reçoit
  MACHINE ||--o{ ANOMALY : présente
  CUSTOMER ||--o{ ML_MODEL_VERSION : entraîne
  ALERT ||--o{ NOTIFICATION_EVENT : génère
  NOTIFICATION_EVENT ||--o{ NOTIFICATION_DELIVERY : distribue
  CUSTOMER ||--o{ REALTIME_EVENT : reçoit
  CUSTOMER ||--o{ AUDIT_LOG : journalise
```

`Customer` est la racine d'isolation. Les métriques référencent explicitement
customer, environnement et machine. `PROTECT` préserve les relations structurantes,
`CASCADE` supprime les dépendances tenant, et une anomalie peut garder sa trace
après suppression de sa métrique (`SET_NULL`).

## Contraintes et index essentiels

- UUID : tenants, inventaire, alertes, anomalies, modèles et notifications.
- `BigAutoField` : métriques Django et séquence globale des événements temps réel.
- `JSONField` : métadonnées source, contexte, explications, datasets et résultats.
- Unicité tenant/source/external_id pour les machines et connecteur/external_id
  pour les assets; hash unique pour codes d'enrôlement et jetons d'agents.
- Unicité partielle d'une alerte non résolue par tenant/clé de déduplication, d'un
  modèle ML actif par tenant et d'une métrique idempotente non nulle par tenant.
- Index machine/métrique/temps, tenant/temps, tenant/statut/sévérité et audit.
- Dates timezone-aware; Django est configuré avec `Africa/Casablanca` et `USE_TZ`.

## Configuration

```dotenv
DATABASE_ENGINE=postgresql
POSTGRES_DB=infrasentinel
POSTGRES_USER=infrasentinel
POSTGRES_PASSWORD=<secret-externe>
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_SSLMODE=prefer
POSTGRES_CONN_MAX_AGE=60
```

Aucune valeur de connexion n'est codée dans `settings.py`. En production distante,
utiliser le mode TLS imposé par le fournisseur et vérifier ses certificats.

## Création et contrôle des migrations

```powershell
. ./scripts/common.ps1
Import-DotEnv backend/.env
./.venv/Scripts/python.exe backend/manage.py migrate
./.venv/Scripts/python.exe backend/manage.py migrate --check
./.venv/Scripts/python.exe backend/manage.py showmigrations
./.venv/Scripts/python.exe backend/manage.py makemigrations --check --dry-run
```

Le 26 août 2026, la découverte complète Django a créé une base de test PostgreSQL,
trouvé **186 tests** : **183 réussis, 3 ignorés et 0 échec**. Le
schéma OpenAPI a aussi été généré et validé. Ce résultat remplace le chiffre
historique de 48 tests, qui ne représentait qu'une étape de reconstruction.

## Migration SQLite vers PostgreSQL

1. Geler les écritures et sauvegarder les deux bases.
2. Migrer un PostgreSQL vide au même commit applicatif.
3. Exporter SQLite avec les natural keys prévues.
4. Charger les données, réinitialiser les séquences et comparer les nombres de
   lignes, FK, tenants, métriques, alertes et utilisateurs.
5. Faire une recette avant la bascule; conserver SQLite jusqu'à acceptation.

Le script `scripts/migrate-sqlite-to-postgresql.ps1` automatise les garde-fous. Ne
pas lancer `loaddata` sur une base PostgreSQL déjà alimentée.

## Sauvegarde et restauration

```powershell
pg_dump --format=custom --file=infrasentinel.dump $env:POSTGRES_DB
createdb infrasentinel_restore_test
pg_restore --dbname=infrasentinel_restore_test infrasentinel.dump
```

Tester la restauration sur une base séparée, chiffrer les dumps, stocker hors de
l'hôte principal et documenter RPO/RTO et rétention. Le volume Docker persistant ne
remplace pas une sauvegarde.

## Dépannage

- `connection refused` : vérifier service, host/port, firewall et réseau Compose.
- `password authentication failed` : vérifier le secret injecté sans l'afficher.
- tests sans droit `CREATEDB` : utiliser un compte de test dédié non production.
- migrations divergentes : comparer `showmigrations`; ne pas réécrire l'historique
  déjà appliqué.
- connexions saturées : mesurer avant d'ajuster connexion, workers ou pool; voir
  [PERFORMANCE.md](PERFORMANCE.md).
