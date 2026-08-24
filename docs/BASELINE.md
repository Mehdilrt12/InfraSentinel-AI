# Baseline technique

Date : 24 août 2026 — version reconstruite `2.0.0`.

## Contexte

La copie de travail antérieure a disparu du disque avant la phase 17. La Corbeille,
les autres volumes et les dépôts Git accessibles ont été vérifiés sans trouver de
copie restaurable. La révision d'origine connue était `845f8d7` sur `main`.
La présente baseline décrit exclusivement la reconstruction vérifiable contenue
dans ce dépôt; elle ne prétend pas restaurer octet pour octet l'ancien dépôt.

## Architecture actuelle

- `backend/` : Django 6, DRF, JWT, PostgreSQL, Channels et Celery.
- `frontend/` : React 19/Vite 6, dashboard responsive.
- `agent/` : agent Windows Python, service Windows, DPAPI, cache SQLite local.
- `vmware_connector/` : client vCenter pyVmomi et métriques de performance.
- `hyperv_connector/` : exécuteur Python et un script PowerShell centralisé.
- `scripts/` : installation, lancement, arrêt, statut et validation.
- `docs/` : architecture et procédures par domaine.
- `backend/*/tests.py` et `agent/tests/` : tests unitaires et sécurité.

## Technologies réellement utilisées

Python 3.14, Django 6.0.6, DRF 3.17.1, SimpleJWT 5.5.1,
PostgreSQL via psycopg 3.3.4, Channels 4.3.2, Daphne 4.2.3,
Celery 5.6, Redis, scikit-learn 1.9, pandas 3.0 et pyVmomi 9.
Le frontend utilise React 19.1, React Router 7.18, Axios 1.19,
Recharts 3.1 et Vite 6.4.

## Fonctionnalités présentes

- Authentification email/JWT et rôles ADMIN, SUPERVISOR, TECHNICIAN, CLIENT, VIEWER.
- Isolation multi-tenant appliquée aux querysets et aux relations entrantes.
- Environnements, machines, agents, enrollment à usage unique et heartbeat.
- Normalisation commune Windows/VMware/Hyper-V et historique indexé.
- Règles configurables avec opérateur, seuil, durée, scope et sévérité.
- Alertes durables avec déduplication, occurrence, corrélation et recommandation.
- Isolation Forest reproductible sur les seules métriques persistées.
- Collecteurs VMware/Hyper-V réels; aucun jeu VMware/Hyper-V fictif n'est injecté.
- Temps réel WebSocket avec ticket court, séparation par tenant et replay.
- Notifications email persistantes, cooldown, retry et journal d'envoi.
- Celery/Redis pour ML, notifications, connecteurs, agrégats et rapports.

## Partiel ou non vérifié sur infrastructure réelle

- Aucune connexion vCenter ou Hyper-V réelle n'était disponible pendant la
  reconstruction : les collecteurs sont testables par mocks, pas certifiés sur
  l'infrastructure de production de l'utilisateur.
- L'envoi SMTP réel requiert une configuration externe; le backend console/locmem
  sert aux tests.
- Teams, Slack et Telegram sont prévus dans le modèle de canaux, sans adaptateur
  d'envoi actif.
- L'installation effective du service Windows exige une console Administrateur.
- Les modèles ML exigent au moins 20 fenêtres de données réelles; aucun modèle
  pré-entraîné avec des données inventées n'est livré.

## Risques et limites

- Redis et PostgreSQL doivent être hautement disponibles en production.
- Le secret Django, les mots de passe DB/SMTP et secrets connecteurs doivent être
  injectés par variables/coffre; `secret_ref` ne contient jamais le secret.
- Le stockage de métriques n'implémente pas encore partitionnement/rétention
  PostgreSQL; à prévoir lorsque le volume dépasse les capacités d'une table unique.
- Les compteurs vSphere peuvent dépendre des niveaux de statistiques vCenter.
- WinRM/PowerShell Remoting et les permissions Hyper-V doivent être préparés.

## État global

Base cohérente et exécutable jusqu'à la phase 17. Une fonctionnalité externe ne
doit être considérée opérationnelle qu'après le test d'intégration correspondant.

## Reproduction

```powershell
Copy-Item backend/.env.example backend/.env
docker compose up -d db redis
./scripts/setup.ps1
./scripts/test-all.ps1
./scripts/start-local.ps1
```

