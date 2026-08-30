# Rapport d'amélioration UI/UX

## Résumé

Le frontend conserve l'identité sombre teal/cyan d'InfraSentinel-AI et les
contrats métier existants. Les travaux concernent la lisibilité, la cohérence
des métriques, l'accessibilité et les états opérationnels. Aucune donnée de
démonstration n'a été ajoutée et aucune valeur stockée n'a été convertie.

## Pages améliorées

- Connexion/inscription : erreurs HTTP différenciées, soumission et autocomplete.
- Vue globale : suppression du graphique multi-unité, flux de mesures lisibles,
  état temps réel dynamique et compteurs toujours issus de l'API.
- Machines : recherche, OS, agent, temps relatif et navigation clavier.
- Détail machine : valeurs actuelles, metadata RAM/GPU, graphiques homogènes,
  tendances avec unités, alertes et anomalies contextualisées.
- Agents : code d'enrôlement à usage unique, téléchargement conditionnel,
  révocation et feedback, sans exposition du token agent.
- Alertes : valeur, seuil, source, date, recommandation et cycle complet.
- Anomalies : relation score/seuil, features explicables et acquittement.
- VMware/Hyper-V : états vides, collecte suivie, metadata structurée, unités et
  graphiques communs, sans inventaire factice.
- ML : statut distinct de la sévérité, dataset synthétique clairement signalé,
  noms de modèles lisibles et stables, identifiant technique réservé aux
  informations scientifiques progressives.
- Utilisateurs/configuration/audit : rôles et actions localisés, unités de
  seuil, durées lisibles et mutations sans rechargement global.

## Système central d'unités

`frontend/src/metricFormatting.js` fournit :

- `formatBytes`, `formatMemory`, `formatStorage` ;
- `formatByteRate`, `formatBitRate`, `formatRate` ;
- `formatPercent`, `formatLatency`, `formatDuration` ;
- `formatTemperature`, `formatFrequency`, `formatCount` ;
- `formatTimestamp`, `formatRelativeTime` ;
- formatage sémantique des métriques, dimensions et états ;
- regroupement des séries par unité compatible ;
- interprétation prudente des tendances et scores ML.

`null`, `undefined` et chaîne vide restent absents (`—`) au lieu de devenir
zéro. L'interface normale utilise au maximum une décimale. Les scores
scientifiques conservent davantage de précision uniquement dans les détails.

## Composants partagés

- `Page`, `DataState`, `LoadingState`, `EmptyState`, `ErrorState` ;
- `MetricCard`, `MetricValue`, `Timestamp` ;
- `Status`, `Severity`, `ActionFeedback` ;
- `Table` avec en-têtes, région nommée et activation clavier.

## Graphiques

- Les axes Y ne mélangent plus des grandeurs incompatibles.
- Les pourcentages utilisent le domaine 0–100 du contrat producteur.
- Capacité et débit choisissent dynamiquement une unité lisible.
- Tooltips : libellé métier, dimension, valeur et unité.
- Les séries d'état utilisent des libellés opérationnels.

## Temps réel et performance

- Événements WebSocket regroupés sur une fenêtre de 500 ms.
- Invalidation par famille d'événements au lieu d'un rechargement systématique
  de toutes les requêtes de la page.
- Le polling de secours continue de rafraîchir l'ensemble.
- Les mutations ne font plus `window.location.reload()`.
- Les routes restent chargées paresseusement.

## Responsive et accessibilité

- Sidebar mobile avec backdrop, touche Échap et `aria-expanded`.
- Focus visible et activation clavier des lignes.
- Statuts exprimés par texte et couleur.
- Chargements `role=status`, erreurs `role=alert`.
- Tables transformées en cartes sous 620 px.
- Grilles adaptées à 1280, 900, 780, 620 et 460 px.
- Respect de `prefers-reduced-motion`.
- Police système locale, sans dépendance réseau.

## Tests ajoutés

La suite vérifie o/Ko/Mo/Go/To/Po, débits byte/bit, pourcentages,
latence, uptime, température, fréquence, compteurs, zéro, valeurs absentes,
valeurs signées, timestamps, états service/VM, relation score/seuil et exclusion
des métriques nulles des graphiques. Elle vérifie aussi l'invalidation ciblée
des ressources temps réel, le polling de secours et le rendu serveur initial
des 16 routes critiques (l'inscription est redirigée lorsqu'elle est désactivée).

## Validation exécutée

| Contrôle | Commande | Résultat observé |
|---|---|---|
| Tests frontend | `npm test -- --run` | 40 découverts, 40 réussis, 0 échec |
| Lint frontend | `npm run lint` | réussi, 0 avertissement ESLint |
| Build frontend | `npm run build` | réussi, 2 385 modules transformés |
| Audit dépendances | `npm audit --audit-level=moderate` | 0 vulnérabilité |
| Régression Django/PostgreSQL | `python manage.py test -v 1` avec la configuration PostgreSQL locale et le profil OpenAPI de test | 193 exécutés, 0 échec, 6 ignorés car intégrations externes optionnelles |
| Agent Windows | suite Python de l'agent | 25 réussis, 0 échec |
| Redis/Celery réel | `docker compose exec -T -e INFRASENTINEL_RUN_REDIS_INTEGRATION=1 api python manage.py test async_tasks.tests.test_redis_integration -v 2` | 3 réussis, connexion/reconnexion, panne temporaire et round-trip broker validés |
| Image frontend | `docker compose build frontend` | image construite avec le build Vite de production |
| Runtime local | `docker compose ps`, requêtes `/` et `/api/health/` | six services sains, frontend HTTP 200, DB et Redis `ok` |

La suite Django complète et celle de l'agent ont été exécutées après le retour
de Docker/PostgreSQL ; les changements de cette revue sont limités au frontend
et à la documentation.

## Limites restantes

- Aucun framework E2E DOM/axe/régression visuelle n'est installé.
- La liste machines n'affiche pas CPU/RAM/disque car l'API n'offre pas de résumé
  latest-metrics ; aucune requête N+1 n'a été ajoutée.
- Les données que l'API n'expose pas ne sont pas simulées, notamment l'état du
  service Windows dans la ressource Agent.
- La vérification visuelle automatisée dépend de l'accès autorisé au navigateur
  local. Dans cette session, le navigateur intégré a refusé la prise de contrôle
  de l'URL locale pour raison de politique de sécurité. Les contrôles visuels
  manuels 1920×1080, 1366×768 et mobile restent donc **NOT TESTED** ; ils ne sont
  pas présentés comme réussis.

## Verdict strict

| Domaine | Verdict | Justification |
|---|---|---|
| UI/UX REVIEW | PASS | Toutes les routes, composants partagés et contrats de métriques ont été audités et documentés. |
| UNIT FORMATTING | PASS | Système central, données absentes préservées, unités et tests sémantiques réussis. |
| RESPONSIVE DESIGN | PARTIAL | CSS responsive et navigation mobile implémentés ; inspection visuelle multi-viewport non exécutable dans cette session. |
| CHART PRESENTATION | PARTIAL | Séries séparées par unité, axes et tooltips testés ; validation visuelle interactive non exécutable. |
| ACCESSIBILITY | PARTIAL | Focus, clavier, ARIA, texte des statuts et reduced-motion ajoutés ; aucun audit axe/Lighthouse disponible. |
| REGRESSION TESTS | PASS | Frontend, backend PostgreSQL, agent, Redis/Celery, lint, build et runtime Docker réussis. |
