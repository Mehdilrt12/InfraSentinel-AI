# Moteur de règles

`MonitoringRule` fournit nom, métrique, opérateur (`>`, `<`, `>=`, `<=`, `==`,
`!=`), seuil, durée, sévérité, activation, environnement, machine et cooldown.
`RuleState` mémorise le début continu de la condition par machine. Une valeur
redevenue normale remet l'état à zéro. L'alerte n'est créée qu'après la durée.
Le CRUD et l'activation sont disponibles sous `/api/rules/` et dans Settings.
L'ancien principe de seuils est couvert par des règles à durée zéro; les seuils ne
sont plus dispersés dans les collecteurs.

