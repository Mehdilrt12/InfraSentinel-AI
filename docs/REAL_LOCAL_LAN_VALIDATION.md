# Validation réelle locale/LAN InfraSentinel AI

**Campagne :** 27 août 2026

**Branche :** `codex/local-enterprise-lab`

**Commit de départ :** `e25b59ed9f4c159b995e4975af2016547a960a9c`

**Tag de retour :** `pre-real-local-lan-validation`

## Portée et règle scientifique

Cette campagne valide la plateforme sur le réseau local, sans cloud. Un écran
qui charge ne suffit pas à prouver une source réelle. Les statuts utilisés sont
`REAL PASS`, `CONTROLLED TEST PASS`, `SIMULATED LOAD TEST PASS`, `PARTIAL`,
`NOT TESTED` et `FAIL`.

## Phases 1 à 3 - checkpoint, audit et nettoyage

Le dépôt était propre sur le commit indiqué ci-dessus. L'audit PostgreSQL a
prouvé que tous les assets opérationnels visibles étaient des objets PFE25
marqués synthétiques. Le détail, la classification et le hash de la sauvegarde
sont consignés dans `docs/REAL_LOCAL_DATA_AUDIT.md`.

Après backup validé par `pg_restore --list`, seuls les objets PFE25 ont été
supprimés. L'API du tenant `cgi` a ensuite renvoyé :

```json
{
  "total_assets": 0,
  "online": 0,
  "offline": 0,
  "anomalies": 0,
  "vmware_hosts": 0,
  "hyperv_hosts": 0,
  "active_alerts": 0
}
```

Les APIs machines, agents, alertes, anomalies et modèles ML renvoient également
un compteur zéro. Aucun seed n'est recréé automatiquement.

## Phases 4 à 8 - réseau, frontend, API et WebSocket

Adresse IPv4 active observée lors de la reprise : `192.168.1.3` sur l'interface
Wi-Fi (l'adresse initiale `192.168.0.133` avait changé entre les deux sessions).
Cette adresse n'est pas écrite dans les fichiers versionnés; le script
`prepare-local-compose-env.ps1 -Lan` l'injecte dans `.env`, qui est ignoré par
Git.

Configuration vérifiée :

| Composant | Écoute | Résultat |
|---|---|---|
| Frontend | `0.0.0.0:5173` | HTTP 200 loopback et IP LAN |
| API | `0.0.0.0:8000` | health `status=ok` loopback et IP LAN |
| PostgreSQL | `127.0.0.1:5432` | non joignable via IP LAN |
| Redis | `127.0.0.1:6379` | non joignable via IP LAN |

Le frontend utilise le proxy same-origin `/api` et `/ws`; aucune URL localhost
n'est imposée à un navigateur distant. Le probe WebSocket effectué contre
`ws://192.168.1.3:8000/ws/events/` avec origine LAN a observé :

```text
clients simultanés: 2
séquence de broadcast identique: true
replay après déconnexion: true
ticket réutilisé: HTTP 403
```

## Phase 9 - pare-feu Windows

**PARTIAL - action administrateur requise.** Le réseau Wi-Fi courant est classé
`Public` et les règles InfraSentinel ne sont pas installées. Le script
`configure-lan-firewall.ps1` est prêt à créer uniquement :

| Port | Protocole | Profil | Source | Usage |
|---:|---|---|---|---|
| 5173 | TCP | Private | LocalSubnet | dashboard React/Nginx |
| 8000 | TCP | Private | LocalSubnet | API, agent et WebSocket |

PostgreSQL et Redis ne sont pas concernés. Le pare-feu ne doit jamais être
désactivé globalement.

## Phase 10 - santé serveur

Commande :

```powershell
docker compose --env-file .env up -d --wait --wait-timeout 300
docker compose --env-file .env ps -a
docker compose --env-file .env exec -T worker celery -A config inspect ping --timeout=10
```

Résultat observé : PostgreSQL, Redis, API, worker, Beat et frontend `healthy`;
migration `Exited (0)`; worker Celery `pong`. Les requêtes réelles `/api/health/`
ont confirmé `database=ok` et `redis=ok`.

## Phase 11 - navigateur principal

**PARTIAL.** Les documents HTML de `/login` sont disponibles en HTTP 200 via
loopback et IP LAN, le proxy frontend/API répond et les endpoints authentifiés
renvoient les états vides attendus. Le contrôle visuel automatisé dans le
navigateur intégré a été refusé par sa politique d'accès aux URL locales; il
n'est donc pas déclaré PASS visuel dans cette campagne. Le test manuel sur le
poste principal et le second appareil reste requis.

## Contrôles de sécurité LAN déjà exécutés

| Contrôle | Résultat |
|---|---|
| Origine CORS `http://192.168.1.3:5173` | autorisée |
| Origine CORS `http://evil.invalid` | aucun header d'autorisation |
| Header `Host: evil.invalid` | HTTP 400 |
| PostgreSQL via `192.168.1.3:5432` | refusé |
| Redis via `192.168.1.3:6379` | refusé |
| `python manage.py check` | 0 issue |
| `python manage.py migrate --check` | à jour |

## Matrice intermédiaire

| Élément | Statut actuel |
|---|---|
| Stack Docker locale | REAL PASS |
| PostgreSQL / Redis | REAL PASS |
| Celery / Beat | REAL PASS |
| Frontend localhost | PARTIAL - HTTP/API vérifiés, visuel manuel restant |
| Frontend LAN | PARTIAL - hôte local vérifié, second appareil restant |
| Backend LAN | REAL PASS depuis l'hôte |
| WebSocket LAN | CONTROLLED TEST PASS depuis l'hôte |
| Dashboard REAL-only | REAL PASS, compteurs zéro cohérents |
| Windows Agent PC #1 | NOT TESTED dans cette campagne après nettoyage |
| Windows Agent PC #2 | NOT TESTED |
| VMware réel | NOT TESTED |
| Hyper-V réel | NOT TESTED |
| Cross-device dashboard | NOT TESTED |

## Prochaine porte de validation

Le profil réseau et le pare-feu exigent des droits administrateur, puis un
second appareil physique doit confirmer la joignabilité. Aucune phase
multi-agent, métriques réelles, ML sur métriques réelles ou temps réel
multi-appareil ne sera déclarée PASS avant ce retour.
