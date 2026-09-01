# Rapport UI/UX du frontend

## 1. Positionnement

L'interface adopte un langage visuel de centre d'opérations : fond sombre, contrastes froids, accent turquoise, densité maîtrisée et priorisation des incidents. Elle est conçue pour une lecture quotidienne sur desktop tout en restant exploitable sur tablette et mobile.

Ce rapport décrit l'implémentation courante. Il ne constitue pas un résultat de test visuel ; les validations exécutées et leurs résultats appartiennent à `docs/FRONTEND_TEST_REPORT.md`.

## 2. Système visuel

Les tokens sont centralisés dans `src/styles/tokens.css`.

| Famille | Valeurs principales | Usage |
|---|---|---|
| Fond | `#061015`, `#09191f` | Canvas et surfaces élevées. |
| Surfaces | `#0b2027`, `#0f2931`, `#13333c` | Cartes, panneaux, interactions. |
| Accent | `#32dec2`, `#19c5ac` | Action primaire, sélection, état live. |
| Texte | `#eef8f7`, `#b8d0d2`, `#84a5aa` | Primaire, secondaire, atténué. |
| Sémantique | bleu, violet, orange, rouge, vert, cyan | Source, ML, warning, criticité, succès. |
| Rayons | 8, 12, 18 px | Contrôles, cartes, panneaux. |
| Espacement | échelle 4 à 40 px | Rythme cohérent. |
| Animation | `160ms ease` | Feedback discret. |

La typographie repose sur la pile système définie dans `base.css`, ce qui évite une dépendance nécessaire au rendu. Les identifiants techniques utilisent un style monospace distinct.

## 3. Structure de navigation

### Desktop

- sidebar persistante avec marque, domaines et rôle courant ;
- topbar avec recherche de pages, état temps réel, événements récents et profil ;
- contenu structuré par eyebrow, titre, description, actions et éventuel fil d'Ariane ;
- item actif déterminé par le routeur, y compris sur les vues détail.

### Écrans étroits

- sous 1 100 px, la sidebar devient un drawer avec scrim ;
- le drawer mobile bloque le scroll de fond, place et piège le focus, se ferme par `Escape` et restitue le focus au bouton d'ouverture ;
- sous 760 px, la recherche globale et le bloc profil sont masqués, les grilles passent en une ou deux colonnes ;
- sous 420 px, l'état temps réel est condensé et les actions de page prennent la largeur disponible.

La recherche globale est volontairement une recherche de navigation, pas une recherche métier. Elle ne promet donc pas de résultat machine ou alerte qu'elle ne demande pas à l'API.

## 4. Hiérarchie de l'information

Chaque page suit un schéma cohérent :

1. contexte et objectif dans `PageHeader` ;
2. indicateurs synthétiques lorsque pertinents ;
3. filtres avec portée explicitée ;
4. contenu principal en cartes ou tableaux ;
5. détail secondaire dans drawer, modal ou route dédiée ;
6. limites et états partiels au plus près des données concernées.

Les criticités ne reposent pas uniquement sur la couleur : badges, libellés et points d'état accompagnent les tons. Les nombres d'infrastructure utilisent le format français, des grandes unités et au maximum une décimale.

## 5. Composants partagés

| Composant | Comportement UX |
|---|---|
| `Button` / `IconButton` | Variantes primaire, secondaire, ghost et danger ; état loading ; label accessible pour une icône seule. |
| `Badge` et badges métier | État, sévérité et source avec texte explicite. |
| `Card`, `CardHeader`, `StatCard` | Conteneur et hiérarchie uniforme. |
| `Field`, `Input`, `Select`, `Textarea`, `Checkbox` | Libellé visible, aide et erreur associée. |
| `DataTable` | Tri local explicite, lignes clavier, table transformée en fiches mobiles. |
| `Pagination` | Navigation précédente/suivante et position courante. |
| `Tabs` | Segmentation des dossiers machine, ML et configuration. |
| `Modal`, `Drawer`, `ConfirmDialog` | Focus capturé et restitué, fermeture par clic extérieur ou `Escape`, confirmation des opérations sensibles. |
| `Toast` | Succès, warning et erreur après mutation. |
| `Tooltip` | Contexte additionnel sans remplacer un label. |
| `MetricChart` | Axe avec unité harmonisée, légende, tooltip métier et valeurs lisibles. |

## 6. États de données

L'interface distingue explicitement :

- chargement : skeletons ou `LoadingState` ;
- vide : `EmptyState`, sans exemples fictifs ;
- erreur : `ErrorState` et bouton de réessai ;
- offline : maintien des dernières données disponibles et attente de reconnexion ;
- partiel : warning non bloquant lorsqu'une requête secondaire échoue ;
- interdit : route `/forbidden` ;
- session expirée : retour login avec explication ;
- action asynchrone : confirmation « mise en file » avec identifiant Celery ;
- temps réel indisponible : statut « Mode résilient » plutôt qu'un faux état live.

Le dashboard peut rester utile si une sous-requête échoue. Les vues critiques de détail affichent une erreur localisée et un réessai plutôt qu'une page blanche.

## 7. Parcours principaux

### Exploitation machine

`Machines → dossier machine → overview / métriques / historique / alertes / anomalies / prédictions`.

Le dossier rassemble l'information au lieu de multiplier les écrans. Les recommandations restent liées à l'incident qui les explique. Les graphiques conservent les dimensions de disque, interface, service, datastore ou ressource virtuelle.

### Traitement d'incident

`Dashboard ou Alertes → alerte → contexte → recommandation → changement de statut`.

Le cycle `NEW → ACKNOWLEDGED → IN_PROGRESS → RESOLVED` est présenté comme une action utilisateur. Le nombre d'occurrences montre la déduplication backend.

### Enrôlement agent

`Agents → choisir un environnement → générer un code limité → copier une fois → fermer et effacer`.

L'interface avertit de ne pas placer le secret dans un log, une ligne de commande ou un ticket. Elle ne prétend pas permettre une rotation distincte : la révocation utilise l'état `enabled` réel.

### Administration

`Configuration → règles / notifications / environnements / intégrations`.

Les changements utilisent des modales ciblées et des confirmations. Le mot de passe d'un connecteur n'est jamais demandé ni réaffiché ; seule une référence de secret serveur est saisie.

### Rapports

`Rapports → générer une synthèse → suivre la mise en file → consulter le résultat persistant`.

La page distingue tâche Celery acceptée, rapport en cours, succès et échec. Un chemin d'artefact serveur n'est jamais transformé en téléchargement tant qu'aucun endpoint authentifié n'existe.

### Machine Learning

La page distingue modèle actif, historique, anomalies, évaluation et tâches. Elle affiche les paramètres et documents JSON réels. Lorsque précision/rappel sont absents, l'interface indique qu'ils ne sont pas calculables sans labels au lieu de produire un score décoratif.

## 8. Responsive

Breakpoints implémentés :

| Largeur | Adaptation |
|---|---|
| `≤ 1380 px` | Sidebar réduite, grilles compactes, filtres réorganisés. |
| `≤ 1100 px` | Sidebar hors canvas, menu mobile, cartes principales en colonne. |
| `≤ 760 px` | Topbar compacte, tables en fiches, formulaires/graphiques/grilles en colonne. |
| `≤ 420 px` | Actions pleine largeur, toasts ajustés, statut live abrégé. |

Les tableaux utilisent `data-label` pour conserver le nom de chaque colonne après leur transformation en fiches. Les overlays et actions s'adaptent à la largeur disponible.

## 9. Accessibilité présente

- lien « Aller au contenu » ;
- landmarks `main`, `nav`, `aside`, `header` ;
- navigation et pagination nommées ;
- boutons iconiques pourvus d'un nom accessible ;
- champs associés à un libellé ;
- messages d'authentification en `role=alert` ;
- lignes interactives activables avec `Entrée` et `Espace` ;
- dialogues avec `aria-modal` et titre associé ;
- focus capturé dans les overlays et la navigation mobile, puis restitué au déclencheur ;
- onglets reliés à leur panneau et navigables au clavier ;
- graphiques dotés d'un nom et d'une description textuelle des valeurs et seuils ;
- contenus purement décoratifs masqués avec `aria-hidden` ;
- intitulés textuels en plus des codes couleur ;
- classe `sr-only` pour captions et libellés contextuels.

Points restant à valider ou améliorer :

- parcours complet clavier sur chaque page ;
- contraste mesuré de chaque combinaison et état hover/focus ;
- annonce live des toasts et changements WebSocket selon le comportement final du composant ;
- respect explicite de `prefers-reduced-motion` si des animations supplémentaires sont ajoutées.

## 10. Lisibilité des métriques

`src/utils/format.ts` et `src/utils/metrics.ts` évitent les grands nombres bruts :

- octets : Ko, Mo, Go, To, Po ;
- débit octets : Ko/s à To/s ;
- débit bits : Kb/s à Gb/s ;
- latence : ms puis secondes ;
- disponibilité : secondes, minutes, heures ou jours ;
- fréquence : MHz ou GHz ;
- maximum une décimale ;
- format français et symbole d'unité explicite.

Les graphiques choisissent une unité commune par groupe selon la valeur maximale, puis affichent dans le tooltip la valeur métier originale correctement formatée. Les séries d'unités incompatibles ne partagent pas le même axe.

## 11. Honnêteté fonctionnelle

L'UX contient plusieurs garde-fous contre une démonstration trompeuse :

- aucun placeholder présenté comme donnée réelle ;
- état vide dédié pour un tenant sans télémétrie ;
- mention « page chargée » pour les calculs locaux ;
- tendances qualifiées d'estimations ;
- tâches qualifiées de mises en file ;
- VMware/Hyper-V partiels ou non configurés affichés comme tels ;
- Teams, Slack et Telegram explicitement non implémentés ;
- évaluation ML sans métrique inventée ;
- détails techniques accessibles lorsque nécessaires au diagnostic.

## 12. Limites UX connues

1. La pagination serveur de 100 éléments et l'absence de nombreux filtres backend limitent la portée des recherches locales.
2. L'historique machine n'offre pas encore de sélecteur temporel réel.
3. La page prédictive mappe la pagination DRF fixe de 100 sur des lots UI de 20, mais effectue toujours une requête de tendance par machine du lot.
4. La recherche globale ne recherche que les pages.
5. Il n'existe pas de flux mot de passe oublié, OTP ou MFA à exposer.
6. Les rôles `TECHNICIAN`, `CLIENT` et `VIEWER` ont aujourd'hui la même capacité API de lecture.
7. La validation visuelle multi-viewport est consignée dans `docs/FRONTEND_TEST_REPORT.md` ; une mesure automatisée exhaustive du contraste reste à réaliser.
