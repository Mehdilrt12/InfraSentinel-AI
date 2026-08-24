# Recommandations

La chaîne est `Anomaly -> Context -> Diagnosis hints -> Recommendation`. Le
catalogue produit des hypothèses et actions pour CPU, RAM, disque, latence et
services. Le contexte `resource_kind` produit des conseils dédiés aux hôtes VMware
et Hyper-V : VM dominantes, répartition de charge, allocations et capacité. Toutes les actions sont
explicables et non destructives par défaut. Une extension de volume, un nettoyage
ou un redémarrage n'est jamais exécuté automatiquement : validation humaine et
analyse d'impact sont requises.
