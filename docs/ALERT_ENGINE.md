# Moteur d'alertes

Le flux est `Metrics -> Rules + ML -> Risk -> Alert`. Une alerte contient machine,
customer, timestamps, type, sévérité, source, message, contexte, score éventuel,
recommandation, statut, occurrences et niveau d'escalade. États : `NEW`,
`ACKNOWLEDGED`, `IN_PROGRESS`, `RESOLVED`.

La clé SHA-256 machine/type/source corrèle les répétitions dans une alerte ouverte.
Les occurrences et la dernière observation sont mises à jour sans créer une ligne
par échantillon. Le cooldown des notifications empêche le spam. Résoudre une
alerte permet à un événement ultérieur de créer un nouvel incident durable.

