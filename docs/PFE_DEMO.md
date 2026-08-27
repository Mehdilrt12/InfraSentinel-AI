# Scénarios de démonstration PFE

## Objectif et règle d'honnêteté

Ce guide prépare une démonstration reproductible d'InfraSentinel-AI devant le
jury. Il couvre Windows, les hyperviseurs, les règles, les alertes, le ML, les
recommandations, les permissions, l'isolation multi-client et les notifications.

Les données créées par `prepare_pfe_demo` sont toutes marquées
`synthetic=true` et `demo_suite=PFE25`. Les connecteurs VMware et Hyper-V sont
désactivés, utilisent des domaines `.invalid` et portent le libellé
`DÉMO SYNTHÉTIQUE — NON CONNECTÉ`. Ils ne prouvent donc pas une connexion à un
vCenter ou à un hôte Hyper-V réel.

Phrase d'ouverture recommandée :

> Cette démonstration utilise un jeu synthétique reproductible pour déclencher
> les cas difficiles à provoquer devant le jury. Je distinguerai explicitement
> ce qui est exécuté par les vrais moteurs de ce qui dépend d'une infrastructure
> VMware ou Hyper-V externe non disponible.

## Résultat réellement observé

La préparation et la vérification ont été exécutées localement le 25 août 2026
sur PostgreSQL, Redis, Daphne, Celery et le frontend déjà démarrés.

| Élément | Résultat observé |
|---|---:|
| Utilisateurs de rôles distincts | 5 |
| Machines du tenant de démonstration | 11 |
| Machines online / offline | 10 / 1 |
| Métriques normalisées synthétiques | 250 |
| Règles configurables | 5 |
| Alertes actives | 5 |
| Recommandations non destructives | 5 |
| Assets VMware | 1 hôte, 1 VM, 1 datastore |
| Assets Hyper-V | 1 hôte, 1 VM |
| Modèle Isolation Forest actif | 1, entraîné sur 36 fenêtres synthétiques |
| Anomalie ML | 1, sur `[DEMO] WIN-ML-ANOMALY` |
| Tendance prédictive | croissante, risque 70, confiance MEDIUM |
| Notification | 1 livraison `SENT` vers le backend email console |
| Isolation | 404 dans les deux sens entre les deux tenants |

Le dashboard a affiché 11 assets, 10 online, 1 offline, 2 critiques, 1 anomalie,
1 hôte VMware, 1 hôte Hyper-V et 5 alertes actives.

## Préparation avant le jury

### Prérequis

- PostgreSQL et Redis sains ;
- backend Daphne, worker Celery, Beat et frontend démarrés ;
- `backend/.env` configuré avec `EMAIL_BACKEND` sur le backend console ;
- un tenant local réservé à la démonstration, sans modèle ML réel actif ;
- le port 5173 accessible depuis le navigateur de présentation ;
- résolution d'écran recommandée : 1440 × 900 ou supérieure.

Le préparateur refuse d'écraser un modèle actif non PFE. Il ne transmet jamais
d'email externe : si le backend email n'est pas le backend console, la livraison
reste en attente.

### Création du jeu de démonstration

Depuis la racine du projet, remplacer `<tenant-slug>` par le slug du tenant qui
sera utilisé par le compte présentateur. Le mot de passe est demandé sans être
écrit dans la commande ni conservé dans le repository.

```powershell
. .\scripts\common.ps1
Import-DotEnv 'backend\.env'

$securePassword = Read-Host 'Mot de passe temporaire des comptes PFE' -AsSecureString
$passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
try {
  $env:PFE_DEMO_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
  Push-Location backend
  ..\.venv\Scripts\python.exe manage.py prepare_pfe_demo `
    --customer-slug <tenant-slug> `
    --reset
  Pop-Location
}
finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
  Remove-Item Env:PFE_DEMO_PASSWORD -ErrorAction SilentlyContinue
}
```

Comptes créés dans le tenant principal, avec le mot de passe saisi :

- `pfe25.admin.<tenant-slug>@demo.invalid` ;
- `pfe25.supervisor.<tenant-slug>@demo.invalid` ;
- `pfe25.technician.<tenant-slug>@demo.invalid` ;
- `pfe25.client.<tenant-slug>@demo.invalid` ;
- `pfe25.viewer.<tenant-slug>@demo.invalid`.

Le tenant isolé reçoit `pfe25.viewer.isolated@demo.invalid`.

### Vérification sans modification

```powershell
Push-Location backend
..\.venv\Scripts\python.exe manage.py prepare_pfe_demo `
  --customer-slug <tenant-slug> `
  --verify-only
Pop-Location
```

La sortie attendue contient au minimum 11 machines, 250 métriques, 5 règles,
5 alertes, 5 recommandations, 1 anomalie, 1 modèle synthétique actif, un risque
prédictif de 70 et une livraison `SENT`.

## Ordre de présentation recommandé

Durée cible : 15 à 20 minutes.

1. Dashboard global et machine Windows normale.
2. CPU, RAM, disque et machine offline.
3. Génération d'alerte et recommandation.
4. VMware puis Hyper-V, avec annonce explicite du mode synthétique.
5. Isolation Forest et tendance prédictive.
6. RBAC puis isolation multi-client.
7. Notification console et journal d'audit.

## Scénario 1 — Windows normal

- **Préconditions :** jeu PFE préparé ; session ADMIN ; page `/machines`.
- **Action :** ouvrir `[DEMO] WIN-NORMAL`, puis afficher son historique normalisé.
- **Données générées :** 36 fenêtres de six métriques : CPU autour de 38 %, RAM
  autour de 55 %, disque autour de 61 %, trafic réseau et latence stables.
- **Comportement attendu :** machine `ONLINE`, courbes régulières, aucune alerte et
  aucune anomalie associée à cette machine.
- **Résultat observé :** machine online ; 0 alerte ; 0 anomalie ; métriques visibles
  dans l'historique.
- **Capture à réaliser :** `01-windows-normal.png`, avec le statut et les courbes.
- **Phrase à expliquer au jury :** « Toutes les sources alimentent le même historique
  normalisé ; ici le comportement reste dans son profil habituel et aucun moteur
  ne crée d'événement inutile. »

## Scénario 2 — Anomalie CPU

- **Préconditions :** règle `[PFE DEMO] CPU critique` active, seuil `> 90 %`
  pendant 60 secondes.
- **Action :** ouvrir `[DEMO] WIN-CPU`, puis `/alerts`.
- **Données générées :** deux valeurs CPU successives, 94 % puis 95 %, espacées de
  80 secondes.
- **Comportement attendu :** respect de la durée, puis création d'une seule alerte
  durable CRITICAL au lieu d'une alerte par mesure.
- **Résultat observé :** alerte `RULE_THRESHOLD`, sévérité `CRITICAL`, statut `NEW`,
  occurrence 1.
- **Capture à réaliser :** `02-cpu-critical.png`, avec la règle, la valeur et l'alerte.
- **Phrase à expliquer au jury :** « Le dépassement instantané ne suffit pas : le
  moteur conserve un état et ne déclenche qu'après la durée configurée. »

## Scénario 3 — Anomalie RAM

- **Préconditions :** règle `[PFE DEMO] RAM élevée` active, seuil `> 90 %`
  pendant 60 secondes.
- **Action :** ouvrir `[DEMO] WIN-RAM`, puis filtrer les alertes sur cette machine.
- **Données générées :** 93 % puis 94 % de RAM sur une durée supérieure à 60 secondes.
- **Comportement attendu :** alerte HIGH avec contexte de mesure et recommandation
  mémoire.
- **Résultat observé :** une alerte HIGH `NEW` est présente pour `[DEMO] WIN-RAM`.
- **Capture à réaliser :** `03-ram-high.png`.
- **Phrase à expliquer au jury :** « Le diagnostic reste non destructif : il propose
  d'identifier les processus consommateurs et de rechercher une fuite mémoire avant
  toute augmentation de capacité. »

## Scénario 4 — Saturation disque

- **Préconditions :** règle `[PFE DEMO] Disque saturé` active, seuil `> 90 %`
  pendant 60 secondes.
- **Action :** ouvrir `[DEMO] WIN-DISK`, puis consulter son alerte.
- **Données générées :** 95 % puis 96 % d'utilisation disque.
- **Comportement attendu :** alerte HIGH, conservation de l'historique, recommandation
  de diagnostic et aucune suppression automatique de fichiers.
- **Résultat observé :** une alerte HIGH `NEW` et une recommandation non destructive.
- **Capture à réaliser :** `04-disk-saturation.png`.
- **Phrase à expliquer au jury :** « La plateforme avertit et explique ; elle ne
  lance jamais un nettoyage dangereux sans validation humaine. »

## Scénario 5 — Machine offline

- **Préconditions :** règle `[PFE DEMO] Machine hors ligne` active ; timeout de
  300 secondes.
- **Action :** montrer le dashboard, puis ouvrir `[DEMO] WIN-OFFLINE`.
- **Données générées :** dernier contact positionné 15 minutes dans le passé.
- **Comportement attendu :** passage `OFFLINE`, événement temps réel et alerte
  `MACHINE_OFFLINE` dédupliquée.
- **Résultat observé :** 1 machine offline sur le dashboard et une alerte CRITICAL
  `NEW` intitulée « `[DEMO] WIN-OFFLINE ne répond plus` ».
- **Capture à réaliser :** `05-machine-offline.png`, avec compteur global et ligne machine.
- **Phrase à expliquer au jury :** « L'absence de heartbeat devient un événement de
  supervision centralisé, soumis au même cycle de vie que les alertes de métriques. »

## Scénario 6 — Monitoring d'un hôte VMware

- **Préconditions :** page `/vmware` ; connecteur `[DÉMO SYNTHÉTIQUE — NON CONNECTÉ]`
  désactivé.
- **Action :** annoncer le mode synthétique, ouvrir l'asset
  `[DEMO SYNTHÉTIQUE] ESXI-01` et consulter ses métriques.
- **Données générées :** asset HOST, état `connected`, CPU 72 %, RAM 68 %, parent
  racine et metadata `synthetic=true`.
- **Comportement attendu :** inventaire hôte/VM/datastore et métriques normalisées,
  sans tentative de connexion au domaine `.invalid`.
- **Résultat observé :** 1 connecteur, 1 hôte, 1 VM et 1 datastore affichés ; dernière
  collecte « Jamais » ; le connecteur porte un état d'erreur de démonstration.
- **Capture à réaliser :** `06-vmware-host-synthetic.png`, en gardant le libellé
  `NON CONNECTÉ` visible.
- **Phrase à expliquer au jury :** « Le connecteur et le normaliseur sont implémentés,
  mais ce scénario d'interface est synthétique ; je ne prétends pas avoir interrogé
  un vCenter réel pendant cette démonstration. »

## Scénario 7 — Monitoring d'une VM VMware

- **Préconditions :** inventaire VMware synthétique visible.
- **Action :** ouvrir `[DEMO SYNTHÉTIQUE] VM-APP-01`.
- **Données générées :** asset VM `poweredOn`, parent `host-01`, CPU 44 % et RAM 57 %.
- **Comportement attendu :** relation VM → hôte conservée et métriques accessibles
  via la machine normalisée liée.
- **Résultat observé :** la VM est listée sous VMware, avec parent, état et deux
  métriques normalisées.
- **Capture à réaliser :** `07-vmware-vm-synthetic.png`.
- **Phrase à expliquer au jury :** « Les informations spécifiques VMware restent
  dans les metadata, tandis que CPU et RAM utilisent les mêmes noms normalisés que
  Windows et Hyper-V. »

## Scénario 8 — Monitoring d'un hôte Hyper-V

- **Préconditions :** page `/hyperv` ; connecteur Hyper-V de démonstration désactivé.
- **Action :** annoncer le mode synthétique, puis ouvrir
  `[DEMO SYNTHÉTIQUE] HV-01`.
- **Données générées :** asset HOST `Running`, CPU 63 % et RAM 71 %.
- **Comportement attendu :** affichage du host et de ses métriques sans exécuter de
  commande PowerShell distante.
- **Résultat observé :** 1 connecteur, 1 hôte et 1 VM affichés ; dernière collecte
  « Jamais » et endpoint `hyperv.demo.invalid`.
- **Capture à réaliser :** `08-hyperv-host-synthetic.png`.
- **Phrase à expliquer au jury :** « Les commandes PowerShell réelles sont isolées
  dans le collecteur ; ici je montre uniquement un inventaire synthétique clairement
  étiqueté, car aucun hôte Hyper-V externe n'est joint. »

## Scénario 9 — Monitoring d'une VM Hyper-V

- **Préconditions :** inventaire Hyper-V synthétique visible.
- **Action :** ouvrir `[DEMO SYNTHÉTIQUE] HV-VM-01`.
- **Données générées :** asset VM `Running`, parent `hv-host-01`, CPU 39 %, RAM 52 %
  et métrique spécifique `hyperv.vm.state=Running`.
- **Comportement attendu :** les métriques communes alimentent les moteurs génériques
  et l'état spécifique Hyper-V reste disponible dans les metadata.
- **Résultat observé :** VM liée au host, état `Running` et trois métriques visibles.
- **Capture à réaliser :** `09-hyperv-vm-synthetic.png`.
- **Phrase à expliquer au jury :** « La normalisation ne détruit pas l'information
  métier : elle unifie CPU/RAM et conserve simultanément l'état propre à Hyper-V. »

## Scénario 10 — Détection d'anomalie ML

- **Préconditions :** page `/ml` ; modèle PFE actif ; badge de données synthétiques visible.
- **Action :** montrer la version, les paramètres, puis l'anomalie de
  `[DEMO] WIN-ML-ANOMALY`.
- **Données générées :** 36 fenêtres d'entraînement synthétiques avec six features,
  puis une combinaison multivariée inhabituelle sur la machine ML.
- **Comportement attendu :** entraînement Isolation Forest reproductible, scoring de
  la fenêtre ciblée, anomalie persistée et alerte HIGH associée.
- **Résultat observé :** 1 fenêtre évaluée, 1 anomalie créée ; score
  `0,02533356`, seuil `3,12e-17`, modèle actif à 200 estimateurs, contamination 0,02
  et `random_state=42`.
- **Capture à réaliser :** `10-ml-anomaly.png`, avec la mention « fenêtres synthétiques
  de démonstration », la version et le score.
- **Phrase à expliquer au jury :** « Le modèle a réellement été entraîné et exécuté,
  mais le dataset est explicitement synthétique ; la plateforme ne le présente pas
  comme un apprentissage de production. »

## Scénario 11 — Tendance prédictive

- **Préconditions :** machine `[DEMO] WIN-TREND` et règle CPU à 85 %.
- **Action :** ouvrir la machine et descendre jusqu'à « Tendances prédictives ».
- **Données générées :** 13 valeurs CPU sur six heures, de 50 % à 74 %, progression
  linéaire de 4 points par heure.
- **Comportement attendu :** tendance `INCREASING`, estimation de franchissement,
  score de risque et avertissement que ce n'est pas une certitude.
- **Résultat observé :** moyenne glissante 70 %, dernière valeur 74 %, risque 70,
  confiance `MEDIUM`, seuil 85 % et date de franchissement estimée.
- **Capture à réaliser :** `11-predictive-trend.png`.
- **Phrase à expliquer au jury :** « Il s'agit d'une extrapolation explicable fondée
  sur l'historique, pas d'une promesse ; le niveau de confiance reste visible. »

## Scénario 12 — Génération et cycle de vie d'une alerte

- **Préconditions :** page `/alerts` avec cinq alertes `NEW`.
- **Action :** montrer CPU, RAM, disque, offline et ML ; acquitter une alerte non
  critique prévue pour la démonstration, puis la passer en cours ou la résoudre.
- **Données générées :** trois alertes de seuil, une alerte offline et une alerte ML.
- **Comportement attendu :** déduplication, sévérité, source, occurrence, statut et
  audit de chaque transition.
- **Résultat observé avant manipulation jury :** 5 alertes : 2 CRITICAL et 3 HIGH,
  toutes `NEW`, occurrence 1.
- **Capture à réaliser :** `12-alert-lifecycle-before.png` puis
  `12-alert-lifecycle-after.png`.
- **Phrase à expliquer au jury :** « Une alerte est un objet durable avec un cycle de
  vie ; elle n'est pas une simple notification éphémère. »

## Scénario 13 — Recommandation contextualisée

- **Préconditions :** au moins une alerte CPU, RAM ou disque ouverte.
- **Action :** ouvrir la machine concernée et montrer « Alertes et recommandations ».
- **Données générées :** recommandation structurée créée en même temps que chaque alerte.
- **Comportement attendu :** indices de diagnostic, actions proposées, justification
  et champ `destructive=false`.
- **Résultat observé :** 5 alertes sur 5 possèdent une recommandation structurée non
  destructive.
- **Capture à réaliser :** `13-recommendation.png`, idéalement pour l'alerte CPU.
- **Phrase à expliquer au jury :** « Le système explique quoi vérifier et pourquoi ;
  il laisse les actions risquées sous contrôle de l'administrateur. »

## Scénario 14 — Permissions multi-utilisateur

- **Préconditions :** comptes ADMIN, SUPERVISOR, TECHNICIAN, CLIENT et VIEWER créés.
- **Action :** se connecter comme ADMIN et afficher `/users`, puis comme VIEWER et
  tenter `/users` ou la création d'un environnement. En option, montrer qu'un
  SUPERVISOR peut gérer une règle sans gérer les customers.
- **Données générées :** cinq utilisateurs rattachés au même tenant, un par rôle.
- **Comportement attendu :** lecture des ressources tenant pour les rôles actifs ;
  écriture réservée à ADMIN/SUPERVISOR ; utilisateurs/customers réservés à ADMIN.
- **Résultat observé par API :** ADMIN sur `/api/users/` → 200 ; VIEWER sur
  `/api/users/` → 403 ; tentative d'écriture VIEWER → 403 et aucun objet créé.
- **Capture à réaliser :** `14-rbac-admin.png` puis `14-rbac-viewer-403.png`.
- **Phrase à expliquer au jury :** « Le frontend affiche le résultat, mais la vraie
  sécurité est appliquée côté API ; modifier l'interface ne permet pas de contourner
  le RBAC. »

## Scénario 15 — Isolation multi-client

- **Préconditions :** tenant principal préparé et tenant `pfe-demo-isolated` présent.
- **Action :** noter l'ID de `[DEMO] CLIENT-B-SECRET`, puis essayer son URL avec le
  compte du tenant principal ; répéter dans l'autre sens avec le viewer isolé.
- **Données générées :** 11 machines dans le tenant principal et 1 machine secrète
  dans le tenant secondaire.
- **Comportement attendu :** listes filtrées par customer et détails étrangers rendus
  invisibles par une réponse 404, pas par une simple interdiction d'interface.
- **Résultat observé :** principal → 11 machines et détail isolé → 404 ; tenant isolé
  → 1 machine et détail principal → 404.
- **Capture à réaliser :** `15-tenant-a.png`, `15-tenant-b.png` et
  `15-cross-tenant-404.png` sans exposer de jeton.
- **Phrase à expliquer au jury :** « L'isolation est effectuée dans les querysets
  serveur ; un identifiant valide d'un autre client reste introuvable. »

## Scénario 16 — Notification email

- **Préconditions :** `EMAIL_BACKEND` console, préférence email CRITICAL active et
  alerte CPU CRITICAL disponible.
- **Action :** montrer la sortie email console, puis la livraison via
  `/api/notifications/deliveries/` ou la configuration.
- **Données générées :** événement `pfe.demo.notification`, destination
  `jury-demo@demo.invalid`, une livraison liée à l'alerte CPU.
- **Comportement attendu :** création durable, traitement hors requête principale,
  statut `SENT`, sans contact avec un serveur SMTP externe.
- **Résultat observé :** le préparateur a appelé l'adaptateur console hors cycle HTTP,
  l'email complet a été écrit dans le terminal et la livraison est `SENT`. Le chemin
  Celery périodique reste couvert par les tests de notifications, pas par cette
  exécution synchrone déterministe.
- **Capture à réaliser :** `16-notification-console.png` et
  `16-notification-delivery-sent.png`.
- **Phrase à expliquer au jury :** « L'email est le premier adaptateur réellement
  implémenté ; la démonstration utilise le backend console pour prouver le flux sans
  envoyer de message à un tiers. »

## Checklist de démonstration

### La veille

- [ ] Repartir d'un commit identifié et conserver les changements locaux utiles.
- [ ] Vérifier l'espace disque PostgreSQL et le répertoire des modèles ML.
- [ ] Exécuter les tests backend ciblés, le lint et le build frontend.
- [ ] Vérifier `docker compose ps` pour PostgreSQL et Redis.
- [ ] Préparer le tenant avec `prepare_pfe_demo --reset`.
- [ ] Exécuter `prepare_pfe_demo --verify-only` et conserver sa sortie.
- [ ] Tester les six comptes de rôle sans enregistrer le mot de passe dans le navigateur.
- [ ] Vérifier que l'email backend est `console`, jamais SMTP réel.
- [ ] Ouvrir chaque page et confirmer l'absence d'erreur réseau.
- [ ] Réaliser les captures de secours listées dans ce document.
- [ ] Préparer une vidéo locale courte en dernier recours, sans la présenter comme
  une exécution en direct.

### Quinze minutes avant

- [ ] Démarrer DB, Redis, backend, worker, Beat et frontend.
- [ ] Vérifier `/api/health/`, `/api/docs/` et `/dashboard`.
- [ ] Vérifier 11 assets, 10 online, 1 offline, 5 alertes et 1 anomalie.
- [ ] Vérifier les pages VMware et Hyper-V et le libellé `NON CONNECTÉ`.
- [ ] Fermer les onglets, terminaux et notifications sans rapport avec le PFE.
- [ ] Désactiver les notifications personnelles et le partage de mots de passe.
- [ ] Garder un terminal ouvert sur les logs backend/Celery, sans secrets.
- [ ] Régler le zoom navigateur et la résolution de projection.

### Pendant

- [ ] Annoncer immédiatement que le jeu est synthétique.
- [ ] Ne jamais cliquer « Collecter » sur les connecteurs `.invalid`.
- [ ] Ne jamais afficher `.env`, jetons, secrets, cookies ou mots de passe.
- [ ] Montrer le résultat avant le détail technique.
- [ ] Respecter l'ordre recommandé et garder deux minutes pour les questions.
- [ ] Pour une action mutable, utiliser uniquement un objet `[PFE DEMO]`.
- [ ] Après chaque action, confirmer le changement visible ou annoncer l'échec.
- [ ] Ne jamais qualifier VMware/Hyper-V de collecte réelle dans ce scénario.

### Après

- [ ] Se déconnecter des comptes PFE.
- [ ] Supprimer la variable `PFE_DEMO_PASSWORD` du processus PowerShell.
- [ ] Arrêter les services uniquement si la plateforme n'est plus utilisée.
- [ ] Conserver les AuditLogs : ils sont immuables par conception.
- [ ] Si nécessaire, relancer ultérieurement `--reset` pour remplacer uniquement les
  objets PFE25. Le reset ne supprime pas les AuditLogs historiques.

## Plan de secours

- **Frontend indisponible :** montrer les mêmes objets dans `/api/docs/` et exécuter
  les GET via Swagger ; ne pas inventer un résultat visuel.
- **WebSocket indisponible :** annoncer le fallback polling et recharger la page.
- **Worker Celery indisponible :** montrer la livraison durable `PENDING`, redémarrer
  le worker, puis confirmer son traitement.
- **Modèle absent :** ne pas cliquer plusieurs fois sur « Entraîner » ; relancer le
  préparateur et vérifier que le modèle est marqué synthétique.
- **VMware/Hyper-V externe absent :** rester sur les assets synthétiques étiquetés et
  expliquer l'architecture réelle à partir de `docs/VMWARE.md` et `docs/HYPERV.md`.
- **Échec non compris :** montrer le journal, annoncer honnêtement la limite et passer
  au scénario suivant plutôt que de masquer l'erreur.
