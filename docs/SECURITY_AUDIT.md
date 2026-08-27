# Audit de sécurité — InfraSentinel AI

Date de l'audit initial : 24 août 2026; résultats de suite révalidés le 26 août 2026.
Périmètre : backend Django/DRF/Channels/Celery,
dashboard React/Vite, agent Windows, connecteurs VMware et Hyper-V, PostgreSQL,
Redis, Docker, scripts, journaux, dépendances et tests.

## Résultat exécutif

L'audit initial a été réalisé entièrement en lecture seule avant la première
correction. Il n'a trouvé aucun secret suivi par Git et les querysets métier
étaient déjà majoritairement limités par client. Il a cependant confirmé cinq
risques élevés : version Django affectée par quatre avis de sécurité, JWT du
navigateur persistés dans `localStorage`, administration `Customer` trop large
pour un administrateur tenant, jeton agent susceptible d'accompagner une
redirection HTTP, et profil local dangereux s'il était exposé comme production.

Après remédiation : **0 critique, 0 élevé, 3 moyens résiduels et 4 faibles
résiduels**. Les risques résiduels dépendent d'une infrastructure de production
qui n'est pas présente dans ce repository : MFA/anti-bot avancé, limitation au
reverse proxy et contrôle d'egress vers les hyperviseurs.

## Méthode et preuves

- inspection manuelle des modèles, serializers, ViewSets, permissions, tâches,
  consommateurs ASGI, collecteurs, stockage agent, frontend et manifests ;
- recherche des secrets, sinks XSS, exécutions shell, erreurs persistées,
  stockages de tokens et frontières tenant ;
- `python manage.py check --deploy` sur la configuration initiale : 6 alertes
  (`HSTS`, redirection SSL, secret faible, cookies non Secure et `DEBUG=true`) ;
- `pip-audit -r backend/requirements.txt` initial : 4 vulnérabilités connues dans
  Django 6.0.6 (`PYSEC-2026-2090`, `2091`, `2092`, `3717`) ;
- `npm audit --json` initial : 0 vulnérabilité sur 305 dépendances recensées ;
- tests multi-tenant, IDOR, JWT, CSRF, throttling, agent, WebSocket, erreurs,
  connecteurs et en-têtes ajoutés à la suite PostgreSQL ;
- aucune donnée réelle VMware/Hyper-V ni aucun secret n'a été inventé pour les
  validations.

Cet audit est une revue de code et de configuration, pas un test d'intrusion sur
une infrastructure de production. Aucun vCenter, hôte Hyper-V, proxy TLS, WAF ou
secret store externe n'était disponible.

## Constats initiaux et corrections

| ID | Sévérité initiale | Constat vérifié | Correction appliquée |
|---|---|---|---|
| H-01 | Élevée | `Django==6.0.6` était signalé par `pip-audit` pour quatre avis 2026, dont un avis officiel élevé. | Passage à `Django==6.0.8`, réinstallation et nouvel audit de dépendances. |
| H-02 | Élevée | Access et refresh JWT étaient lus/écrits dans `localStorage`; une XSS aurait pu voler les deux secrets persistants. | Flux navigateur dédié : access uniquement en mémoire, refresh rotatif en cookie `HttpOnly`, `Secure` configurable, `SameSite=Strict`, CSRF obligatoire. Les endpoints JWT non navigateur restent disponibles. |
| H-03 | Élevée | Un `ADMIN` tenant pouvait créer un autre `Customer`, modifier `active` et supprimer son propre tenant avec cascades. | Lecture de son client conservée; toute mutation `Customer` exige maintenant un superutilisateur plateforme. Tests de non-élévation ajoutés. |
| H-04 | Élevée | `requests` suivait les redirections et l'en-tête personnalisé `X-Agent-Token` pouvait être propagé vers une autre origine. | `allow_redirects=False`; toute réponse 3xx est refusée et testée. |
| H-05 | Élevée si exposée | L'environnement local actif avait `DEBUG=true`, secret Django faible, HTTP/cookies non Secure et SSL PostgreSQL désactivé; le port API Docker écoutait toutes les interfaces. | Secrets locaux régénérés, port Docker lié à loopback par défaut, profil `.env.production.example` séparé, docs privées hors debug et checklist `check --deploy`. Le profil local HTTP reste volontairement local. |
| M-01 | Moyenne | Clé JWT couplée à `SECRET_KEY`, sans audience ni issuer explicites. | `JWT_SIGNING_KEY` indépendante obligatoire, `aud` et `iss` explicites, durées 15 min/1 jour et rotation/blacklist conservées. |
| M-02 | Moyenne | Throttle public générique; login sans bucket par compte et enrollment à 600/min. | Buckets séparés login IP/compte, inscription, enrollment et requêtes agent; cache Redis partagé et `TRUSTED_PROXY_COUNT=0` par défaut. |
| M-03 | Moyenne | `Customer.active=false` n'empêchait ni login/refresh, ni session existante, ni agent. | Permission tenant active par défaut, règle SimpleJWT active et filtre agent `customer__active=true`. |
| M-04 | Moyenne | Le ticket WebSocket était signé mais réutilisable 60 s; aucune validation d'`Origin`. | Nonce aléatoire hashé en PostgreSQL, consommation atomique unique, expiration, allowlist d'origine, revalidation du compte à chaque événement et durée de connexion bornée. |
| M-05 | Moyenne | Les clés d'idempotence agent étaient facultatives et un heartbeat trop long pouvait provoquer une erreur DB. | Clé obligatoire par métrique agent, rejeu dédupliqué, serializers utilisés réellement et version bornée à 40 caractères. |
| M-06 | Moyenne | Connecteurs : loopback possible, TLS désactivable sans garde, `config` pouvait contenir des secrets. | Rejet loopback/link-local, allowlist facultative mais prévue, TLS non vérifié interdit sauf drapeau serveur, identifiants interdits dans URL et clés secrètes refusées dans `config`. |
| M-07 | Moyenne | `str(exc)` était persisté dans connecteurs, collectes, tâches et notifications puis exposé par API. PowerShell et pyVmomi pouvaient fournir des détails internes. | Messages publics génériques, logs structurés par type d'exception, redaction centralisée des tokens/JWT/tickets/mots de passe. |
| M-08 | Moyenne | Parser et tailles/longueurs n'étaient pas explicitement bornés partout; mots de passe de login arbitrairement longs. | JSON uniquement, limite explicite 2,5 Mio, mots de passe ≤ 128, organization ≤ 160, lots ≤ 5000 et JSON connecteur ≤ 16 Kio/profondeur 8. |
| M-09 | Moyenne | Conteneurs applicatifs exécutés en root, sans suppression de capabilities. | Utilisateur non privilégié, `cap_drop: ALL`, `no-new-privileges`, répertoires d'écriture dédiés. |
| M-10 | Moyenne | Swagger et inscription publique activés par défaut, source maps Vite de production présentes. | Tous désactivés hors debug par défaut; source maps seulement avec opt-in explicite. |
| M-11 | Moyenne | `SECURE_PROXY_SSL_HEADER` faisait confiance à `X-Forwarded-Proto` même sans proxy explicitement configuré. | Confiance conditionnée à `TRUST_X_FORWARDED_PROTO=true`; nombre de proxies explicite. |
| M-12 | Moyenne | Le spool agent stockait en clair des métriques et métadonnées locales. | Nouvelles lignes chiffrées avec Windows DPAPI, compatibilité de lecture des anciennes lignes et test au repos. |
| L-01 | Faible | CSP/Permissions-Policy n'étaient pas servis sur l'API. | CSP restrictive sur JSON, CSP compatible sidecar sur Swagger, Permissions-Policy, Referrer-Policy, COOP, nosniff et anti-frame. |
| L-02 | Faible | Erreur de filtre `customer` superuser invalide susceptible de remonter en 500. | UUID validé et réponse 400 stable. |
| L-03 | Faible | Celery ne déclarait pas explicitement les formats acceptés. | Tâches/résultats JSON uniquement; pickle refusé par configuration. |

## Authentification et sessions

Le navigateur appelle d'abord `GET /api/auth/browser/csrf/`, puis
`POST /api/auth/browser/login/`. Seul l'access JWT est accessible au JavaScript
et il disparaît au rechargement; le frontend utilise le refresh HttpOnly pour
restaurer la session. Refresh et logout exigent `X-CSRFToken`. Le refresh est
tourné et l'ancien JTI placé en blacklist. Logout révoque le refresh courant.

Les clients API non navigateur peuvent continuer à utiliser `/api/auth/token/`,
`/api/auth/refresh/` et `/api/auth/logout/`; ils sont responsables d'un stockage
de secret adapté à leur plateforme. Une rotation de `DJANGO_SECRET_KEY` ou
`JWT_SIGNING_KEY` invalide volontairement les sessions/tickets ou JWT concernés.

L'inscription publique est désactivée hors debug sauf opt-in. Quand elle est
activée, elle reste soumise au throttle mais ne comporte pas encore de
vérification d'adresse email.

## Autorisation, RBAC et multi-tenant

- deny-by-default via `IsActiveTenant`;
- lecture métier limitée au `customer` courant ;
- écritures habituelles réservées à `ADMIN`/`SUPERVISOR` ;
- utilisateurs réservés à `ADMIN` tenant ;
- mutations de la table des tenants réservées au superutilisateur plateforme ;
- relations `environment`, `machine` et `user` revalidées dans le tenant ;
- IDs étrangers invisibles (`404`) pour les querysets métier ;
- agent limité à sa machine, son customer et son environnement enrôlés.

Les UUID ne sont qu'une défense secondaire : l'isolation repose sur les querysets
et validators serveur, et les tests utilisent systématiquement deux tenants.

## Agent Windows

Le code d'enrollment et le token agent sont générés par `secrets`, stockés en
base sous SHA-256 uniquement et jamais sérialisés. Ce hash simple est adapté ici
à des secrets opaques à forte entropie, pas à des mots de passe humains. Le code
d'enrollment est expirant, atomiquement consommé une fois; le token est révocable
avec `enabled=false` et les agents d'un customer désactivé sont refusés.

Le token local est protégé par DPAPI, les payloads du spool le sont aussi sous
Windows, les redirects sont refusés, HTTPS est obligatoire hors localhost
explicitement autorisé, les réponses sont validées et les logs rotatifs passent
par un redactor. Le rejeu d'un lot identique ne crée aucune seconde métrique.

## Infrastructure et secrets

Aucun `.env` peuplé, fichier de clé, base SQLite, spool, artefact ML ou certificat
privé n'est suivi par Git. Les mots de passe PostgreSQL/Redis/SMTP et secrets
connecteurs restent injectés par environnement ou secret store. Le profil de
production exige HTTPS, cookies Secure, PostgreSQL `verify-full`, Redis `rediss`,
HSTS et hôtes/origines explicites.

Le reverse proxy de production doit :

1. terminer TLS et rediriger HTTP avant Daphne ;
2. remplacer, et non concaténer, les en-têtes `Forwarded`/`X-Forwarded-*` ;
3. limiter corps, URL, headers, connexions et débits avant Django ;
4. expurger `ticket` des queries WebSocket dans ses access logs ;
5. injecter une CSP frontend adaptée à l'URL API/WSS réelle ;
6. ne jamais exposer directement PostgreSQL ou Redis.

## Risques résiduels

### Moyens

1. MFA, CAPTCHA adaptatif et verrouillage de compte ne sont pas implémentés. Les
   throttles Django réduisent l'abus mais ne remplacent pas une protection edge.
2. VMware/Hyper-V nécessitent légitimement un accès réseau interne. Une allowlist
   applicative existe, mais la protection définitive contre SSRF/DNS rebinding
   exige un pare-feu egress vers les seuls vCenter/hôtes autorisés.
3. Les limites Daphne/Django ne remplacent pas les limites de connexions, headers,
   body et WebSocket d'un reverse proxy/WAF de production.

### Faibles

1. Le ticket WebSocket à usage unique reste dans la query du handshake; les logs
   du proxy doivent l'expurger. Sa validité est limitée à 60 secondes.
2. Une connexion WebSocket volée reste valide jusqu'au prochain événement ou
   pendant au plus 15 minutes. Le frontend ferme normalement la socket au logout.
3. Les anciennes lignes de spool créées avant ce correctif restent en clair jusqu'à
   leur envoi/suppression; toutes les nouvelles lignes Windows utilisent DPAPI.
4. L'inscription activée volontairement ne vérifie pas encore l'adresse email.

## Validation reproductible

Résultats obtenus le 24 août 2026 après remédiation :

| Contrôle | Résultat |
|---|---|
| Suite Django complète sur PostgreSQL/Redis | 186 découverts : 183 réussis, 0 échec, 3 ignorés explicitement |
| Tests agent Windows | 25 réussis, 0 échec |
| Tests frontend | 18 réussis, 0 échec |
| Ruff backend/agent/connecteurs | aucun problème |
| ESLint et build Vite | réussis; source maps absentes par défaut |
| `manage.py check` / migrations sèches | aucun problème; aucune migration manquante |
| `manage.py check --deploy` avec profil de production | aucun avertissement |
| `pip-audit` après passage à Django 6.0.8 | aucune vulnérabilité connue |
| `npm audit` | aucune vulnérabilité connue |
| Smoke test local | health, schéma, Swagger et frontend : HTTP 200 |

Les six tests ignorés sont les tests d'intégration nécessitant réellement SMTP,
Redis/broker, VMware ou Hyper-V. Ils ne sont pas présentés comme validés.

Depuis la racine PowerShell :

```powershell
. ./scripts/common.ps1
Import-DotEnv 'backend/.env'
$env:CHANNEL_LAYER = 'memory'
Set-Location backend
../.venv/Scripts/python.exe manage.py check
../.venv/Scripts/python.exe manage.py makemigrations --check --dry-run
../.venv/Scripts/python.exe manage.py test --verbosity 1
Set-Location ..
$env:PYTHONPATH = (Resolve-Path agent)
Push-Location agent
../.venv/Scripts/python.exe -m unittest discover -s tests -v
Pop-Location
./.venv/Scripts/python.exe -m ruff check backend agent vmware_connector hyperv_connector
Set-Location frontend
npm audit
npm test
npm run lint
npm run build
```

`check --deploy` doit être exécuté avec le profil de production chargé, pas avec
le profil local HTTP. Un exemple sans secret réel est fourni dans
`backend/.env.production.example`; les valeurs effectives doivent provenir du
secret store de la plateforme.

Audit Python recommandé dans un environnement d'outillage séparé :

```powershell
pip-audit -r backend/requirements.txt
```

Avant mise en production, charger `.env.production.example` depuis un secret
store, exécuter `check --deploy`, valider le certificat PostgreSQL et tester les
headers depuis l'extérieur du reverse proxy.

## Références

- Django, checklist de déploiement : <https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/>
- Django, publication de sécurité 6.0.8 : <https://www.djangoproject.com/weblog/2026/aug/04/security-releases/>
- DRF, throttling : <https://www.django-rest-framework.org/api-guide/throttling/>
- OWASP, Authentication Cheat Sheet : <https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html>
- OWASP, HTML5 Security Cheat Sheet : <https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html>
- OWASP, REST Security Cheat Sheet : <https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html>
- OWASP, WebSocket Security Cheat Sheet : <https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html>
