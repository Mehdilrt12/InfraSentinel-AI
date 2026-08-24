# Pipeline Machine Learning

```text
NormalizedMetric -> validation -> fenêtres 5 min -> pivot features -> imputation
-> RobustScaler -> IsolationForest -> évaluation -> version -> artifact -> inference
```

Features : CPU, RAM, disque, network in/out et latence. Paramètres initiaux :
`n_estimators=200`, `contamination=0.02`, `random_state=42`, `n_jobs=-1`.
L'imputation médiane et le RobustScaler sont stockés dans le même pipeline que le
modèle. Le seuil est le quantile correspondant à la contamination sur le score
`-decision_function` du training.

Chaque `MLModelVersion` conserve date, features, preprocessing, paramètres,
période/nombre d'échantillons, taux d'anomalie, moyenne/écart des scores, seuil et
artifact. L'écriture de l'artifact est atomique et l'activation transactionnelle.
Training et inference sont des tâches séparées et idempotentes. Moins de 20
fenêtres réelles provoquent un refus explicite. Aucune donnée synthétique n'est
livrée ou présentée comme réelle.

