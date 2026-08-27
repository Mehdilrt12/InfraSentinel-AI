# Rapport final de validation du laboratoire local

**Projet :** InfraSentinel AI 2.0.0

**Date :** 27 août 2026

**Checkpoint avant nettoyage :** `f65647517fab5ca3fd0e1baca44bdb5941fb9830`

**Tag de récupération :** `pre-local-only-cleanup`

## 1. Executive Summary

Le projet fonctionne à nouveau en local. Le défaut visible provenait de
processus API/frontend/Beat arrêtés encore référencés par le fichier runtime et
d'un `.env` Docker incomplet. Le lancement hybride et la composition Docker
complète ont ensuite été vérifiés par healthchecks réels.

Le cœur du PFE est opérationnel sur données contrôlées : métriques normalisées,
règles temporelles, alertes dédupliquées, Isolation Forest versionné, inférence,
tendance prédictive, recommandations, WebSocket, multi-tenant, PostgreSQL,
Redis et Celery. Un agent Windows Python réel a collecté le poste local.

La validation n'autorise pas la conclusion « tout fonctionne ». L'installation
réelle du Windows Service exige une élévation administrateur; `Get-VM` est refusé
à l'utilisateur courant; aucun vCenter, SMTP externe ni réseau WAN autorisé n'est
configuré. Le verdict strict est donc **LOCAL ENTERPRISE LAB PARTIALLY
VALIDATED**.

## 2. Travaux cloud retirés

L'audit préalable est dans `docs/CLOUD_REMOVAL_AUDIT.md`. Ont été retirés :

- cinq rapports exclusivement Azure;
- un rapport exclusivement Google Cloud;
- la ligne Azure correspondante dans l'index documentaire.

Aucun SDK, URL, manifeste, commande ou variable provider n'était présent dans le
code applicatif. Le groupe Azure de staging vide et le budget créés auparavant
sont externes au dépôt et n'ont pas été supprimés sans autorisation destructive.
Le projet local n'en dépend pas.

## 3. Fichiers retirés

- `docs/AZURE_PREDEPLOYMENT_AUDIT.md`
- `docs/AZURE_STUDENT_ACCOUNT_AUDIT.md`
- `docs/AZURE_ARCHITECTURE_DECISION.md`
- `docs/AZURE_SECURITY.md`
- `docs/AZURE_COST_GUARDRAILS.md`
- `docs/CLOUD_PREDEPLOYMENT_AUDIT.md`

Tous restent récupérables depuis `pre-local-only-cleanup`.

## 4. Infrastructure générique préservée

`docker-compose.yml`, l'overlay de production générique, Caddy, PostgreSQL,
Redis, Celery/Beat, HTTPS-ready settings, variables d'environnement et script de
sauvegarde sont conservés. Ils ne dépendent d'aucun fournisseur.

## 5. Architecture locale finale

```text
Windows Agent / VMware / Hyper-V / Simulators
                    |
              HTTP(S) + LAN
                    v
React <-> Django ASGI/Channels <-> PostgreSQL
                    |
                  Redis
                    |
             Celery Worker + Beat
                    |
       Rules + ML + Alerts + Notifications
```

Les détails et variables LAN figurent dans `docs/LOCAL_LAB_ARCHITECTURE.md`.
Loopback reste la valeur sûre par défaut; `API_BIND_ADDRESS`,
`FRONTEND_BIND_ADDRESS`, origines Django/Vite et URL agent sont configurables.

## 6. PostgreSQL

**PASS.** PostgreSQL 17.11 est la base de référence. Preuves :

```powershell
docker compose --env-file .env exec -T api python manage.py check
docker compose --env-file .env exec -T api python manage.py makemigrations --check --dry-run
docker compose --env-file .env exec -T api python manage.py migrate --check
./scripts/test-all.ps1 -Database postgresql -RedisIntegration
```

Résultats : aucun problème Django, aucun changement de modèle, migrations à
jour, 186 tests découverts, 183 réussis et 3 skips externes. Les tests de
concurrence PostgreSQL couvrent multi-agent, alertes et notification unique.
Une coupure DB a produit HTTP 503, puis le redémarrage a retrouvé 11 machines et
le même modèle actif.

Aucune preuve de concurrence ne repose sur SQLite. SQLite reste seulement un
chemin de compatibilité/import explicitement non production.

## 7. Redis

**PASS.** Le test d'intégration réel a validé PING, set/get, reconnexion et
round-trip broker. Pendant une coupure volontaire, `/api/health/` a renvoyé 503
et Celery n'a pas pu joindre le broker. Après reprise : clé AOF `alive`
conservée, health `redis=ok`, worker `pong`.

## 8. Celery et Celery Beat

**PASS.** Une tâche `reports.generate` a été envoyée au worker réel : première
exécution `SUCCESS duplicate=false`, seconde `SUCCESS duplicate=true`. Worker
arrêté, une tâche est restée `PENDING` en file; après redémarrage elle est passée
`SUCCESS`. Beat redémarré a planifié `notifications.dispatch_pending` toutes les
15 secondes, reçue et réussie par le worker.

Les tests unitaires couvrent échec, retry, timeout, idempotence et exécution en
double. La reprise de tâche réelle a été observée; la perte du broker pendant
l'émission reste correctement signalée, pas masquée.

## 9. Backend

**PASS dans le périmètre local.** Suite complète :

```text
DISCOVERED 186
PASS       183
FAIL       0
SKIPPED    3
COVERAGE   87 %
```

Les trois skips sont attendus et nommés : VMware réel, Hyper-V réel, SMTP
externe. Redis n'a pas été skippé pendant cette exécution.

Le probe HTTP réel a confirmé login 200, pagination, validation 400, CSRF 403,
viewer 403, détail cross-tenant 404, jeton invalide/révoqué 401 et publication
agent cross-tenant 403.

## 10. Frontend

**PASS.** `vitest` : 20/20; ESLint : zéro warning; Vite : build réussi, 2 384
modules. Le navigateur réel a ouvert `/login`, puis les routes dashboard,
machines, agents, alertes, anomalies, VMware, Hyper-V, ML, utilisateurs,
settings et audit. Chaque page avait son titre attendu et aucune erreur fatale
« API injoignable ».

Le frontend affiche les états vides du tenant temporaire, le statut temps réel
et garde le polling de secours. Une campagne responsive visuelle exhaustive sur
plusieurs appareils n'a pas été rejouée dans ce run.

## 11. Agent Windows réel

**PASS pour le runtime, pas pour le service.** Un agent Python réel a été enrôlé
contre l'API locale, a émis heartbeat et 53 métriques, puis s'est arrêté proprement
avec zéro lot en attente. Les métriques observées incluent CPU, RAM, disque libre
et utilisé, I/O, réseau entrant/sortant, latence, uptime, processus, GPU et état
du service critique. Version persistée : 2.0.0; machine `ONLINE`.

Le token/enrollment n'a pas été retrouvé dans `agent.log`. L'arrêt de l'agent,
l'évaluation offline et la reprise ont produit : `ONLINE -> OFFLINE` avec alerte
`NEW`, puis `ONLINE` et alerte `RESOLVED`.

## 12. Windows Service

**NOT TESTED.** Le service `InfraSentinelAgent` n'est pas installé et la session
courante n'est pas administrateur. Les 25 tests agent/installateur passent,
incluant DPAPI machine-scope, mais ils ne remplacent pas installation, auto-start,
reboot et désinstallation réels.

## 13. Métriques

**PASS pour Windows et le modèle commun.** Les modèles/indexes et normaliseurs
Windows/VMware/Hyper-V sont couverts par tests. Le runtime réel Windows a persisté
les noms canoniques. Les données spécifiques restent en métadonnées.

VMware et Hyper-V ne sont pas classés PASS réel : leurs métriques ont uniquement
été testées via mocks/fixtures synthétiques.

## 14. Rules Engine

**PASS.** Les tests couvrent opérateurs, durée, enable/disable, scope machine et
environnement, dimensions, service critique, offline et isolation client. Le
scénario réel agent a validé la règle offline; les scénarios PFE CPU/RAM/disque
ont produit les alertes attendues.

## 15. Alert Engine

**PASS.** Création, severity, cooldown, déduplication, corrélation,
acknowledgement/résolution et réouverture prise en charge sont couverts. Un probe
transactionnel avec 100 métriques CPU semblables a laissé une seule alerte
ouverte, pas 100.

## 16. ML anomaly detection

**PASS sur données contrôlées synthétiques; PARTIAL scientifiquement.** Modèle
Isolation Forest réel, version et artefact présents, six features, 36 fenêtres
d'entraînement/validation. Le pipeline chargé a évalué 61 fenêtres : 59 normales,
2 anormales. Une anomalie contrôlée a été persistée et exposée.

Le dataset porte `synthetic=true`. Aucune vérité terrain réelle : précision et
rappel sont `null`, comme exigé plutôt qu'inventés.

## 17. Règles vs ML vs hybride

**PARTIAL.** Comparaison opérationnelle : 4 incidents de règles, 1 anomalie ML,
0 chevauchement à 15 minutes. Cela prouve les trois chemins, pas la supériorité
statistique d'un modèle sans labels.

## 18. Analyse prédictive

**PASS sur série contrôlée.** Après régénération de l'historique dans la fenêtre
de 24 h : tendance `INCREASING`, 4 points/heure, risque 70, confiance `MEDIUM`,
échéance calculée, `is_estimate=true`. Le précédent résultat zéro était causé
par un dataset vieux de plus de 24 h, non par une sortie fabriquée.

## 19. Recommandations

**PASS.** Cinq alertes contrôlées ont des pistes et actions; toutes sont
non-destructives. Les branches contextuelles VMware/Hyper-V sont unit-tested,
sans prétention de collecte réelle.

## 20. WebSocket

**PASS.** Le probe réseau réel a connecté deux clients, reçu la même séquence,
rejoué l'événement manqué après déconnexion et rejeté la réutilisation du ticket
en HTTP 403. Le probe a repassé après redémarrage de l'API.

## 21. Notifications

**PARTIAL.** Modèle, préférences, anti-spam, cooldown, retry, logs et exécution
Celery sont testés. La notification PFE est `SENT` par le backend console.
**NOT TESTED - EXTERNAL SMTP DELIVERY** car aucun host/user/password SMTP n'est
configuré. Une sortie console n'est pas une preuve d'email reçu.

## 22. Hyper-V

**NOT TESTED - REAL HYPER-V PERMISSION REQUIRED.** Le service VMMS et `Get-VM`
existent sur l'hôte, mais `Get-VM` retourne « required permission ». Le collecteur
PowerShell, normaliseur, tâches et mocks passent; aucune VM réelle n'a été lue.

## 23. VMware

**NOT TESTED - REAL VMWARE ENVIRONMENT REQUIRED.** Aucun URL, utilisateur ou
secret vCenter autorisé n'est configuré. Authentification, découverte, erreurs,
normalisation et tâches sont couvertes par mocks, pas par un vCenter réel.

## 24. Multi-tenant et RBAC

**PASS.** Deux tenants temporaires ont été créés. Client A ne voit pas la machine
B dans la liste, reçoit 404 sur son détail, l'agent A reçoit 403 en publiant vers
B et un viewer reçoit 403 sur `/api/users/`. L'administrateur reste limité à son
tenant sauf rôle global explicitement autorisé.

## 25. Charge

**PARTIAL.** Run frais 5/10/25/50 agents, 10 s par palier, une collecte/s : zéro
erreur, mais p95 330,93 ms et CPU API 130,60 % à 50. Le benchmark historique de
30 s montre 9,35 % d'erreurs à 50 et 69,92 % à 100 à cause des 100 connexions PG.
La campagne fraîche s'est arrêtée à la saturation significative; 150/250 ne sont
pas testés.

## 26. Résilience

**PASS pour les scénarios exécutés.** Redis, worker, Beat, API et PostgreSQL ont
été arrêtés/redémarrés séparément. Le stack complet a subi `docker compose down`
puis `up -d --wait` sans `-v`; DB, clé Redis et artefact ML ont survécu. L'API
signale 503 pendant les indisponibilités DB/Redis au lieu d'un faux statut OK.

## 27. Sauvegarde / restauration

**PASS.** Le script a produit un dump custom de 239 678 octets et checksum valide.
Restauration réelle dans `infrasentinel_restore_probe` : 50 migrations, 3
customers, 12 machines et 1 modèle. La base temporaire a ensuite été supprimée.
Le script accepte maintenant `COMPOSE_MODE=local` sans imposer SMTP/domaine de
production; son mode par défaut reste production.

## 28. Sécurité

**PASS dans le périmètre non offensif.** `final_api_probe.py` confirme auth,
RBAC, IDOR, multi-tenant, CSRF, validation, injection de recherche non exposante,
agent révoqué et headers. Aucun motif de clé privée/credential fort n'est suivi
par Git; `.env`, runtime, dumps, logs et tmp sont ignorés.

`npm audit --omit=dev` : 0 vulnérabilité. `pip-audit` a d'abord trouvé deux avis
sur `requests 2.32.3`; passage à 2.33.0, 25 tests agent repassés, puis
`No known vulnerabilities found`.

## 29. Remote/WAN-like

**NOT TESTED - REMOTE WAN ENVIRONMENT UNAVAILABLE.** Aucun tunnel/VPN privé et
aucun agent distant autorisé n'étaient disponibles. Aucun port Django brut n'a
été exposé publiquement.

## 30. Redémarrage hôte

**NOT TESTED.** Un reboot Windows aurait interrompu cette session et exige une
action utilisateur. Seul le restart Docker complet, volumes conservés, est PASS.

## 31. Limites restantes

- service Windows réel et reboot non validés;
- Hyper-V présent mais permission absente;
- aucun vCenter réel;
- aucun SMTP externe ni WAN privé;
- dataset ML synthétique sans labels réels;
- plafond durable de charge inconnu et saturation PG démontrée;
- artefact ML propre au mode runtime : un modèle entraîné dans Docker doit être
  évalué depuis le volume Docker, pas depuis un store hôte différent;
- responsive multi-appareil non rejoué visuellement pendant cette campagne.

## 32. Préparation de la démonstration

`docs/LOCAL_PFE_DEMO.md` fournit les commandes, captures et phrases. Le cœur
logiciel est démontrable localement. Le jury doit voir les labels synthétiques et
les limites réelles; aucune donnée VMware/Hyper-V factice ne doit être présentée
comme collecte.

## 33. Matrice finale

| Exigence | Statut |
|---|---|
| Cloud dependencies removed | PASS |
| Google Cloud work removed | PASS |
| Azure work removed du dépôt | PASS |
| Docker | PASS |
| PostgreSQL | PASS |
| Redis | PASS |
| Celery | PASS |
| Celery Beat | PASS |
| Backend | PASS |
| Frontend | PASS |
| WebSocket | PASS |
| Windows Agent REAL | PASS |
| Windows Service REAL | NOT TESTED |
| Metrics | PARTIAL |
| Rules Engine | PASS |
| Alert Engine | PASS |
| ML Training | PASS contrôlé |
| ML Inference | PASS contrôlé |
| Anomaly Detection | PASS contrôlé |
| Predictive Analysis | PASS contrôlé |
| Recommendations | PASS |
| Hyper-V REAL | NOT TESTED |
| VMware REAL | NOT TESTED |
| SMTP REAL | NOT TESTED |
| Remote WAN | NOT TESTED |
| RBAC | PASS |
| Multi-Tenant | PASS |
| Security | PASS |
| Docker Restart Recovery | PASS |
| Host Reboot Recovery | NOT TESTED |
| Backup / Restore | PASS |
| Load Test | PARTIAL |

Maximum frais : **50 agents**

p50 : **114,53 ms**

p95 : **330,93 ms**

p99 : **381,51 ms**

Erreur : **0 % sur 10 s**

Maximum historique : **100 agents**, avec **69,92 % d'erreurs**

## 34. Corrections réalisées

- retrait de la documentation exclusivement Azure/GCP après audit;
- nouveau contrat d'architecture local/LAN;
- attente de disponibilité et logs par processus dans `start-local.ps1`;
- génération sûre/idempotente du `.env` Docker local;
- sauvegarde PostgreSQL utilisable en mode local;
- mise à jour de `requests` 2.32.3 vers 2.33.0;
- documentation ML, performance et démonstration actualisée.

## 35. Risques par priorité

### HIGH

- saturation PostgreSQL/Daphne sous charge longue à partir de 50 agents
  accélérés; tester pool borné/PgBouncer avant toute promesse de capacité;
- absence de preuve réelle VMware et Hyper-V pour une soutenance qui les annonce.

### MEDIUM

- Windows Service et reboot non validés avec élévation;
- modèle évalué uniquement sur contrôles synthétiques sans labels;
- SMTP externe et réseau WAN non validés;
- store ML distinct entre runtime hôte et volume Docker.

### LOW

- validation responsive visuelle à compléter sur plusieurs viewports;
- soak test de plusieurs heures/jours absent.

## 36. Commandes de reproduction essentielles

```powershell
./scripts/prepare-local-compose-env.ps1
docker compose --env-file .env build
docker compose --env-file .env up -d --wait --wait-timeout 300
docker compose --env-file .env ps -a
./scripts/test-all.ps1 -Database postgresql -RedisIntegration
. ./scripts/common.ps1
Import-DotEnv backend/.env
./.venv/Scripts/python.exe scripts/final_api_probe.py
./.venv/Scripts/python.exe scripts/final_realtime_probe.py
Get-Content -Raw scripts/final_ml_probe.py |
  docker compose --env-file .env exec -T api python -
```

## 37. Action manuelle restante

Pour valider Windows Service et Hyper-V, ouvrir une PowerShell **Administrateur**
sur cet hôte, installer le package test de l'agent puis autoriser le compte à
interroger Hyper-V. Ne pas effectuer ces actions pendant la démonstration sans
fenêtre de rollback et procédure de désinstallation.

## 38. Verdict final

**LOCAL ENTERPRISE LAB PARTIALLY VALIDATED**

Le projet est prêt pour une démonstration locale honnête du cœur Windows,
centralisation, règles, alertes, ML, prédiction, recommandations, temps réel et
multi-tenant. Il n'est pas prêt à revendiquer une validation réelle complète de
VMware, Hyper-V, Windows Service, SMTP externe, WAN ou capacité 250 agents.
