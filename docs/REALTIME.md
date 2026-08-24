# Temps réel / WebSocket

Flux : `Agent/Connector -> PostgreSQL outbox -> Channel Layer Redis -> WebSocket
tenant -> Dashboard`. Événements : `machine.online`, `machine.offline`,
`metric.update`, `alert.created`, `alert.updated`, `anomaly.detected`.

Le navigateur obtient un ticket signé valable 60 secondes via JWT HTTP, puis se
connecte sans placer son access token dans l'URL. Le consumer revalide user/client,
rejoint uniquement `tenant_<uuid>` et rejoue au maximum 500 événements depuis le
dernier numéro de séquence. Plusieurs clients reçoivent le même groupe; une
déconnexion n'affecte pas les autres.

Le curseur frontend est stocké en session avec une clé propre au client, empêchant
un changement de tenant de réutiliser une séquence étrangère. Le frontend empêche
les doubles connexions, reconnecte avec backoff exponentiel et arrête timers/socket
à la destruction. En cas d'échec il conserve un polling de secours toutes les 30
secondes. Les événements perdus sont rejoués depuis
PostgreSQL. Les tests ASGI couvrent connexion, reconnexion avec replay, plusieurs
clients, déconnexion indépendante, curseur invalide et rejet d'un ticket invalide.
