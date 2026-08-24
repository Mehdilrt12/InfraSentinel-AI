# Dashboard

Routes : `/login`, `/dashboard`, `/machines`, `/machines/:id`, `/agents`,
`/alerts`, `/anomalies`, `/vmware`, `/vmware/:id`, `/hyperv`, `/hyperv/:id`,
`/ml`, `/users`, `/settings`, `/audit`.

La vue globale présente assets, online/offline, criticité, anomalies, hosts et
alertes actives. Les détails montrent historique, alertes, anomalies, risque,
tendances estimées et recommandations. Les vues virtualisation séparent
connecteurs, hosts, VM et datastores; ML montre version, holdout temporel,
paramètres, score et absence éventuelle de vérité terrain. Tous les écrans disposent
d'états loading, empty, error, offline et partial, couverts par tests de rendu. Le
CSS est responsive et les routes sont chargées paresseusement en chunks Vite.
