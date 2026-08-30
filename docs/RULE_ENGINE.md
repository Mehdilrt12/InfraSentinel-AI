# Moteur de règles

## Modèle

`MonitoringRule` porte `name`, `metric`, `operator`, `threshold`,
`duration_seconds`, `severity`, `enabled`, les scopes optionnels `environment` et
`machine`, et `cooldown_seconds`. Les opérateurs acceptés sont `>`, `<`, `>=`,
`<=`, `==` et `!=`. Les sévérités sont `INFO`, `WARNING`, `HIGH`, `CRITICAL`.

`RuleState` mémorise par règle, machine et dimension le premier instant vrai, la
dernière mesure évaluée, la dernière correspondance, sa valeur, le nombre de
correspondances consécutives, le nombre de mesures normales consécutives et l'état
actif. La contrainte unique rend cet état déterministe pour un service, volume,
disque, GPU ou datastore.

## Évaluation temporelle

```mermaid
stateDiagram-v2
  [*] --> Normal
  Normal --> Pending: condition vraie
  Pending --> Normal: condition fausse
  Pending --> Active: durée atteinte + 2 preuves
  Active --> Active: condition vraie / alerte corrélée
  Active --> Recovery: première mesure normale
  Recovery --> Active: condition vraie
  Recovery --> Normal: deuxième mesure normale / résolution
```

Les mesures sont lues dans l'ordre temporel; une mesure plus ancienne que le dernier
état est ignorée. Pour une durée non nulle, une condition doit couvrir la durée et
fournir au moins deux mesures correspondantes. Un écart supérieur au maximum de
120 secondes ou deux fois la durée réinitialise la preuve : deux pics éloignés ne
simulent pas une condition continue. Une alerte active survit à une première mesure
normale et se résout après deux normales consécutives. Une nouvelle valeur anormale
pendant cette récupération maintient l'incident. Les règles à durée nulle gardent
leur comportement instantané pour compatibilité. La règle spéciale
`machine.online` évalue `last_seen` et bascule la machine hors ligne après sa durée.

## API

`/api/rules/` expose le CRUD paginé. Les ADMIN/SUPERVISOR gèrent les règles de leur
tenant; le backend valide que machine et environnement appartiennent au même
customer. L'action d'activation/désactivation documentée par OpenAPI est la source
de vérité; consulter `/api/docs/` pour le corps exact de la version déployée.

```json
{
  "name": "CPU durable > 90 %",
  "metric": "system.cpu.utilization",
  "operator": ">",
  "threshold": 90,
  "duration_seconds": 300,
  "severity": "HIGH",
  "enabled": true,
  "environment": null,
  "machine": null,
  "cooldown_seconds": 600
}
```

## Exécution et limites

Celery Beat appelle `monitoring.evaluate_rules` chaque minute. L'ancien comportement
instantané reste représentable avec une durée nulle; les seuils ne sont plus codés
dans les collecteurs. La précision effective d'une durée dépend toutefois de la
fréquence de collecte et de Beat. Une absence de mesures n'est pas identique à une
valeur basse : utiliser `machine.online` pour la disponibilité.

Les tests couvrent opérateurs, durée, écart maximal entre preuves, hystérésis de
récupération, dimensions, offline, concurrence et isolation multi-tenant. La
validation réelle du 30 août a conservé le seuil `CPU > 80 % pendant 30 s` :
le banc borné à 24 workers sur 32 processeurs logiques n'a atteint que 76,2 %, donc
aucune alerte n'était attendue et la preuve matérielle reste PARTIAL. En cas de
déclenchement tardif, vérifier la fréquence des métriques, les timestamps, Beat,
le worker et le `RuleState` correspondant.
