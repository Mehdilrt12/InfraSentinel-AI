# Agent Windows

## Fonctionnement

`Windows startup -> InfraSentinelAgent service -> collecte -> spool -> HTTPS -> API`.
La configuration est un JSON externe dans `%ProgramData%\InfraSentinel\config.json`.
Le code d'enrollment initial vient de `INFRASENTINEL_ENROLLMENT_CODE`; il est à
usage unique. Le token reçu est chiffré avec Windows DPAPI, ne figure ni dans le
JSON ni dans les logs, et est transmis uniquement dans l'en-tête Authorization.

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

`./.venv/Scripts/python.exe -m unittest discover agent/tests` couvre configuration
HTTPS, spool/restart, token invalide, en-tête secret et validation des réponses.
Les tests du backend couvrent enrollment, heartbeat et isolation inter-client.

