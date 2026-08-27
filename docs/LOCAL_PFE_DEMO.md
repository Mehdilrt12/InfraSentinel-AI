# Scénario de démonstration PFE locale

## Message central au jury

> InfraSentinel ne se limite pas à afficher un seuil dépassé : il combine
> historique normalisé, Isolation Forest, évolution temporelle et règles pour
> détecter ce qui est anormal maintenant et estimer un risque à venir.

## Préconditions

- Docker Desktop actif;
- `.env`, `backend/.env` et `frontend/.env` locaux, non versionnés;
- sept services Compose sains;
- un tenant de démonstration dédié;
- navigateur sur `http://127.0.0.1:5173`;
- ne jamais présenter les ressources VMware/Hyper-V synthétiques comme réelles.

```powershell
./scripts/prepare-local-compose-env.ps1
docker compose --env-file .env up -d --build --wait --wait-timeout 300
docker compose --env-file .env ps -a
Invoke-RestMethod http://127.0.0.1:8000/api/health/
```

Le healthcheck attendu indique `status=ok`, `database=ok`, `redis=ok`.

## Préparer les données contrôlées

```powershell
$env:PFE_DEMO_PASSWORD = Read-Host 'Mot de passe temporaire du jury' -MaskInput
docker compose --env-file .env exec -e PFE_DEMO_PASSWORD=$env:PFE_DEMO_PASSWORD `
  -T api python manage.py prepare_pfe_demo --customer-slug <tenant-demo> --reset
Remove-Item Env:\PFE_DEMO_PASSWORD
```

Résultat observé le 27 août 2026 : 11 machines de démonstration, 250 métriques,
5 règles, 5 alertes avec recommandations, 1 anomalie ML, 1 tendance prédictive
à risque 70 et une notification console `SENT`. Toutes ces données sont marquées
synthétiques.

## Déroulé recommandé

### 1. Plateforme et centralisation

Montrer `docker compose ps`, `/api/health/` et le dashboard global.

À expliquer : PostgreSQL est la source de vérité; Redis transporte cache,
Channels et tâches, tandis que Celery traite l'asynchrone.

Capture : health API et sept services sains.

### 2. Agent Windows réel

Lancer un agent autorisé vers l'adresse locale/LAN. Montrer enrollment, heartbeat,
machine `ONLINE` et métriques CPU/RAM/disque/I/O/réseau/latence/processus/uptime.

À expliquer : l'enrôlement retourne un jeton stocké via DPAPI; les secrets ne
sont pas écrits dans les logs.

Capture : page machine et historique. Ne pas confondre ce runtime réel avec
l'installation Windows Service, qui exige une session administrateur distincte.

### 3. Règles et alerte durable

Ouvrir les machines CPU, RAM et disque contrôlées. Montrer la durée de règle,
la sévérité et l'alerte unique. Le probe de déduplication a envoyé 100 métriques
CPU semblables et a conservé une seule alerte ouverte.

À expliquer : le moteur maintient un état temporel, applique cooldown et clé de
déduplication, puis gère ACK/IN_PROGRESS/RESOLVED.

Capture : règle et détail d'alerte avec recommandation.

### 4. Isolation Forest réelle

Ouvrir `/ml`. Montrer version, six features, score et seuil. Le modèle réel a
évalué 61 fenêtres : 59 normales et 2 anormales.

À expliquer : les données de démonstration sont synthétiques et labellisées
comme telles; le score n'est pas une valeur inventée mais la sortie du pipeline
Joblib chargé.

Capture : version du modèle et anomalie.

### 5. Analyse proactive

Montrer la machine de tendance et le résultat `INCREASING`, risque 70, confiance
`MEDIUM`, taux 4 points/heure et échéance estimée.

À expliquer : l'échéance est une extrapolation linéaire avec avertissement, pas
une promesse de panne.

Capture : carte/ligne de tendance avec `is_estimate`.

### 6. Temps réel

Ouvrir deux sessions, provoquer une métrique/alerte et montrer la mise à jour.
Le probe automatisé a validé deux clients, même séquence, replay après
déconnexion et rejet HTTP 403 d'un ticket réutilisé.

À expliquer : WebSocket transporte les événements importants; le frontend
conserve un polling de secours.

### 7. Multi-tenant et sécurité

Montrer qu'un administrateur Client A ne voit pas Client B. Le probe réel a
obtenu 404 sur l'objet d'un autre tenant, 403 pour un viewer sur les utilisateurs,
401 pour jeton invalide/révoqué et 403 sur une publication agent cross-tenant.

Capture : listes A/B ou sortie structurée du probe.

### 8. VMware et Hyper-V

Montrer uniquement les écrans et données marquées
`[DEMO SYNTHÉTIQUE — NON CONNECTÉ]` si aucun lab réel n'est disponible.

À expliquer : les connecteurs, normaliseurs et mocks sont testés, mais aucune
collecte réelle VMware n'a été exécutée; Hyper-V existe sur l'hôte mais l'utilisateur
courant n'a pas la permission `Get-VM`. Ces points sont `NOT TESTED`, pas `PASS`.

### 9. Notification

Montrer le cycle Alert -> NotificationEvent -> Celery -> Delivery. Le backend
console est validé; aucune livraison SMTP externe ne doit être annoncée.

## Commandes de preuve

```powershell
./scripts/test-all.ps1 -Database postgresql -RedisIntegration
. ./scripts/common.ps1
Import-DotEnv backend/.env
./.venv/Scripts/python.exe scripts/final_api_probe.py
./.venv/Scripts/python.exe scripts/final_realtime_probe.py
Get-Content -Raw scripts/final_ml_probe.py |
  docker compose --env-file .env exec -T api python -
```

## Checklist avant entrée du jury

- [ ] Docker, API, PostgreSQL, Redis, worker, Beat et frontend sains;
- [ ] `/login` puis les onze routes majeures s'ouvrent sans erreur fatale;
- [ ] mot de passe de démonstration temporaire testé et non versionné;
- [ ] données synthétiques clairement identifiées;
- [ ] modèle actif et artefact présents dans le même runtime;
- [ ] anomalies, tendance, alertes et recommandations visibles;
- [ ] deux sessions WebSocket prêtes;
- [ ] aucune promesse de VMware/Hyper-V/SMTP réel sans environnement;
- [ ] fermer les notifications personnelles et préparer les captures;
- [ ] garder `docs/LOCAL_FINAL_VALIDATION_REPORT.md` comme preuve.
