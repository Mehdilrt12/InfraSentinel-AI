# Installation de l'agent Windows

## Résultat attendu

```text
Setup téléchargé
  -> configuration URL + jeton d'enrôlement
  -> enrôlement auprès de l'API
  -> token agent protégé par DPAPI
  -> service Windows InfraSentinelAgent
  -> démarrage automatique différé
  -> heartbeat ONLINE + collecte périodique
```

Le package cible Windows 10/11 et Windows Server modernes en x64. L'installation
requiert un compte administrateur. Le serveur doit être joignable en HTTPS avec un
certificat valide; HTTP n'est accepté que sur loopback avec une option réservée aux
tests locaux.

## Construire le package

Prérequis de construction : Windows x64, Python 3.14, les dépendances de
`agent/requirements-build.txt` et Inno Setup 6.

```powershell
python -m pip install -r agent/requirements-build.txt
winget install --id JRSoftware.InnoSetup -e
powershell -ExecutionPolicy Bypass -File scripts/build-windows-agent.ps1
```

Le script exécute les tests unitaires, construit
`agent/dist/InfraSentinelAgent.exe`, compile le setup et génère son SHA-256 dans :

```text
installer/windows/output/InfraSentinelAgent-2.0.0-setup.exe
installer/windows/output/InfraSentinelAgent-2.0.0-setup.exe.sha256
```

Les répertoires de build sont ignorés par Git. Publier ensemble le setup et son
fichier SHA-256 sur un dépôt d'artefacts HTTPS contrôlé, puis renseigner
`VITE_AGENT_INSTALLER_URL` au build du frontend pour afficher le bouton de
téléchargement dans `/agents`. Le binaire construit dans ce dépôt n'est pas signé
Authenticode : une signature de code d'entreprise est obligatoire avant une
diffusion de production.

## Installation interactive

1. Dans le dashboard, créer un code d'enrôlement pour un environnement Windows ou
   mixte du client concerné.
2. Télécharger le setup depuis le dépôt d'artefacts approuvé et vérifier le hash.
3. Exécuter le setup en administrateur.
4. Saisir l'URL HTTPS du serveur, le nom de machine souhaité et le code à usage
   unique.
5. Le setup n'annonce la fin qu'après configuration, enregistrement et démarrage du
   service.
6. Vérifier dans le dashboard que l'agent et sa machine sont `ONLINE`.

Le code d'enrôlement n'est jamais ajouté à `config.json`. Le token permanent émis
par le serveur est stocké dans
`C:\ProgramData\InfraSentinel\credentials.dat`, chiffré avec DPAPI en portée
machine. Le répertoire de données n'accorde l'accès qu'à `LocalSystem` et au groupe
Administrateurs.

## Installation silencieuse

Ne placez jamais le code d'enrôlement directement dans les arguments du processus.
Créez un fichier à ACL restrictive, puis transmettez seulement son chemin :

```powershell
$setup = 'C:\Packages\InfraSentinelAgent-2.0.0-setup.exe'
$enrollmentFile = 'C:\SecureTemp\infrasentinel-enrollment.txt'

$process = Start-Process -FilePath $setup -Verb RunAs -Wait -PassThru -ArgumentList @(
  '/VERYSILENT',
  '/SUPPRESSMSGBOXES',
  '/NORESTART',
  '/SERVERURL=https://sentinel.example.net',
  "/ENROLLMENTFILE=$enrollmentFile",
  '/MACHINENAME=WINDOWS-SRV-01'
)
if ($process.ExitCode -ne 0) {
  throw "Installation refusée : $($process.ExitCode)"
}
```

Le setup copie le fichier dans son répertoire temporaire protégé et demande à
l'agent d'écraser puis supprimer cette copie. Le fichier source reste sous la
responsabilité de l'outil de déploiement et doit être supprimé après usage. Le
journal Inno Setup contient le chemin du fichier, jamais son contenu.

Pour le laboratoire local uniquement, ajouter `/ALLOWHTTPLOCALHOST=1` avec une URL
`http://127.0.0.1:<port>`. Cette dérogation ne permet pas HTTP vers une adresse
distante.

## Service et fichiers

| Élément | Valeur |
|---|---|
| Service | `InfraSentinelAgent` |
| Compte | `LocalSystem` |
| Démarrage | automatique différé |
| Reprise | 5 s, 15 s puis 60 s après échecs successifs |
| Programme | `C:\Program Files\InfraSentinel Agent\InfraSentinelAgent.exe` |
| Configuration | `C:\ProgramData\InfraSentinel\config.json` |
| Secret DPAPI | `C:\ProgramData\InfraSentinel\credentials.dat` |
| Cache hors-ligne | `C:\ProgramData\InfraSentinel\spool.sqlite3` |
| Logs rotatifs | `C:\ProgramData\InfraSentinel\logs\agent.log` |

Commandes de diagnostic, depuis PowerShell administrateur :

```powershell
Get-Service InfraSentinelAgent
sc.exe qc InfraSentinelAgent
Restart-Service InfraSentinelAgent
Get-Content 'C:\ProgramData\InfraSentinel\logs\agent.log' -Tail 100
```

Les logs ne contiennent ni token agent ni code d'enrôlement. Les messages de
transport peuvent contenir l'URL du serveur mais pas les secrets.

## Mise à niveau

Exécuter le nouveau setup avec le même `AppId`. Le setup :

1. valide le token DPAPI existant par heartbeat;
2. conserve les réglages de collecte existants;
3. arrête le service;
4. remplace le binaire et met à jour le service;
5. redémarre le service.

Un nouveau fichier d'enrôlement n'est pas requis tant que le token agent est valide.
En silencieux, `/SERVERURL` et `/MACHINENAME` sont facultatifs lors d'une mise à
niveau; leur absence conserve les valeurs courantes. Pour changer de tenant ou
réenrôler un agent révoqué, fournir un nouveau code valide.

## Désinstallation

La désinstallation arrête et supprime le service puis retire les fichiers de
`Program Files`. La configuration, le token DPAPI, le spool et les logs restent dans
`ProgramData` afin de permettre une réinstallation sans perte de contexte.

Pour une suppression définitive, révoquer d'abord l'agent dans le serveur, puis
utiliser le script de purge. Il exige une confirmation, refuse d'agir si le service
existe encore et vérifie que la cible résolue est exactement le répertoire attendu :

```powershell
powershell -ExecutionPolicy Bypass -File scripts/purge-windows-agent-data.ps1 `
  -ConfirmPurge
```

Cette purge est irréversible.

## Procédure de validation

Tests unitaires et construction :

```powershell
Push-Location agent
../.venv/Scripts/python.exe -m unittest discover -s tests -v
Pop-Location
powershell -ExecutionPolicy Bypass -File scripts/build-windows-agent.ps1
```

Cycle système complet, dans PowerShell administrateur sur une machine de test sans
service InfraSentinel préexistant :

```powershell
powershell -ExecutionPolicy Bypass -File scripts/test-windows-agent-installer.ps1 `
  -SetupPath installer/windows/output/InfraSentinelAgent-2.0.0-setup.exe `
  -ServerUrl https://sentinel.example.net `
  -EnrollmentFile C:\SecureTemp\valid-enrollment.txt
```

Le script refuse de démarrer si le service existe déjà. Il vérifie successivement :

| Scénario | Résultat obligatoire |
|---|---|
| jeton invalide | setup non nul, aucun service |
| serveur indisponible | setup non nul, aucun service |
| installation valide | service `Running`, démarrage automatique |
| upgrade sans nouveau code | token existant validé, service `Running` |
| restart | retour à `Running` en moins de 30 secondes |
| uninstall | service supprimé |
| conservation | `config.json` toujours présent |

## Validation réalisée le 25 août 2026

Environnement : Windows 11 x64 build 26200, Python 3.14.6, PyInstaller 6.21.0,
Inno Setup 6.7.3 et API locale réelle. Le cycle élevé a produit :

```text
InvalidToken           PASS
ServerUnavailable      PASS
Installation           PASS
Upgrade                PASS
ServiceRestart         PASS
Uninstall              PASS
ConfigurationPreserved PASS
```

Le backend a confirmé la machine `LEGION-phase23` en état `ONLINE`, l'agent en
version 2.0.0, un heartbeat réel et 84 métriques normalisées sur les deux cycles de
validation. Le mode d'upgrade
validé est une réinstallation de la même version, ce qui exerce le chemin technique
`stop -> update -> start`; une montée entre deux versions différentes devra être
réexécutée lorsqu'une version 2.0.1 ou supérieure existera. Le transport de ce test
était HTTP loopback avec l'option de laboratoire; un test de recette sur l'URL HTTPS
de production reste obligatoire avant diffusion.
