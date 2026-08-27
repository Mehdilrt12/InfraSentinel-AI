# InfraSentinel AI

Plateforme centralisée de supervision proactive pour Windows, VMware et Hyper-V.

```text
Windows Agent ─┐
VMware/vCenter ├─> API Django ─> PostgreSQL ─> Rules/ML ─> Alerts
Hyper-V Host ──┘                       └─> Celery/Redis ─> Notifications
                                              └─> WebSocket ─> React
```

Le dépôt reconstruit couvre les phases 0 à 27 : authentification JWT et RBAC,
multi-tenant, collecte et normalisation des métriques, règles temporelles,
alertes corrélées, Isolation Forest reproductible, recommandations, dashboard,
WebSocket, notifications email, exécution asynchrone avec Redis/Celery,
documentation OpenAPI, sécurité, audit, conteneurisation, déploiement et package
d'installation de l'agent Windows, tests de charge, scénarios PFE et documentation
technique finale.

## Démarrage local

1. Copier `backend/.env.example` vers `backend/.env` et
   `frontend/.env.example` vers `frontend/.env`, puis remplacer les secrets
   d'exemple. Exécuter `scripts/prepare-local-compose-env.ps1` pour préparer le
   `.env` Docker sans afficher les secrets.
2. Démarrer PostgreSQL et Redis avec `docker compose up -d db redis`.
3. Exécuter `scripts/setup.ps1`, puis `scripts/start-local.ps1`.
4. Ouvrir <http://127.0.0.1:5173>.

SQLite reste disponible comme chemin de compatibilité/import avec
`DATABASE_ENGINE=sqlite`; PostgreSQL demeure la configuration principale et celle
de la suite backend complète.

Commencer par `docs/LOCAL_FINAL_VALIDATION_REPORT.md` pour l'état strict du
laboratoire, puis par `docs/README.md` pour l'index, les commandes et le
troubleshooting. Les rapports `docs/RECONSTRUCTION_AUDIT.md` et
`docs/TEST_RECOVERY_REPORT.md` restent des preuves historiques; les résultats
courants sont 186 tests Django découverts sur PostgreSQL : 183 réussis, 3 ignorés
et aucun échec.
