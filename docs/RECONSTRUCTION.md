# État de la reconstruction

Date de validation : 24 août 2026 — version `2.0.0`.

## Périmètre livré

Le dépôt a été reconstruit jusqu'à la phase 17. Il fournit une plateforme
centralisée composée d'une API Django/DRF/Channels, d'un dashboard React/Vite,
d'un agent Windows, de connecteurs VMware et Hyper-V, de PostgreSQL, Redis et
Celery. Les métriques Windows, VMware et Hyper-V convergent vers un schéma
normalisé commun, puis alimentent les règles, alertes, recommandations et le
pipeline Isolation Forest.

La reconstruction ne prétend pas être une copie binaire du dépôt disparu. Elle
constitue une nouvelle baseline autonome, versionnée et reproductible.

## Preuves de validation

| Contrôle | Résultat vérifié |
|---|---|
| Migrations PostgreSQL depuis une base vide | Succès |
| Tests backend sur SQLite | 45/45, 3 ignorés car concurrence PostgreSQL |
| Tests backend sur PostgreSQL | 48/48 |
| Couverture backend | 61 % (mesure large incluant API et migrations) |
| Tests agent Windows | 8/8 |
| Tests frontend | 10/10 |
| Ruff | Succès, zéro erreur |
| ESLint | Succès, zéro avertissement |
| Build Vite production | Succès |
| Audit npm | 0 vulnérabilité connue |
| PostgreSQL et Redis | Conteneurs sains |
| Worker Celery, exécution et redémarrage | Succès |

## Éléments vérifiés uniquement par isolation

Les collecteurs VMware et Hyper-V ont une implémentation réelle et des chemins
de test sans données inventées. VMware n'a pas été connecté à un vCenter. Hyper-V
a été tenté sur l'hôte local, mais `Get-VM` a refusé l'accès faute de permissions;
il n'est donc pas validé comme intégration réelle. L'envoi email a été
validé avec un backend de développement; un test SMTP réel reste nécessaire avec
les paramètres de l'organisation. L'installation du service Windows doit être
effectuée sur une machine Windows avec élévation administrateur.

## Démarrage reproductible

```powershell
Copy-Item .env.example .env
Copy-Item backend/.env.example backend/.env
Copy-Item frontend/.env.example frontend/.env
# Remplacer les mots de passe et secrets d'exemple.
docker compose up -d db redis
./scripts/setup.ps1
./scripts/test-all.ps1
./scripts/start-local.ps1
```

Le dashboard est exposé sur `http://127.0.0.1:5173` et l'état API sur
`http://127.0.0.1:8000/api/health/`. `scripts/status-local.ps1` contrôle les
processus et `scripts/stop-local.ps1` les arrête sans supprimer les données.
