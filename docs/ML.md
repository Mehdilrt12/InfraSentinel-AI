# Pipeline Machine Learning

```text
NormalizedMetric -> validation -> fenêtres 5 min -> pivot features -> imputation
-> RobustScaler -> IsolationForest -> évaluation -> version -> artifact -> inference
```

Features : CPU, RAM, disque, network in/out et latence. Paramètres initiaux :
`n_estimators=200`, `contamination=0.02`, `random_state=42`, `n_jobs=-1`.
L'imputation médiane et le RobustScaler sont stockés dans le même pipeline que le
modèle. Le dataset trié chronologiquement est séparé 80/20. Le pipeline et le seuil
sont ajustés uniquement sur les 80 % initiaux; les 20 % finaux constituent le
holdout temporel. Le seuil est le quantile correspondant à la contamination sur le
score `-decision_function` du training.

Chaque `MLModelVersion` conserve date, features, preprocessing, paramètres,
période/nombre d'échantillons, taux d'anomalie validation, distribution des scores,
seuil et artifact. L'artifact est référencé par nom relatif dans un volume partagé;
l'écriture est atomique et un seul modèle actif est autorisé par client.
Training et inference sont des tâches séparées et idempotentes. Moins de 20
fenêtres réelles provoquent un refus explicite. Aucune donnée synthétique n'est
livrée ou présentée comme réelle.

Sans labels opérationnels réels, précision et rappel restent explicitement `null`.
Voir `ML_EVALUATION.md` et `PREDICTIVE.md`.
