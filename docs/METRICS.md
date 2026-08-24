# Métriques normalisées

Le contrat commun contient `timestamp`, `source_type`, `environment`, `machine`,
`metric_name`, `metric_value`, `unit`, `status`, `metadata` et une clé d'idempotence.

Les CPU Windows, VMware et Hyper-V deviennent
`system.cpu.utilization`. Les noms communs couvrent mémoire, disque, espace libre,
I/O, réseau entrant/sortant, latence, uptime, processus et GPU. Les dimensions
spécifiques restent dans `metadata`; les états de service et VM ont des noms
`windows.service.state` et `virtual.machine.state`. Les débits communs sont stockés
en `bytes/s`; les entrées KiB/MiB/GiB par seconde sont converties tout en gardant
`original_unit` dans les métadonnées. Le normalizer rejette les lots vides, dates
invalides ou trop futures, NaN/infini, métadonnées non JSON, identifiants trop longs
et lots de plus de 5000 mesures.
