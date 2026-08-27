# Audit de pré-déploiement Google Cloud

**Projet :** InfraSentinel-AI
**Date de l'audit :** 26 août 2026
**Périmètre :** inspection locale et Google Cloud en lecture seule
**Verdict initial :** `BLOCKED — COST NOT VERIFIED`
**Réévaluation du 26 août 2026 :** **READY FOR USER APPROVAL — NOT PROVISIONED**

## Executive summary

Aucune infrastructure InfraSentinel-AI n'a été provisionnée sur Google Cloud pendant cet audit. Aucun service n'a été activé, aucune ressource n'a été créée, aucun rôle IAM n'a été modifié et aucune configuration de facturation n'a été changée.

Le projet Google Cloud actif est `project-091724ac-8f84-46fe-9d2` (nom affiché : `My First Project`, numéro `557576556334`). Il n'est pas identifié comme un projet dédié à InfraSentinel-AI.

Une seconde inspection, effectuée après l'activation de l'essai par l'utilisateur, montre désormais un compte **Free Trial actif**, un crédit disponible de **300,00 USD (100 % restant)**, valable du **26 août 2026 au 22 novembre 2026**, soit 88 jours au moment du contrôle. La console et la documentation officielle indiquent qu'aucun débit n'est effectué pendant l'essai et que le compte se ferme avec arrêt des ressources si le crédit ou la durée sont épuisés sans passage volontaire au compte payant. L'objectif zéro MAD est donc vérifiable tant que le compte n'est jamais mis à niveau et que seuls des produits couverts sont utilisés.

L'état local est techniquement encourageant : la suite complète exécutée le même jour a réussi, le build frontend est valide et la composition Docker de production a déjà démarré avec succès dans un environnement isolé. Néanmoins, le dépôt n'est pas une release immuable : la branche `main` contient 125 changements de travail (65 fichiers suivis modifiés et 60 fichiers non suivis), aucun tag n'existe, et le rapport de validation final conserve des éléments HIGH non résolus. Le dépôt ne doit donc pas encore être déployé comme release de staging officielle.

## 1. Méthode et garanties de non-modification

L'inspection GCP a été effectuée exclusivement dans la console Google Cloud, en lecture seule. La CLI `gcloud` n'est pas installée sur le poste. Les pages suivantes ont été contrôlées : projet actif, synthèse de facturation, crédits, projets liés, budgets, API activées, Compute Engine, Cloud Run, Cloud SQL, IAM, comptes de service et quotas.

Actions explicitement **non effectuées** :

- réouverture ou modification du compte de facturation ;
- ajout ou modification d'un moyen de paiement ;
- activation d'une API ;
- création d'un projet, d'une VM, d'un service Cloud Run, d'une base Cloud SQL, d'un Redis géré, d'une adresse IP ou d'un registre d'images ;
- ajout d'un principal IAM ou création d'un compte de service ;
- création d'un budget ou d'une alerte de coût ;
- engagement de consommation, réservation ou GPU.

## 2. État Google Cloud observé

| Contrôle | Résultat observé | Statut |
|---|---|---|
| Projet actif | `project-091724ac-8f84-46fe-9d2` / `My First Project` | PARTIAL — non dédié à InfraSentinel-AI |
| Numéro de projet | `557576556334` | PASS — lecture seule |
| Facturation août 2026 | 0,00 USD affiché pour le 1–26 août | PASS — état historique uniquement |
| Compte de facturation | compte Free Trial actif ; commande `Fermer le compte de facturation` disponible | PASS après réévaluation |
| Crédits | `Free Trial`, disponible, 100 %, 300,00 USD restants sur 300,00 USD | PASS |
| Validité des crédits | 26 août 2026 → 22 novembre 2026 ; 88 jours restants au contrôle | PASS |
| Protection contre débit personnel | aucun débit pendant l'essai ; fermeture/arrêt des ressources sans mise à niveau | PASS — ne jamais cliquer sur `Mettre à niveau` |
| Budgets/alertes | aucun budget existant ; création maintenant disponible | BLOCKER avant provisionnement |
| Compute Engine | API non activée ; la page propose `Activer` | NOT PROVISIONED |
| Cloud Run | API Admin non activée ; aucun service ou job visible | NOT PROVISIONED |
| Cloud SQL | facturation demandée pour continuer ; aucune instance visible | NOT PROVISIONED |
| Comptes de service | aucune ligne affichée | NOT PROVISIONED |
| IAM | un compte utilisateur principal avec des rôles très larges, dont Propriétaire | HIGH — moindre privilège absent |
| Quotas | page en échec de chargement avec numéro de suivi | NOT VERIFIED |
| MFA | rappel console : authentification en deux étapes requise à partir du 1er septembre 2026 | ACTION UTILISATEUR REQUISE |

Le compte de facturation est volontairement partiellement masqué dans ce document (`01558B-…-42C6B6`) afin de ne pas publier un identifiant complet dans Git.

### API actuellement activées

La console affiche 22 API activées, principalement BigQuery/Dataplex et services de base : Analytics Hub, BigQuery et ses API associées, Dataplex, Datastore, Logging, Monitoring, Cloud SQL component API, Cloud Storage, Trace, Dataform, Google Cloud APIs, Service Management, Service Usage et Telemetry. Aucun trafic pertinent n'était visible dans les graphiques consultés.

Cette liste ne constitue pas une autorisation pour en activer d'autres. En particulier, Compute Engine et Cloud Run Admin restent inactives.

## 3. Vérification de l'objectif zéro coût

### Règles officielles pertinentes

- Le [Google Cloud Free Tier](https://docs.cloud.google.com/free/docs/free-cloud-features) exige un compte de facturation actif et en règle, même pour les ressources couvertes par le Free Tier.
- Compute Engine offre au maximum une instance non préemptible `e2-micro` par mois dans `us-west1`, `us-central1` ou `us-east1`, avec des limites de disque et de trafic. Cette gratuité ne couvre pas une architecture adaptée automatiquement à InfraSentinel-AI.
- [Cloud Run](https://cloud.google.com/run/pricing) possède un quota gratuit, mais les sorties réseau, les instances minimales, les connexions longues et les charges en arrière-plan peuvent générer des frais.
- [Cloud SQL](https://cloud.google.com/sql/pricing) n'a pas de niveau PostgreSQL permanent gratuit adapté au staging. L'essai de 30 jours documenté exige lui aussi une facturation active.
- [Memorystore for Redis](https://cloud.google.com/memorystore/docs/redis/pricing) est facturé selon la capacité provisionnée ; aucun niveau permanent gratuit utilisable n'a été vérifié.
- [Artifact Registry](https://cloud.google.com/artifact-registry/pricing) offre 0,5 Gio-mois, puis facture le stockage, le transfert et certains traitements.
- Une adresse IPv4 externe attachée à une VM est facturable selon la [tarification réseau VPC](https://cloud.google.com/vpc/network-pricing). Au tarif affiché de 0,005 USD/heure, son ordre de grandeur est 3,65 USD/mois pour 730 heures.

### Estimations indicatives, non contractuelles

Les tarifs publics consultés pour `us-central1` donnent les ordres de grandeur suivants avant disque, réseau, sauvegardes et taxes :

| Ressource | Estimation mensuelle | Compatibilité fonctionnelle | Conclusion |
|---|---:|---|---|
| `e2-micro` | ~6,12 USD avant Free Tier | 1 Gio de RAM : insuffisant pour API + PostgreSQL + Redis + worker + beat + frontend + ML | REJECTED |
| `e2-small` | ~12,23 USD | 2 Gio : très insuffisant pour la composition actuelle | REJECTED |
| `e2-medium` | ~24,46 USD | 4 Gio : sous le prérequis documentaire de 8 Gio et sans marge ML | HIGH RISK |
| Cloud SQL `db-f1-micro` | ~7,67 USD avant stockage/réseau | base gérée minimale, sans haute disponibilité | PAID |
| Redis géré | facturé dès le provisionnement | compatible techniquement | PAID |
| IPv4 externe VM | ~3,65 USD | requise pour joindre l'API sans autre exposition publique | PAID |

Ces valeurs ne sont pas un devis. Elles servent à comparer les options avec le crédit disponible. La calculatrice GCP et les quotas du compte devront encore être contrôlés juste avant le provisionnement.

### Décision coût

**COST COVERAGE VERIFIED FOR THE PROPOSED STAGING — USER APPROVAL STILL REQUIRED.**

Le plan mono-VM révisé ci-dessous consommerait environ 176 USD sur les 88 jours si la VM reste allumée en continu, hors trafic exceptionnel et snapshots. Il reste donc environ 124 USD de marge sur le crédit de 300 USD. La garantie « zéro MAD » provient du mode Free Trial sans mise à niveau automatique, et non de l'Always Free. La création d'un budget de 200 USD avec alertes doit précéder la VM ; un budget avertit mais ne bloque pas techniquement la consommation.

## 4. État local avant déploiement

### Git et release

| Élément | État observé | Risque |
|---|---|---|
| Branche | `main` | la branche de travail ne constitue pas une release |
| HEAD | `33c18fa` — `Revue stricte et réparations phases 0-17` | identifiable mais non figé |
| Tags | aucun | HIGH — pas de version déployable immuable |
| Worktree | 65 fichiers suivis modifiés, 60 non suivis, 0 supprimé | HIGH — 125 changements non figés |
| Diff suivi | 3 455 insertions, 585 suppressions dans 65 fichiers | revue/commit nécessaires |

Le déploiement d'un worktree aussi sale rendrait la reproduction et le rollback non fiables. Aucun commit ni tag n'a été créé pendant cet audit.

### Architecture réellement présente

La stratégie de production actuelle est une composition Docker mono-hôte :

```text
Internet / HTTPS
      |
   reverse proxy attendu
      |
  frontend + API Django/ASGI
      |       |        |
 PostgreSQL  Redis   Celery worker + Beat
                      |
                ML / notifications /
                collectes planifiées
```

Le fichier `docker-compose.yml` définit `db`, `redis`, `migrate`, `api`, `frontend`, `worker` et `beat`. Les fichiers d'environnement d'exemple couvrent Django/JWT, PostgreSQL, Redis/Celery, email, hôtes autorisés, CORS, CSRF et paramètres TLS. La configuration de production applique notamment `DEBUG=False`, redirection SSL, cookies sécurisés, inscription publique désactivée, services internes non publiés et restrictions de conteneur.

Il n'existe actuellement ni Terraform, ni configuration Cloud Build, ni manifeste GCP, ni procédure validée propre à GCP. `docs/DEPLOYMENT.md` décrit un VPS Docker générique avec Caddy, recommandé à 4 vCPU, 8 Gio de RAM et 80 Gio SSD.

### Contrôles réellement exécutés

Commandes rapides relancées après l'inspection cloud :

```powershell
. .\scripts\common.ps1
Import-DotEnv 'backend\.env'
$env:DATABASE_ENGINE='postgresql'
.\.venv\Scripts\python.exe backend\manage.py check
.\.venv\Scripts\python.exe backend\manage.py migrate --check

$env:PYTHONPATH=(Join-Path (Get-Location) 'agent')
.\.venv\Scripts\python.exe -m unittest discover agent\tests

Set-Location frontend
npm run test
npm run build
```

Résultats observés :

- Django system check : 0 problème ;
- migrations : aucun écart, code retour 0 ;
- agent Windows : 25 tests réussis sur 25 ;
- frontend : 20 tests réussis sur 20 ;
- Vite : build de production réussi, 2 384 modules transformés.

La suite exhaustive avait été exécutée immédiatement avant cet audit, sur le même code applicatif :

- backend PostgreSQL : 186 tests découverts, 183 réussis, 3 ignorés, 0 échec, couverture 87 % ;
- agent : 25/25 ;
- frontend : 20/20, lint et build réussis ;
- Ruff : réussi ;
- `pip-audit` : aucune vulnérabilité connue détectée ;
- Docker : reconstruction isolée, migrations, API, frontend, PostgreSQL, Redis, worker et beat validés puis ressources temporaires supprimées.

Les trois tests backend ignorés dépendent respectivement d'un SMTP externe réel, d'un VMware réel et d'un Hyper-V réel. Ces intégrations ne doivent pas être annoncées comme validées en environnement réel.

### Blocages applicatifs/release déjà documentés

Le rapport `docs/FINAL_VALIDATION_REPORT.md` conserve le verdict strict **NOT READY FOR PFE DEMO** et les éléments HIGH suivants :

1. scénario de tendance prédictive PFE obsolète (`predictive_trends=0`, risque observé 0 au lieu de 70 attendu) ;
2. service Windows Agent non installé sur la machine de validation ;
3. installateur Windows non signé ;
4. release Git non figée.

Restent également non testés en environnement externe : VMware réel, Hyper-V réel et ses permissions, SMTP externe, HTTPS distant, agent distant, charge finale à 50/100 agents et modèle ML évalué sur données réelles labellisées.

## 5. Plan de déploiement proposé — en attente d'approbation, non exécuté

Le plan le plus proche de l'implémentation actuelle est un staging Docker mono-VM. Il réduit les services gérés, conserve la parité avec `docker-compose.yml`, couvre PostgreSQL/Redis/Celery sans services payants séparés et simplifie le rollback. Son coût estimé reste couvert par le crédit Free Trial.

| Ressource envisagée | Région | Usage | Coût attendu | Couverture Free Tier/crédits | Stratégie d'arrêt/suppression | Statut |
|---|---|---|---|---|---|---|
| Projet GCP dédié `infrasentinel-staging-<suffixe>` | organisation autorisée | isolation IAM, quotas et coûts | 0 USD pour le projet seul | sans objet | supprimer le projet après export | AWAITING APPROVAL |
| Budget projet 200 USD, alertes 50/75/90/100 % | compte/projet | garde-fou à 100/150/180/200 USD | 0 USD | sans objet | supprimer avec le projet | À CRÉER AVANT LA VM |
| VM `e2-standard-2` Debian/Ubuntu, sans GPU | `us-central1-a` proposé | Docker : API, frontend, PostgreSQL, Redis, worker, beat | 0,06701142 USD/h ; ~48,92 USD/mois ; ~141,53 USD/88 jours | couvert par le crédit | arrêter hors démonstration ou supprimer la VM | AWAITING APPROVAL |
| Disque zonal `pd-balanced` 80 Gio | `us-central1-a` | OS, PostgreSQL, modèles, journaux | 0,10 USD/Gio-mois ; ~8 USD/mois ; ~23,15 USD/88 jours | couvert par le crédit | export utile puis supprimer le disque | AWAITING APPROVAL |
| IPv4 externe éphémère | `us-central1` | HTTPS accessible aux agents Windows | 0,005 USD/h ; ~3,65 USD/mois ; ~10,56 USD/88 jours | couvert par le crédit | arrêt VM = libération automatique | AWAITING APPROVAL |
| Caddy + certificat Let's Encrypt | VM | reverse proxy HTTPS | logiciel/certificat 0 USD | sans objet | arrêter Caddy et révoquer si nécessaire | AWAITING DOMAIN CHOICE |
| Artifact Registry | non utilisé dans le plan initial | évité pour réduire ressources et coûts | 0 USD | sans objet | sans objet | EXCLUDED |

**Coût de base continu estimé sur 88 jours : ~175,24 USD**, hors trafic sortant exceptionnel, snapshot et taxes éventuelles. Marge estimée : **~124,76 USD**. Une politique opérationnelle d'arrêt de la VM hors périodes de test réduira fortement ce montant.

### Architecture gérée alternative

Cloud Run + Cloud SQL + Memorystore réduirait l'administration de la VM, mais introduirait des coûts obligatoires pour PostgreSQL et Redis, et ne correspond pas directement aux workers Celery/Beat persistants ni aux WebSockets sans adaptation. Cette option est rejetée pour l'objectif zéro coût et nécessiterait une phase d'architecture supplémentaire.

### Procédure de rollback prévue

Avant toute suppression d'un staging contenant des données utiles :

1. désactiver les agents/connecteurs distants ou pointer leurs URLs vers une maintenance explicite ;
2. exporter PostgreSQL avec `pg_dump` et vérifier le fichier de restauration ;
3. sauvegarder les modèles ML et la configuration non secrète ;
4. arrêter la composition Docker ;
5. supprimer VM, disque, snapshot temporaire, adresse IP et images du registre ;
6. supprimer le projet dédié si plus aucune ressource n'est requise ;
7. contrôler la page de facturation jusqu'à stabilisation à zéro et documenter les éventuels coûts différés.

## 6. Risques classés

### CRITICAL

- **Ne jamais mettre le compte à niveau :** un passage volontaire au compte payant supprimerait la garantie d'absence de débit personnel après consommation des crédits.
- **Absence de projet GCP dédié autorisé :** le projet actif générique ne doit pas être modifié comme s'il appartenait automatiquement au périmètre InfraSentinel-AI.

### HIGH

- worktree Git très sale, sans tag ni artefact de release immuable ;
- rôle Propriétaire et autres rôles larges portés par un compte utilisateur principal, sans compte de service dédié ;
- dimensionnement gratuit `e2-micro` incompatible avec la pile Docker et le ML ;
- validation externe absente pour VMware, Hyper-V, SMTP, HTTPS distant et Windows Service ;
- MFA à activer par le propriétaire du compte avant l'échéance annoncée par la console.

### MEDIUM

- quotas GCP non vérifiés à cause d'une erreur de chargement de la console ;
- aucune infrastructure-as-code GCP ni pipeline de déploiement/rollback automatisé ;
- architecture mono-hôte sans haute disponibilité ;
- persistance et sauvegarde cloud non validées ;
- scénario prédictif de démonstration à remettre en cohérence avec le code actuel.

### LOW

- plusieurs API BigQuery/Dataplex sont déjà activées sans lien démontré avec InfraSentinel-AI ; leur désactivation n'a pas été effectuée car elles peuvent appartenir à un autre usage du projet.

## 7. Conditions obligatoires avant une nouvelle demande d'approbation

1. obtenir l'approbation explicite du plan mono-VM ci-dessus ;
2. créer le projet dédié sans toucher au projet générique existant ;
3. vérifier les quotas Compute Engine du nouveau projet ;
4. créer le budget de 200 USD et ses alertes avant toute ressource facturable ;
5. confirmer que le compte reste Free Trial et ne jamais sélectionner `Mettre à niveau` ;
6. figer le code : revue, commit, tag de release et artefacts reproductibles ;
7. résoudre ou accepter formellement les HIGH du rapport de validation final ;
8. préparer un compte de service dédié avec le strict minimum de permissions ;
9. fournir un domaine ou approuver un nom HTTPS temporaire de staging fondé sur l'IP ;
10. contrôler chaque jour crédits, budget et coût prévisionnel pendant le staging.

## 8. Verdict

**READY FOR USER APPROVAL — CLOUD STAGING NOT PROVISIONED.**

Le crédit et la protection Free Trial permettent maintenant de couvrir le staging proposé sans débit personnel, à condition de ne jamais mettre le compte à niveau. Le plan reste toutefois non autorisé tant que l'utilisateur n'a pas approuvé explicitement les ressources, la région, le budget de 200 USD et la stratégie de suppression. Le dépôt doit aussi être figé avant l'envoi du code. Jusqu'à cette approbation, l'état correct demeure **NOT PROVISIONED**.
