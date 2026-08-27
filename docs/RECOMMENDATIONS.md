# Moteur de recommandations

## Principe

La chaîne réelle est `Anomaly/Alert -> contexte -> hypothèses de diagnostic ->
actions proposées`. À la création d'une alerte, le service construit une
`Recommendation` structurée en `diagnosis_hints`, `actions`, `rationale` et
`destructive=false`; un résumé textuel reste dans l'alerte pour compatibilité.

Le catalogue couvre CPU, mémoire, utilisation/espace disque, latence et service
Windows. Pour un hôte VMware surchargé, il propose d'identifier les VM dominantes et
d'évaluer une redistribution contrôlée. Pour Hyper-V, il compare allocations des VM
et capacité physique avant tout rééquilibrage.

## Exemple

```json
{
  "diagnosis_hints": [
    "Identifier les processus les plus consommateurs",
    "Vérifier les changements et la charge récente"
  ],
  "actions": [
    "Comparer la charge au profil habituel",
    "Inspecter les services associés"
  ],
  "rationale": "Recommandation explicable fondée sur system.cpu.utilization et le contexte WINDOWS.",
  "destructive": false
}
```

## Garde-fous et limites

Le moteur n'exécute aucune commande. Nettoyage, extension, redémarrage ou migration
exigent validation humaine et analyse d'impact. Les conseils sont déterministes et
explicables, pas générés par un LLM ni adaptés automatiquement à une CMDB. Pour une
métrique inconnue, un conseil générique invite à comparer l'historique et les
changements récents.

Les tests vérifient les catalogues, contextes VMware/Hyper-V, caractère non
destructif, création OneToOne et exposition via l'alerte. Si le contexte spécifique
manque, vérifier `source_type` et `metadata.resource_kind` dans la mesure/alerte.
