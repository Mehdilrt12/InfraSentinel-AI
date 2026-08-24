# Évaluation ML

L'évaluation comporte deux niveaux distincts afin de ne pas inventer de qualité
scientifique.

1. Lors du training, les fenêtres réelles sont triées dans le temps. Les 80 %
   initiales servent à ajuster prétraitement, Isolation Forest et seuil; les 20 %
   finales servent de holdout chronologique. Sont conservés le taux d'anomalie et
   la distribution des scores de validation.
2. `ml.evaluate` compare, sur une période donnée, les incidents issus des règles,
   les anomalies ML et leurs recouvrements dans une fenêtre de 15 minutes. Il
   mesure des volumes opérationnels, pas une exactitude supervisée.

Sans labels réels d'incident, `ground_truth_available=false`, `precision=null` et
`recall=null`. Le projet ne produit donc ni précision, ni rappel, ni F1 inventés.

```powershell
./scripts/evaluate-ml.ps1 -CustomerId <uuid> -Days 30
```

La commande équivalente est `python manage.py evaluate_ml`. L'API
`POST /api/ml/models/evaluate/` planifie la même logique via Celery et l'enregistre
dans l'audit. Les fixtures synthétiques ne sont utilisées que dans les tests et y
sont explicitement marquées comme telles.
