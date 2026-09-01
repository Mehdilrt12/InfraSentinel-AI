# Frontend InfraSentinel AI

Interface d'exploitation React/Vite d'InfraSentinel AI. Elle affiche uniquement les ressources renvoyées par l'API centrale : parc Windows, alertes, anomalies, tendances, modèles ML, inventaires VMware/Hyper-V, règles, notifications, utilisateurs, audit et rapports. Aucune donnée de démonstration n'est injectée par le frontend.

## Pile technique

- React 19 et TypeScript 5 ;
- Vite 6 pour le développement et le build ;
- React Router 7 pour le routage ;
- TanStack Query 5 pour le cache serveur ;
- Axios pour HTTP ;
- Recharts pour les séries temporelles ;
- Lucide React pour les icônes ;
- Vitest, Testing Library et jsdom pour les tests ;
- ESLint 9 pour l'analyse statique.

Les versions exactes sont celles de `package.json` et `package-lock.json`. L'image de build Docker utilise Node.js 22.

## Démarrage local

Pré-requis : le backend doit être joignable et autoriser l'origine Vite dans CORS/CSRF.

```powershell
cd frontend
npm ci
Copy-Item .env.example .env
npm run dev
```

L'interface est alors servie par Vite, par défaut sur `http://127.0.0.1:5173`. Le fichier `.env` local ne doit pas être commité s'il contient une adresse propre au poste ou au LAN.

### Variables de build

| Variable                           | Valeur par défaut    | Usage réel                                                              |
| ---------------------------------- | -------------------- | ----------------------------------------------------------------------- |
| `VITE_API_BASE_URL`                | `/api`               | URL de base HTTP prioritaire.                                           |
| `VITE_API_URL`                     | `/api`               | Alias conservé pour Docker et la compatibilité de configuration.        |
| `VITE_WS_URL`                      | dérivée de l'origine | URL WebSocket explicite ; l'image Nginx fournie impose la même origine. |
| `VITE_PUBLIC_REGISTRATION_ENABLED` | `false`              | Affiche la création d'espace client. Le backend doit aussi l'autoriser. |
| `VITE_POLL_INTERVAL_MS`            | `30000`              | Intervalle du fallback ; le code impose au moins 10 secondes.           |
| `VITE_AGENT_INSTALLER_URL`         | vide                 | Affiche le lien de téléchargement de l'agent lorsqu'il est configuré.   |
| `VITE_ENABLE_SOURCEMAPS`           | `false`              | Active les sourcemaps du build lorsqu'elle vaut `true`.                 |

Les variables `VITE_*` sont publiques dans le bundle. Aucun secret, mot de passe de connecteur ou jeton d'enrôlement permanent ne doit y être placé.

## Commandes

```powershell
npm run dev          # serveur Vite
npm run typecheck    # vérification TypeScript
npm run lint         # ESLint, aucun warning accepté
npm test             # suite Vitest non interactive
npm run test:watch   # Vitest en mode veille
npm run build        # typecheck puis bundle de production
npm run preview      # aperçu local du bundle
```

Ces commandes décrivent la procédure de validation ; leurs résultats courants sont consignés séparément dans `docs/FRONTEND_TEST_REPORT.md`.

## Démarrage Docker

Depuis la racine du dépôt, le service `frontend` construit le bundle puis le sert avec Nginx non privilégié sur le port interne `8080` :

```powershell
docker compose build frontend
docker compose up -d
docker compose ps
```

Nginx sert la SPA, relaie `/api/` vers Django et `/ws/` vers Channels. Dans cette topologie, garder `VITE_API_URL=/api` évite CORS et les URL propres à un poste.

## Routes effectives

| Route                        | Fonction                                           | Accès interface                 |
| ---------------------------- | -------------------------------------------------- | ------------------------------- |
| `/login`                     | Connexion navigateur sécurisée                     | Public                          |
| `/register`                  | Création initiale client                           | Public seulement si activée     |
| `/dashboard`                 | Synthèse opérationnelle                            | Utilisateur actif               |
| `/machines`, `/machines/:id` | Inventaire et dossier machine                      | Utilisateur actif               |
| `/agents`                    | Agents Windows et enrôlement                       | Lecture tous ; actions managers |
| `/alerts`, `/alerts/:id`     | Incidents, cycle de vie, recommandations           | Lecture tous ; actions managers |
| `/anomalies`                 | Anomalies persistées et acquittement               | Lecture tous ; action managers  |
| `/predictions`               | Tendances par machine                              | Utilisateur actif               |
| `/ml`                        | Registre scientifique et tâches ML                 | Lecture tous ; actions managers |
| `/vmware`, `/vmware/:id`     | Vue VMware réelle                                  | Utilisateur actif               |
| `/hyperv`, `/hyperv/:id`     | Vue Hyper-V réelle                                 | Utilisateur actif               |
| `/users`                     | Comptes du tenant                                  | Administrateur                  |
| `/audit`                     | Journal immuable                                   | Administrateur ou superviseur   |
| `/reports`                   | Rapports tenant et génération asynchrone           | Utilisateur actif               |
| `/settings`                  | Règles, notifications, environnements, connecteurs | Administrateur ou superviseur   |

`TECHNICIAN`, `CLIENT` et `VIEWER` sont en lecture seule avec le contrat backend actuel. Les contrôles visuels ne remplacent jamais les permissions Django.

## Architecture source

```text
src/
├── api/             client HTTP, rotation de session, helpers de ressources
├── app/             composition, routes, ErrorBoundary, QueryClient
├── auth/            session, garde d'authentification, capacités RBAC
├── components/
│   ├── charts/      graphiques métriques normalisés
│   ├── common/      design system et états de données
│   └── layout/      shell NOC, navigation, recherche, notifications
├── pages/           modules fonctionnels chargés à la demande
├── realtime/        ticket WebSocket, replay, reconnexion, polling
├── styles/          tokens, base, composants, layout, pages, responsive
├── test/            configuration et rendu de test partagé
├── types/           contrats TypeScript de l'API
└── utils/           formatage et normalisation des séries
```

Le point d'entrée actif est `src/main.tsx`. Les pages sont chargées avec `React.lazy`, sous `AuthProvider`, `QueryClientProvider`, `ToastProvider` et `ErrorBoundary`.

## Sécurité de session

Le client utilise le flux navigateur du backend :

1. récupération d'un jeton CSRF ;
2. login protégé par `X-CSRFToken` ;
3. access JWT gardé uniquement en mémoire ;
4. refresh dans un cookie HttpOnly géré par le serveur ;
5. une seule tentative de refresh partagée après un `401` ;
6. purge du cache privé et de la séquence temps réel au logout ou à l'expiration.

Le frontend ne lit pas le cookie HttpOnly et ne stocke aucun JWT dans `localStorage` ou `sessionStorage`. Seule la dernière séquence WebSocket, non secrète, est conservée par tenant dans `sessionStorage`.

## Données et limites visibles

- Les listes DRF sont paginées à 100 objets par page, sauf l'audit (50 par défaut).
- Plusieurs filtres d'interface sont locaux à la page chargée car l'API ne fournit pas le filtre équivalent.
- Les graphiques machine utilisent les métriques réelles de la première page ; il n'existe pas encore de plage temporelle configurable côté API.
- Le dashboard calcule les risques sur au plus huit machines de la page chargée.
- La page Risques prédictifs découpe les pages DRF fixes de 100 machines en lots UI de 20 afin de borner le fan-out sans sauter d'assets.
- Les tendances sont obtenues par `/machines/{id}/trends/`, pas par une ressource globale `predictions`.
- Les recommandations sont imbriquées dans les alertes ; il n'existe pas de CRUD de recommandations.
- La génération de rapports déclenche un rafraîchissement borné de `/reports/` après le `202`. Le backend n'expose ni statut Celery adressable par l'ID retourné, ni lien fiable tâche/rapport, ni endpoint authentifié de téléchargement d'artefact.
- L'adaptateur Email est implémenté ; la livraison SMTP réelle dépend de la configuration et n'est pas prouvée par les tests frontend. Teams, Slack et Telegram sont affichés comme non disponibles.
- Les collecteurs VMware et Hyper-V ne sont jamais remplacés par des valeurs fictives. Une installation sans infrastructure retourne des états vides ou partiels.

## Diagnostic rapide

### « Le serveur API est injoignable »

Vérifier d'abord :

```powershell
Invoke-WebRequest http://127.0.0.1:8000/api/health/
docker compose ps
docker compose logs api --tail 100
```

Si Vite utilise une autre machine, remplacer `127.0.0.1` dans le `.env` local par l'adresse LAN du serveur, puis aligner `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS` et `CSRF_TRUSTED_ORIGINS` côté Django.

### Temps réel en « Mode résilient »

Le dashboard reste utilisable par polling. Vérifier le proxy `/ws/`, l'accès à `/api/realtime/ticket/`, Redis/Channels et les règles réseau. Le bouton d'état dans la barre supérieure force une reconnexion.

### Interface vide

Un état vide signifie qu'aucune ressource réelle n'a été renvoyée. Vérifier l'enrôlement de l'agent, son heartbeat, le tenant du compte et les collectes ; le frontend ne fabrique pas de mesures.

Pour les décisions d'architecture et la matrice API détaillée, consulter `docs/FRONTEND_FINAL_ARCHITECTURE.md` et `docs/FRONTEND_API_INTEGRATION.md`.
