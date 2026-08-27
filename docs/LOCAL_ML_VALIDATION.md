# Validation locale Machine Learning et analyse proactive

**Date :** 27 août 2026

**Environnement :** Django/PostgreSQL/Redis dans Docker, modèle dans le volume
`model_store`

**Nature des données :** `CONTROLLED TEST DATA` synthétiques, jamais présentées
comme historique de production

## Objectif scientifique vérifié

La validation couvre la chaîne réellement implémentée :

```text
NormalizedMetric -> fenêtres de 5 min -> imputation médiane -> RobustScaler
-> Isolation Forest -> score/threshold -> Anomaly -> Alert
                    + tendance linéaire/règle -> risque prévisionnel
                    + règles temporelles -> recommandation explicable
```

## Préparation reproductible

Le tenant utilisé doit être dédié à la démonstration. Le mot de passe temporaire
n'est ni versionné ni affiché dans les résultats.

```powershell
$env:PFE_DEMO_PASSWORD = Read-Host 'Mot de passe temporaire' -MaskInput
docker compose --env-file .env exec -e PFE_DEMO_PASSWORD=$env:PFE_DEMO_PASSWORD `
  -T api python manage.py prepare_pfe_demo --customer-slug <tenant-demo> --reset
Remove-Item Env:\PFE_DEMO_PASSWORD
```

La commande marque les machines, métriques, connecteurs et modèles avec
`synthetic=true`, `demo_suite=PFE25` et `purpose=jury_demonstration_only`.

## Entraînement observé

| Élément | Valeur observée |
|---|---|
| Algorithme | `IsolationForest` |
| Version | `iforest-20260827T053628-8c1dc4bc` |
| Fenêtres | 36, dont 28 entraînement et 8 validation chronologique |
| Features | CPU, RAM, disque, réseau entrant/sortant, latence |
| Prétraitement | imputation médiane, `RobustScaler`, fenêtres 5 minutes |
| `n_estimators` | 200 |
| `contamination` | 0,02 |
| `random_state` | 42 |
| Seuil appris | `3.122502256758253e-17` |
| Artefact | présent dans le volume, SHA-256 `e8abc43add487865d697fce9c210fdac4c17eae081fa1696325ea36e1411acaf` |

L'évaluation ne dispose pas de vérité terrain : précision et rappel restent
explicitement `null`. Le taux d'anomalie d'entraînement observé est 3,57 % et
celui du holdout 0 %. Ces valeurs ne prouvent pas la qualité sur des données
réelles.

## Inférence réellement exécutée

Le pipeline Joblib a été chargé depuis l'artefact, puis sa vraie
`decision_function` a évalué 61 fenêtres normalisées :

- 59 fenêtres sous le seuil;
- 2 fenêtres au-dessus ou égales au seuil;
- score minimum `-0.0924608589`;
- score maximum `0.0285858732`;
- une anomalie contrôlée nouvelle persistée par la préparation PFE.

Commande de preuve depuis le runtime qui possède le volume modèle :

```powershell
Get-Content -Raw scripts/final_ml_probe.py |
  docker compose --env-file .env exec -T api python -
```

Exécuter le même script dans le Python hôte après un entraînement Docker échoue
correctement si l'artefact n'existe que dans le volume Docker. Le registre en
base et le stockage d'artefacts doivent donc appartenir au même mode d'exécution.

## Règles, ML et hybride

Sur la fenêtre contrôlée : quatre incidents de règles, une anomalie ML et aucun
recouvrement à quinze minutes ont été observés. Sans labels, ce résultat décrit
les événements persistés; il ne permet pas de calculer faux positifs, faux
négatifs, précision ou rappel.

## Analyse prédictive

Le premier probe retournait zéro risque parce que l'historique PFE datait de plus
de 24 heures, donc sortait volontairement de la fenêtre. Après régénération à
l'heure courante, sans modifier l'algorithme :

| Champ | Résultat |
|---|---|
| Métrique | `system.cpu.utilization` |
| Tendance | `INCREASING` |
| Taux | `4.0` points par heure |
| Risque | `70` |
| Confiance | `MEDIUM` |
| Seuil | règle CPU du scénario |
| Échéance | calculée par la logique applicative, environ 3 h 45 après le probe |
| Marquage | `is_estimate=true` avec avertissement explicite |

Le résultat est une extrapolation linéaire, pas une certitude de panne.

## Recommandations

Cinq alertes ont été contrôlées. Chacune possède des pistes de diagnostic et des
actions; toutes ont `destructive=false`. CPU, RAM, disque, offline et anomalie ML
sont couverts. Les conseils VMware/Hyper-V sont testés par unité mais ne valent
pas validation d'un environnement réel.

## Verdict ML local

**PASS sur données contrôlées synthétiques** pour entraînement reproductible,
stockage/version, chargement, inférence, score, persistance, règles, tendance et
recommandation. **PARTIAL scientifiquement** tant qu'un dataset réel labellisé
n'est pas disponible pour mesurer précision, rappel et dérive.
