# Dashboard

Routes : `/login`, `/dashboard`, `/machines`, `/machines/:id`, `/agents`,
`/alerts`, `/anomalies`, `/vmware`, `/vmware/:id`, `/hyperv`, `/hyperv/:id`,
`/ml`, `/users`, `/settings`, `/audit`.

La vue globale présente assets, online/offline, criticité, anomalies, hosts et
alertes actives. Les détails montrent historique, alertes, anomalies, risque et
recommandations. Les vues virtualisation séparent connecteurs, hosts et VM; ML
montre version, paramètres, score et évaluation. Tous les écrans disposent d'états
loading, empty, error, offline et partial. Le CSS est responsive. Vite produit des
chunks et source maps; les routes peuvent être lazy-loadées si le dashboard croît.

