# Installation sur un autre laptop Windows

Ce parcours installe une nouvelle plateforme InfraSentinel AI autonome depuis
le dépôt GitHub. Il ne copie ni secrets ni base de données depuis un autre
poste.

## Prérequis

- Windows 10/11 64 bits avec virtualisation activée;
- Docker Desktop avec le moteur WSL 2;
- Git;
- PowerShell 5.1 ou 7;
- au moins 8 Go de RAM (12 Go recommandés) et 15 Go libres;
- ports 5173 et 8000 disponibles.

Python et Node.js ne sont pas requis sur l'hôte pour le mode Docker complet.

## Installation en une commande

```powershell
git clone https://github.com/Mehdilrt12/InfraSentinel-AI.git
cd InfraSentinel-AI
Set-ExecutionPolicy -Scope Process Bypass
./scripts/bootstrap-windows-laptop.ps1
```

Le script :

1. vérifie et démarre Docker Desktop;
2. génère localement les secrets manquants dans `.env`;
3. construit et démarre PostgreSQL, Redis, Django, Celery, Beat et React;
4. applique et vérifie les migrations;
5. demande l'organisation, l'email et le mot de passe du premier administrateur;
6. crée le tenant et l'environnement Windows initial;
7. vérifie la santé applicative.

Le mot de passe est saisi avec `Read-Host -AsSecureString`, transmis au
conteneur par l'entrée standard, puis effacé de la mémoire non managée. Il
n'apparaît ni dans Git, ni dans `.env`, ni dans la ligne de commande.

Ouvrir ensuite :

```text
http://127.0.0.1:5173/login
```

## Options non interactives partielles

L'organisation et l'email peuvent être fournis sans placer le mot de passe sur
la ligne de commande :

```powershell
./scripts/bootstrap-windows-laptop.ps1 `
  -Organization 'My Company' `
  -AdminEmail 'admin@example.com'
```

Le mot de passe reste demandé de manière sécurisée. Une seconde exécution est
idempotente : elle ne remplace pas le mot de passe d'un administrateur existant.

Utiliser `-SkipBuild` pour redémarrer les images déjà construites et
`-SkipAdmin` pour préparer seulement l'infrastructure.

## Mode LAN

```powershell
./scripts/bootstrap-windows-laptop.ps1 -Lan
```

L'adresse IPv4 active est détectée et stockée uniquement dans `.env`. Le
frontend/API écoutent sur le LAN, tandis que PostgreSQL et Redis restent sur
`127.0.0.1`.

Sur un réseau privé de confiance, ouvrir PowerShell comme administrateur :

```powershell
Set-NetConnectionProfile -InterfaceAlias 'Wi-Fi' -NetworkCategory Private
./scripts/configure-lan-firewall.ps1 -Action Install
```

Les règles autorisent seulement TCP 5173/8000 depuis `LocalSubnet` sur le
profil Private. Ne jamais désactiver globalement le pare-feu.

## Commandes quotidiennes

```powershell
# Etat
docker compose --env-file .env ps

# Redémarrage
docker compose --env-file .env up -d --wait

# Arrêt sans supprimer les données
docker compose --env-file .env down

# Mise à jour
git pull --ff-only
./scripts/bootstrap-windows-laptop.ps1
```

Ne pas utiliser `docker compose down -v` sauf si la suppression définitive de
la base, de Redis et des modèles ML est réellement voulue.

## Dépannage

- Docker indisponible : ouvrir Docker Desktop et vérifier WSL 2 avec
  `wsl --status`.
- Port occupé : `Get-NetTCPConnection -State Listen -LocalPort 5173,8000`.
- API indisponible : `docker compose --env-file .env logs api --tail 100`.
- Santé : `Invoke-RestMethod http://127.0.0.1:8000/api/health/`.
- Repartir d'un checkout propre ne nécessite jamais de copier `.env` depuis un
  autre poste; le script génère de nouveaux secrets locaux.

## Limites de validation

Le script a reconstruit et démarré la stack Windows/Docker existante, reconnu un
administrateur sans modifier son mot de passe, puis réussi un bootstrap sur une
base PostgreSQL entièrement vide : 1 tenant, 1 admin, 1 environnement et 2 logs
d'audit. La régression associée compte 191 tests backend (188 réussis, 3 skips),
25 tests agent et 20 tests frontend, sans échec.

Un second laptop physique reste une validation distincte : sa version de
Windows, WSL, Docker et ses règles de sécurité peuvent nécessiter une
intervention manuelle.
