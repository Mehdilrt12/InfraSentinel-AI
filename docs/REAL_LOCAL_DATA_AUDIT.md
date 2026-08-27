# Audit des données réelles du laboratoire local/LAN

**Date :** 27 août 2026

**Checkpoint Git avant modification :** `e25b59ed9f4c159b995e4975af2016547a960a9c`

**Tag de récupération :** `pre-real-local-lan-validation`

## Règles de classement

- `REAL` : source réellement enrôlée ou connectée, sans marqueur de test, avec
  identité et télémétrie observables.
- `CONTROLLED_TEST` : objet portant `synthetic=true`, `demo_suite=PFE25`, le
  préfixe `[DEMO]` ou le domaine réservé `demo.invalid`.
- `SIMULATED` : agent ou machine produit par le banc de charge.
- `SEED` : donnée initiale statique sans preuve de collecte.
- `UNKNOWN` : provenance insuffisante; elle ne peut pas être présentée comme
  réelle.

## État constaté avant nettoyage

L'inspection ORM de PostgreSQL a trouvé :

| Objet | Total | REAL | CONTROLLED_TEST | Conclusion |
|---|---:|---:|---:|---|
| Machines | 12 | 0 | 12 | aucune machine réelle |
| Agents | 1 | 0 | 1 | agent `2.0.0-demo` |
| Métriques | 250 | 0 | 250 | toutes synthétiques |
| Alertes | 6 | 0 | 6 | dérivées des scénarios PFE25 |
| Anomalies | 2 | 0 | 2 | dérivées des scénarios PFE25 |
| Connecteurs | 2 | 0 | 2 | endpoints `.demo.invalid`, désactivés |
| Assets virtuels | 5 | 0 | 5 | VMware/Hyper-V synthétiques |
| Modèles ML actifs | 1 | 0 | 1 | dataset `synthetic=true` |

Les 11 machines du tenant `cgi` appartenaient aux environnements `[PFE DEMO]`
Windows, VMware et Hyper-V. La douzième appartenait au tenant isolé
`pfe-demo-isolated`. Les cinq comptes `pfe25.*@demo.invalid` et le compte du
tenant isolé étaient également des données contrôlées. Les comptes
`admin@infrasentinel.local` et `mehdilrt@gmail.com` ont été conservés; leur
authenticité métier reste à confirmer par le propriétaire mais ils ne portent
aucun marqueur de simulation.

## Sauvegarde préalable

Avant toute suppression, PostgreSQL 17.11 a produit une archive custom :

```text
runtime/backups/infrasentinel-20260827T103628Z.dump
size: 247535 bytes
sha256: a781d4df188b2d072d0e4a973e5878e9c55366625ad69112996abc373c4afa2d
```

`pg_restore --list` a validé le format et les 348 entrées de l'archive. Le
répertoire `runtime/` est ignoré par Git; aucun dump ni secret n'est versionné.

## Nettoyage appliqué

La routine existante de nettoyage PFE25 a supprimé uniquement les objets
explicitement associés à `demo_suite=PFE25`, les comptes de démonstration et le
tenant isolé. Le code de génération, les tests et la commande de démonstration
ont été conservés.

État PostgreSQL après nettoyage :

| Objet | Total opérationnel |
|---|---:|
| Customers | 2 |
| Utilisateurs | 2 |
| Environnements Windows vides | 2 |
| Machines / agents | 0 / 0 |
| Métriques / alertes / anomalies | 0 / 0 / 0 |
| Connecteurs / assets virtuels | 0 / 0 |
| Règles / modèles ML | 0 / 0 |

Le dashboard normal doit donc afficher zéro asset, zéro hôte VMware et zéro
hôte Hyper-V jusqu'à l'enrôlement ou la connexion d'une source réelle. Les
scénarios contrôlés peuvent être recréés explicitement pour une campagne
scientifique, mais ne doivent pas être mélangés au mode opérationnel.
