CATALOG = {
    "system.cpu.utilization": (
        [
            "Identifier les processus les plus consommateurs",
            "Vérifier les changements et la charge récente",
        ],
        [
            "Comparer la charge au profil habituel",
            "Inspecter les services associés",
            "Répartir la charge si la capacité est durablement insuffisante",
        ],
    ),
    "system.memory.utilization": (
        [
            "Identifier les processus gourmands en mémoire",
            "Chercher des signes de fuite mémoire",
        ],
        [
            "Comparer mémoire disponible et engagée",
            "Vérifier la capacité allouée",
            "Planifier une augmentation après validation",
        ],
    ),
    "system.disk.utilization": (
        [
            "Identifier les volumes et répertoires responsables",
            "Vérifier la croissance récente",
        ],
        [
            "Nettoyer uniquement les données temporaires validées",
            "Appliquer la politique de rétention",
            "Étendre le stockage avec approbation",
        ],
    ),
    "system.disk.free": (
        [
            "Identifier les fichiers volumineux",
            "Contrôler journaux et sauvegardes locales",
        ],
        [
            "Archiver selon la politique de conservation",
            "Étendre le volume après analyse d'impact",
        ],
    ),
    "system.network.latency": (
        ["Tester le chemin réseau", "Comparer avec d'autres hôtes du même segment"],
        [
            "Inspecter perte, saturation et changements réseau",
            "Escalader vers l'équipe réseau avec les mesures",
        ],
    ),
    "windows.service.state": (
        [
            "Vérifier l'état et les événements du service critique",
            "Identifier la cause de l'arrêt",
        ],
        [
            "Valider les dépendances et le compte de service",
            "Redémarrer seulement après autorisation et analyse",
        ],
    ),
}


def build_recommendation(metric_name, context=None):
    hints, actions = CATALOG.get(
        metric_name,
        (
            [
                "Comparer l'événement à l'historique de la machine",
                "Vérifier les changements récents",
            ],
            [
                "Collecter des éléments de diagnostic",
                "Faire valider toute action corrective par un administrateur",
            ],
        ),
    )
    context = context or {}
    source = context.get("source_type", "source supervisée")
    resource_kind = (context.get("metric_metadata") or {}).get("resource_kind")
    hints = list(hints)
    actions = list(actions)
    if (
        source == "VMWARE"
        and resource_kind == "HOST"
        and metric_name
        in {
            "system.cpu.utilization",
            "system.memory.utilization",
        }
    ):
        hints.append("Identifier les VM qui contribuent le plus à la charge de l'hôte")
        actions.append("Évaluer une redistribution contrôlée des workloads entre hôtes")
    if (
        source == "HYPERV"
        and resource_kind == "HOST"
        and metric_name
        in {
            "system.cpu.utilization",
            "system.memory.utilization",
        }
    ):
        hints.append("Comparer les allocations des VM à la capacité physique de l'hôte")
        actions.append(
            "Rééquilibrer les allocations uniquement après validation de capacité"
        )
    return {
        "diagnosis_hints": hints,
        "actions": actions,
        "rationale": f"Recommandation explicable fondée sur {metric_name} et le contexte {source}.",
        "destructive": False,
    }
