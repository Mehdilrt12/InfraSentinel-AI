# Agent Windows

## Fonctionnement

`Windows startup -> InfraSentinelAgent service -> collecte -> spool -> HTTPS -> API`.
La configuration est un JSON externe dans `%ProgramData%\InfraSentinel\config.json`.
L'installateur lit le code d'enrollment à usage unique depuis un fichier temporaire
protégé, réalise l'enrôlement avant d'enregistrer le service, puis détruit sa copie.
Le token reçu est chiffré avec Windows DPAPI en portée machine, ne figure ni dans le
JSON ni dans les logs, et est transmis uniquement dans l'en-tête `X-Agent-Token`.
Le backend accepte encore `Authorization: Bearer` pour compatibilité, mais le client
professionnel utilise l'en-tête dédié.

Métriques : CPU, RAM, usage/espace disque, I/O, réseau in/out, latence TCP,
uptime, processus, services critiques, OS, hostname et IP. Pour NVIDIA,
`nvidia-smi` fournit optionnellement utilisation GPU, VRAM utilisée, pourcentage
VRAM et température. Une valeur `N/A` ou un GPU absent n'est pas remplacé par zéro.
Le cache SQLite local est borné, FIFO et persistant; ses payloads sont chiffrés par
DPAPI sous Windows et les anciennes lignes en clair restent lisibles uniquement pour
assurer une migration progressive. Retry exponentiel avec jitter,
reconnexion, réponse JSON validée, logs rotatifs, signal d'arrêt et reprise sont
implémentés. Le client refuse les redirections HTTP afin de ne jamais transférer
`X-Agent-Token` vers une autre origine. `verify_tls=false` exige désormais
`allow_insecure_tls=true`; cette dérogation ne doit servir qu'à un diagnostic maîtrisé.

## Installation recommandée

Utiliser le setup Windows généré, en mode interactif ou silencieux. Il configure
le service `InfraSentinelAgent` sous `LocalSystem`, le démarrage automatique
différé et les actions de reprise. La procédure complète se trouve dans
`docs/AGENT_INSTALLATION.md`.

Le script historique reste disponible pour le développement depuis les sources :

```powershell
./scripts/manage-agent-service.ps1 install
./scripts/manage-agent-service.ps1 start
./scripts/manage-agent-service.ps1 status
```

Il ne remplace pas le package d'installation.

## Tests

Depuis le répertoire `agent`, la commande
`../.venv/Scripts/python.exe -m unittest discover -s tests -v` couvre notamment
HTTPS, validation TLS, redirections, chiffrement DPAPI du spool, spool/restart,
indisponibilité, reconnexion, arrêt propre, collecte minimale et compteurs de débit,
token invalide et en-tête secret. Le test backend de bout en bout couvre enrollment,
heartbeat, métrique PostgreSQL et token révoqué. Le setup 2.0.0 a également été
validé en administrateur sur Windows 11 : installation, upgrade, redémarrage du
service, désinstallation et conservation de la configuration.

## Configuration externe

```json
{
  "backend_url": "https://monitoring.example.net",
  "machine_name": "WINDOWS-SRV-01",
  "interval_seconds": 30,
  "heartbeat_seconds": 60,
  "request_timeout_seconds": 15,
  "verify_tls": true,
  "allow_insecure_tls": false,
  "critical_services": ["W32Time", "WinRM"],
  "latency_host": "monitoring.example.net",
  "latency_port": 443,
  "spool_max_items": 10000,
  "log_max_bytes": 5242880,
  "log_backup_count": 5,
  "allow_http_localhost": false
}
```

`backend_url` doit normalement être HTTPS. HTTP n'est accepté que pour localhost
avec l'option explicite de développement. L'enrôlement utilise
`POST /api/agent/enroll/`; heartbeat et mesures utilisent
`/api/agent/heartbeat/` et `/api/agent/metrics/`. L'API valide la version et le
jeton et rattache le payload à la machine enregistrée.

## Collecte, limites et dépannage

Les compteurs cumulés disque/réseau deviennent des débits entre deux cycles; le
premier cycle peut ne pas avoir de taux exploitable. GPU NVIDIA dépend de l'outil
fournisseur. Le spool est vidé dans l'ordre après le retour du serveur.

- service absent : exécuter `Get-Service InfraSentinelAgent` en administrateur;
- enrôlement refusé : vérifier code non utilisé/non expiré, URL et horloge;
- token invalide : révoquer/réenrôler sans copier le token dans un log;
- API indisponible : vérifier HTTPS/DNS/pare-feu; le spool doit se vider ensuite;
- erreur TLS : corriger le certificat, ne pas désactiver TLS en production;
- GPU absent : comportement normal si aucun GPU compatible n'est présent ;
- GPU présent : vérifier les séries `system.gpu.utilization`,
  `system.gpu.memory.used`, `system.gpu.memory.utilization` et
  `system.gpu.temperature`. La puissance et le throttling restent des garde-fous
  du banc de test, pas des métriques envoyées par l'agent.

La validation locale du setup ne remplace pas une campagne sur toutes les versions
Windows cibles ni une signature de code publique. Voir
[AGENT_INSTALLATION.md](AGENT_INSTALLATION.md).
