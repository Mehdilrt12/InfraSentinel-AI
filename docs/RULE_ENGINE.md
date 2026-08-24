# Moteur de règles

`MonitoringRule` fournit nom, métrique, opérateur (`>`, `<`, `>=`, `<=`, `==`,
`!=`), seuil, durée, sévérité, activation, environnement, machine et cooldown.
`RuleState` mémorise le début continu par machine et par dimension (service,
volume, disque, GPU ou datastore). Une valeur redevenue normale remet l'état à
zéro et résout l'alerte correspondante. L'alerte n'est créée qu'après la durée.
Le CRUD et l'activation sont disponibles sous `/api/rules/` et dans Settings.
L'ancien principe de seuils est couvert par des règles à durée zéro; les seuils ne
sont plus dispersés dans les collecteurs.
