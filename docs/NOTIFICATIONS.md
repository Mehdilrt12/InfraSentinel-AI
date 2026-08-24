# Notifications

Email est le premier canal actif. Teams, Slack et Telegram sont réservés par le
modèle mais sans adaptateur actif. Politique : CRITICAL immédiat, HIGH selon
préférences, WARNING/INFO dashboard uniquement.

La requête principale ne fait pas d'envoi : elle écrit un `NotificationEvent`
durable après commit, crée les livraisons et planifie Celery. Le worker revendique
une livraison sous verrou PostgreSQL, applique le seuil, le cooldown par
alerte/préférence, puis utilise l'adaptateur email. Deux workers concurrents ne
peuvent envoyer deux fois la même livraison. Un état `SENDING` abandonné est repris
après timeout. Une escalade HIGH vers CRITICAL contourne le cooldown. Échec : statut
RETRY, erreur journalisée et délai exponentiel; après huit essais : FAILED. SENT et
SUPPRESSED sont terminaux. La tâche Celery reste mince et appelle ce service métier.

Variables SMTP : `EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL`, `EMAIL_HOST`, `EMAIL_PORT`,
`EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `EMAIL_TIMEOUT`. L'API expose préférences
et historique sous `/api/notifications/`.

`NOT TESTED — EXTERNAL SMTP DELIVERY`
