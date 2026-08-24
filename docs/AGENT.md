# Agent Windows

## Fonctionnement

`Windows startup -> InfraSentinelAgent service -> collecte -> spool -> HTTPS -> API`.
La configuration est un JSON externe dans `%ProgramData%\InfraSentinel\config.json`.
Le code d'enrollment initial vient de `INFRASENTINEL_ENROLLMENT_CODE`; il est à
usage unique. Le token reçu est chiffré avec Windows DPAPI, ne figure ni dans le
JSON ni dans les logs, et est transmis uniquement dans l'en-tête `X-Agent-Token`.
Le backend accepte encore `Authorization: Bearer` pour compatibilité, mais le client
professionnel utilise l'en-tête dédié.

Métriques : CPU, RAM, usage/espace disque, I/O, réseau in/out, latence TCP,
uptime, processus, GPU NVIDIA optionnel, services critiques, OS, hostname et IP.
Le cache SQLite local est borné, FIFO et persistant. Retry exponentiel avec jitter,
reconnexion, réponse JSON validée, logs rotatifs, signal d'arrêt et reprise sont
implémentés.

## Installation service

Dans une console Administrateur :

```powershell
./scripts/manage-agent-service.ps1 install
./scripts/manage-agent-service.ps1 start
./scripts/manage-agent-service.ps1 status
```

L'installation configure `--startup auto`. Aucun EXE graphique n'est fourni.

## Tests

`./.venv/Scripts/python.exe -m unittest discover -s agent/tests` couvre huit
scénarios : HTTPS, spool/restart, indisponibilité, reconnexion, arrêt propre,
collecte minimale et compteurs de débit, token invalide et en-tête secret. Le test
backend de bout en bout couvre enrollment, heartbeat, métrique PostgreSQL et token
révoqué. L'installation effective du service reste à valider en Administrateur.
