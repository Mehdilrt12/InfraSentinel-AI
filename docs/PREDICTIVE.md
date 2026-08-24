# Analyse prédictive

`GET /api/machines/<id>/trends/?hours=24` analyse l'historique normalisé réel de la
machine. Pour chaque métrique disposant d'au moins trois points, le service calcule
une moyenne glissante des cinq derniers points, une pente linéaire, le taux de
variation par heure et une tendance `INCREASING`, `DECREASING` ou `STABLE`.

Lorsqu'une règle de seuil applicable existe et que la pente évolue vers ce seuil,
le service peut calculer une date estimée de franchissement, un risque et une
confiance fondée sur le nombre de points et la durée observée. Une projection de
plus de dix ans est volontairement ignorée.

Chaque résultat contient `is_estimate=true` et un avertissement : la projection
linéaire est une aide à l'analyse, jamais une certitude ni une action automatique.
Le dashboard reprend ce libellé et n'affiche rien lorsque l'historique réel est
insuffisant.
