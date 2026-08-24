# InfraSentinel AI

Plateforme centralisée de supervision proactive pour Windows, VMware et Hyper-V.

```text
Windows Agent ─┐
VMware/vCenter ├─> API Django ─> PostgreSQL ─> Rules/ML ─> Alerts
Hyper-V Host ──┘                       └─> Celery/Redis ─> Notifications
                                              └─> WebSocket ─> React
```

Le dépôt reconstruit couvre les phases 0 à 17 : authentification JWT et RBAC,
multi-tenant, collecte et normalisation des métriques, règles temporelles,
alertes corrélées, Isolation Forest reproductible, recommandations, dashboard,
WebSocket, notifications email et exécution asynchrone avec Redis/Celery.

## Démarrage local

1. Copier `.env.example` vers `.env`, `backend/.env.example` vers
   `backend/.env` et `frontend/.env.example` vers `frontend/.env`, puis remplacer
   les secrets d'exemple.
2. Démarrer PostgreSQL et Redis avec `docker compose up -d db redis`.
3. Exécuter `scripts/setup.ps1`, puis `scripts/start-local.ps1`.
4. Ouvrir <http://127.0.0.1:5173>.

SQLite reste disponible pour les tests et la démonstration avec
`DATABASE_ENGINE=sqlite`; PostgreSQL demeure la configuration cible.

Voir `docs/RECONSTRUCTION_AUDIT.md` pour la revue stricte et ses limites externes,
puis `docs/RECONSTRUCTION.md`, `docs/ARCHITECTURE.md` et `docs/ASYNC_TASKS.md`.
