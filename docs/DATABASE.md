# Base de données

PostgreSQL est la cible principale et se configure uniquement avec
`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`,
`POSTGRES_PORT` et `POSTGRES_SSLMODE`. `DATABASE_ENGINE=sqlite` est réservé aux
tests/démonstrations et à la procédure d'import.

## Relations principales

`Customer` possède utilisateurs, environnements, machines, métriques, règles,
alertes, anomalies, connecteurs et notifications. Une `Machine` appartient à un
environnement et peut avoir un `Agent` ou un `VirtualAsset`. Les métriques ont des
FK explicites vers customer/environment/machine. Les scopes de règle sont
optionnels. Les alertes et anomalies appartiennent toujours à une machine/client.

## Types, contraintes et index

- UUID pour les identités distribuées; bigint pour métriques/événements séquentiels.
- `JSONField` pour métadonnées spécifiques sans perdre vSphere/Hyper-V/Windows.
- contraintes uniques sur identités externes, enrollment hash, agent token hash,
  version ML, préférences, agrégats et clés d'idempotence.
- index temporels et composites machine/métrique/date, tenant/statut/sévérité et
  connecteur/type.
- timestamps timezone-aware.

## Migration depuis zéro

```powershell
$env:DATABASE_ENGINE='postgresql'
$env:POSTGRES_DB='infrasentinel'
$env:POSTGRES_USER='infrasentinel'
$env:POSTGRES_PASSWORD='...'
$env:POSTGRES_HOST='127.0.0.1'
$env:POSTGRES_PORT='5432'
./.venv/Scripts/python.exe backend/manage.py migrate
```

## Import SQLite existant

Geler les écritures, sauvegarder les deux bases, exporter avec `dumpdata --natural-foreign
--natural-primary`, migrer PostgreSQL vide puis exécuter `loaddata`. Réinitialiser
les séquences avec `sqlsequencereset`. Vérifier les comptes, FK, nombres de lignes
et échantillons avant bascule. Le script `scripts/migrate-sqlite-to-postgresql.ps1`
automatise ces garde-fous sans supprimer SQLite.

## Sauvegarde/restauration

```powershell
pg_dump --format=custom --file=infrasentinel.dump $env:POSTGRES_DB
pg_restore --clean --if-exists --dbname=$env:POSTGRES_DB infrasentinel.dump
```

Tester périodiquement la restauration sur une base distincte. Chiffrer les dumps
et appliquer une rétention documentée.

## Validation de la reconstruction

Le 24 août 2026, toutes les migrations ont été appliquées sur une base PostgreSQL
17 vierge, y compris les contraintes partielles de déduplication des alertes et
notifications. La suite backend a ensuite réussi 21 tests sur cette base; la base
de validation isolée a été supprimée après le contrôle, sans toucher à la base
applicative.
