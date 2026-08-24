# Notifications

Email est le premier canal actif. Teams, Slack et Telegram sont réservés par le
modèle mais sans adaptateur actif. Politique : CRITICAL immédiat, HIGH selon
préférences, WARNING/INFO dashboard uniquement.

La requête principale ne fait pas d'envoi : elle écrit un `NotificationEvent`
durable après commit, crée les livraisons et planifie Celery. Le worker revendique
une livraison, applique le seuil, le cooldown par alerte/préférence, puis utilise
l'adaptateur email. Échec : statut RETRY, erreur journalisée et délai exponentiel;
après huit essais : FAILED. SENT et SUPPRESSED sont terminaux.

Variables SMTP : `EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL`, `EMAIL_HOST`, `EMAIL_PORT`,
`EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`. L'API expose préférences
et historique sous `/api/notifications/`.

