# Évaluation du Machine Learning

## Ce qui est mesuré

L'évaluation sépare performance statistique non supervisée et comparaison
opérationnelle. Pendant le training, le holdout chronologique de 20 % mesure taux
d'anomalie, distribution des scores et stabilité du seuil sans réentraîner sur le
futur. La tâche `ml.evaluate` compare ensuite anomalies et incidents issus des
règles dans une fenêtre de 15 minutes.

| Mesure | Disponible | Interprétation |
|---|---|---|
| taux d'anomalie holdout | oui | fréquence des fenêtres au-dessus du seuil |
| distribution des scores | oui | dérive/dispersion des scores |
| overlap règles/anomalies | oui | concordance opérationnelle, pas vérité terrain |
| précision/rappel/F1 | non sans labels | restent explicitement `null` |

`ground_truth_available=false` empêche d'afficher une exactitude inventée. Des
alertes basées sur seuils ne constituent pas automatiquement des labels scientifiques.

## Reproduction

```powershell
./scripts/evaluate-ml.ps1 -CustomerId <uuid> -Days 30
# ou
./.venv/Scripts/python.exe backend/manage.py evaluate_ml --customer-id <uuid> --days 30
```

L'API `POST /api/ml/models/evaluate/` planifie la même logique via Celery et crée un
événement d'audit. Conserver commit, version de modèle, paramètres, période, tenant,
volume de fenêtres et indicateur synthétique avec tout rapport.

## Protocole PFE recommandé

1. Constituer un historique réel et documenter les périodes incomplètes.
2. Faire annoter indépendamment les incidents par un administrateur.
3. Geler train/validation/test dans le temps, sans fuite entre périodes.
4. Comparer aux règles et à une baseline simple.
5. Rapporter faux positifs, faux négatifs et intervalles, pas seulement une moyenne.

Le dataset PFE synthétique sert à démontrer le flux UI/API; il n'est pas un résultat
scientifique réel. Les tests vérifient les calculs et métadonnées, pas la capacité de
généralisation sur une infrastructure inconnue.
