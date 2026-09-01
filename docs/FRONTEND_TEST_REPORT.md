# Rapport de validation du frontend

**Projet :** InfraSentinel AI

**Date :** 1 septembre 2026

**Portée :** frontend React/Vite/TypeScript, intégration HTTP/WebSocket, image Docker et rendu navigateur
**Verdict strict :** **FRONTEND ENTERPRISE PARTIALLY READY** — utilisable pour la démonstration PFE avec données Windows réelles, mais les validations externes et d'accessibilité exhaustive restent à faire.

## 1. Environnement contrôlé

- Windows, PowerShell et Docker Desktop ;
- frontend construit avec Node.js 22 dans l'image Docker ;
- Nginx non privilégié pour la SPA finale ;
- Django/API, PostgreSQL 17, Redis 7.4, Celery worker et Celery Beat dans la stack locale ;
- navigateur Chromium intégré à Codex, sur `http://127.0.0.1:5173` ;
- tenant réel contenant la machine Windows `LEGION` et sa télémétrie ;
- aucune infrastructure VMware, Hyper-V ou SMTP externe disponible pendant cette validation.

## 2. Contrôles automatisés finaux

| Contrôle | Commande | Résultat observé |
|---|---|---|
| Format | `npm run format:check` | PASS, tous les fichiers correspondent au format Prettier. |
| Types | `npm run typecheck` | PASS, aucune erreur TypeScript. |
| Lint | `npm run lint` | PASS, zéro warning autorisé et zéro erreur. |
| Tests | `npm test -- --reporter=dot` | PASS, **17 fichiers / 64 tests**, 0 échec, 0 skip. |
| Build local | `npm run build` | PASS, 2 476 modules transformés en 3,82 s. |
| Audit npm | `npm audit --audit-level=low` | PASS, 0 vulnérabilité connue. |
| Build Docker | `docker compose build frontend` | PASS, build Vite dans Node 22 puis copie dans Nginx. |
| Démarrage | `docker compose up -d frontend` | PASS. |
| Santé stack | `docker compose ps` | frontend, API, PostgreSQL, Redis, worker et Beat `healthy`. |
| Santé API | `Invoke-WebRequest http://127.0.0.1:5173/api/health/` | HTTP 200 ; base et Redis `ok`. |
| CSP | `Invoke-WebRequest http://127.0.0.1:5173/` | `connect-src 'self'` confirmé. |

Le build final produit notamment :

- bundle principal : 347,71 kB, 113,79 kB gzip ;
- dossier machine : 337,06 kB, 102,37 kB gzip ;
- page Rapports : 10,32 kB, 4,09 kB gzip ;
- page Configuration : 18,28 kB, 5,05 kB gzip.

Les pages métier sont chargées à la demande. Aucune sourcemap n'est générée par défaut.

## 3. Couverture des tests frontend

Les 64 tests couvrent notamment :

- résolution de l'URL API, Bearer JWT en mémoire et client HTTP ;
- bootstrap, login, refresh sérialisé, expiration et purge de session ;
- gardes de route, capacités RBAC et interdiction ;
- parsing/formatage des unités avec au plus une décimale ;
- dashboard, machines, alertes et modèle ML ;
- dates inclusives du journal d'audit ;
- payloads Configuration non destructifs (`metadata`, `config`, `secret_ref`) ;
- pagination prédictive : mapping des lots UI de 20 vers les pages DRF fixes de 100 ;
- Rapports : liste réelle, génération asynchrone honnête et absence de faux téléchargement ;
- déconnexion disponible dans le drawer mobile ;
- WebSocket : replay, déduplication, reconnexion, fallback et invalidation du cache.

Il n'existe pas encore de suite E2E Playwright committée. Les contrôles navigateur ci-dessous sont donc des observations manuelles réelles, distinctes de Vitest.

## 4. Validation navigateur réelle

### 4.1 Routes et responsive

Les routes suivantes ont été chargées avec une session administrateur réelle :

`/dashboard`, `/machines`, `/machines/:id`, `/agents`, `/alerts`, `/anomalies`, `/predictions`, `/ml`, `/vmware`, `/hyperv`, `/users`, `/audit`, `/reports`, `/settings?tab=integrations`, `/forbidden` et une route 404.

| Viewport | Couverture observée | Résultat |
|---|---|---|
| 1366 × 768 | Toutes les routes ci-dessus | Aucun crash et aucun débordement horizontal du document. |
| 390 × 844 | Toutes les routes ci-dessus | Aucun crash et aucun débordement horizontal du document ; tables contenues localement. |
| 1920 × 1080 | Dashboard, navigation compacte, machines jusqu'à Hyper-V et page Rapports | Aucun débordement ; hiérarchie et densité conformes. Les dernières routes n'ont pas été répétées après le throttle d'authentification. |

La répétition artificielle de rechargements complets a finalement déclenché le throttle du refresh (`429`) et la session a été redirigée vers `/login`. Les routes visitées après ce `429` ne sont pas comptées comme validation authentifiée. Une navigation SPA normale ne recharge pas le bootstrap d'authentification à chaque route.

Après le dernier redéploiement, un import dynamique a échoué une fois pendant la fenêtre de recréation du conteneur. L'asset répondait ensuite HTTP 200 et un rechargement a rendu `/login` normalement. Ce message transitoire n'est pas masqué dans ce rapport.

### 4.2 Interactions vérifiées

- sidebar desktop réduite et redéployée sans débordement ;
- drawer mobile : scroll du fond bloqué, focus placé sur Fermer, focus restitué sur Ouvrir ;
- centre de notifications mobile : `aria-expanded` cohérent et aucun débordement ;
- drawer Anomalie : ouverture, fermeture par `Escape` et restitution du focus ;
- onglets machine et détails d'une machine réelle ;
- états vides VMware, Hyper-V et Rapports sans donnée inventée ;
- route interdite et route introuvable ;
- redirection vers login après expiration/throttle de la session.

### 4.3 Données réelles observées

La session a affiché la machine Windows `LEGION`, en ligne, avec IP `192.168.1.3`, agent `2.0.0`, heartbeat récent et métriques CPU, mémoire, disque, réseau, GPU et température. Les valeurs étaient formatées en `%`, `Ko/s`, `°C` et unités temporelles lisibles, au plus une décimale.

Le dashboard a affiché 1 machine, 1 en ligne et 38 anomalies ML. La page ML a exposé un modèle Isolation Forest versionné avec contamination 2 %, 200 estimateurs, 7 features et un dataset indiqué non synthétique. Ces observations prouvent uniquement ce que le backend a renvoyé ; elles ne remplacent pas une certification indépendante de la provenance amont.

VMware et Hyper-V ont correctement affiché l'absence de connecteur/asset réel. Aucun host ni VM fictif n'a été ajouté.

## 5. Temps réel et sécurité frontend

- l'UI a affiché `Temps réel actif` ;
- les logs Nginx ont montré `POST /api/realtime/ticket/` en 200 puis le handshake `/ws/events/` en 101 ;
- la CSP finale same-origin autorise ce flux sans joker `ws:`/`wss:` ;
- access JWT uniquement en mémoire ; refresh géré par cookie HttpOnly ;
- aucune clé, token, mot de passe ou référence privée détectée dans le diff frontend ;
- aucun `console.log`, `debugger`, TODO/FIXME critique ou données fake/demo dans le code de production ;
- le cache Query et la séquence temps réel sont purgés à la disparition de l'identité ;
- les restrictions RBAC côté UI ne sont jamais présentées comme remplaçant les permissions Django.

## 6. Matrice QA finale

| Domaine | État | Preuve / réserve |
|---|---|---|
| FRONTEND ARCHITECTURE | PASS | React/TS par domaines, routes lazy, client API, Query cache, design system. |
| AUTH | PARTIAL | Flux, refresh, expiration et gardes testés ; pas de nouveau login/logout manuel avec mot de passe sur l'image finale. |
| RBAC | PARTIAL | Matrice et routes testées ; un seul rôle administrateur parcouru dans le navigateur réel. |
| MULTI-TENANT | PARTIAL | Cache tenant-aware et autorité backend respectés ; pas de parcours manuel Client A/Client B dans cette validation frontend. |
| DASHBOARD | PASS | Données Windows réelles, états live et responsive observés. |
| MACHINES | PASS | Liste et état réel observés. |
| MACHINE DETAILS | PASS | Identité, métriques, historique, alertes, anomalies et prédictions observés. |
| AGENTS | PASS | Parc agent réel et états UI vérifiés ; mutations couvertes par le contrat. |
| ALERTS | PASS | Liste, détail, cycle de vie et recommandations implémentés ; tests de page au vert. |
| ANOMALIES | PASS | Liste/drawer/score/explication et interaction clavier observés. |
| PREDICTIVE RISKS | PASS | Lots de 20 sans saut d'assets testés ; tendances explicitement qualifiées d'estimations. |
| ML | PASS | Modèle, dataset, paramètres, évaluations et tâches réels présentés sans métrique inventée. |
| VMWARE | PARTIAL | UI/contrat/états vides réels validés ; infrastructure VMware externe NOT TESTED. |
| HYPER-V | PARTIAL | UI/contrat/états vides réels validés ; host Hyper-V externe NOT TESTED. |
| AUDIT | PASS | Lecture seule, filtres, pagination et bornes de dates testés. |
| SETTINGS | PASS | Règles, notifications, environnements et connecteurs ; payloads non destructifs testés. |
| REPORTS | PASS | Liste et génération réelles, polling borné, absence d'attribution task/report inventée. |
| WEBSOCKET | PASS | Ticket 200, handshake 101 et UI live observés. |
| REALTIME UI | PASS | Live, attente, polling/offline et événements récents pris en charge. |
| RECONNECTION | PASS | Backoff, replay, déduplication et fallback couverts par tests unitaires/intégration. |
| CHARTS | PASS | Séries groupées par unité/dimension et descriptions accessibles. |
| UNITS | PASS | Grandes unités, locale française et une décimale maximum. |
| TOOLTIPS | PASS | Tooltips métier et statut live vérifiés sans débordement mobile. |
| EMPTY / LOADING / ERROR | PASS | Primitives communes, retries et états réels vérifiés. |
| RESPONSIVE | PARTIAL | Toutes les routes en 1366/mobile et vues clés en 1920 ; pas d'audit visuel exhaustif à tous les breakpoints intermédiaires après le throttle. |
| ACCESSIBILITY | PARTIAL | Clavier, focus, ARIA, tableaux et graphiques améliorés ; pas de lecteur d'écran complet ni mesure exhaustive de contraste. |
| PERFORMANCE | PARTIAL | Lazy loading, cache et tailles de bundles mesurés ; pas de Lighthouse ni profilage grand parc. |
| REAL-ONLY | PASS | Aucun dataset ou asset frontend de démonstration présenté comme réel. |
| EMAIL NOTIFICATION | NOT TESTED | Adaptateur backend présent, mais aucune livraison SMTP externe configurée pour ce contrôle. |
| TESTS | PASS | 17 fichiers, 64 réussis, 0 échec, 0 skip. |
| LINT | PASS | ESLint sans warning. |
| BUILD | PASS | Build local et build Docker réussis. |

## 7. Limites et risques restant connus

1. Plusieurs recherches et statistiques portent seulement sur la page backend chargée, faute de filtres/agrégats serveur.
2. L'historique métrique est limité aux 100 points disponibles et ne propose ni plage réelle ni downsampling.
3. La page prédictive effectue jusqu'à 20 appels de tendances par lot ; un endpoint agrégé serait préférable à grande échelle.
4. Le backend ne relie pas le `task_id` Celery au rapport persistant. L'UI ne prétend donc plus identifier automatiquement le rapport de cette tâche et arrête son polling après deux minutes.
5. Pour un superutilisateur, l'API peut agréger des rapports multi-clients sans exposer le client dans `ReportSerializer`. L'UI affiche cette ambiguïté et ne déduit aucune attribution.
6. Une URL WebSocket externe exige une CSP Nginx explicitement adaptée ; la configuration livrée privilégie la même origine.
7. La sémantique et le contraste doivent encore être validés avec lecteur d'écran et outillage spécialisé.
8. VMware, Hyper-V et SMTP nécessitent leurs infrastructures externes pour une validation de bout en bout.

## 8. Conclusion

Le frontend est **prêt pour une démonstration PFE centrée sur la machine Windows réelle, les métriques, anomalies, alertes, ML, prédictions, rapports et temps réel**. Il n'est pas qualifié « enterprise ready » sans réserves : les intégrations VMware/Hyper-V et Email ne sont pas validées sur infrastructures externes, la preuve multi-rôle/multi-tenant navigateur reste partielle, et l'accessibilité/performance ne disposent pas encore d'un audit spécialisé exhaustif.

Verdict final frontend : **FRONTEND ENTERPRISE PARTIALLY READY**.
