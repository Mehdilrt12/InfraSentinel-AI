# Rapport de performance du laboratoire local

**Exécution fraîche :** 27 août 2026

**Run :** `P2420260827064742`

**Données :** agents et métriques synthétiques, isolés puis supprimés

## Environnement

| Composant | Valeur observée |
|---|---|
| Hôte | Windows, 32 CPU logiques / 24 physiques, 31,73 Gio RAM |
| API testée | un processus Daphne dédié, Django 6.0.8, Python 3.14.6, `DEBUG=false` |
| PostgreSQL | 17.11 Alpine, `max_connections=100` |
| Redis | 7.4.11 Alpine |
| Modèle de charge | agents closed-loop avec jitter initial |
| Lot agent | 12 métriques normalisées par seconde |
| Réseau | loopback HTTP, sans TLS ni latence WAN |

La cadence est environ trente fois plus agressive que l'intervalle nominal de
30 secondes. Elle cherche un plafond local, pas un dimensionnement de production.

## Résultats frais

| Agents | req/s | erreurs | p50 | p95 | p99 | CPU API moyen | RSS max | connexions PG max | Redis clients max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 5 | 5,50 | 0 % | 66,62 ms | 96,69 ms | 146,43 ms | 11,64 % | 246,00 Mio | 23 | 50 |
| 10 | 10,96 | 0 % | 60,46 ms | 87,98 ms | 96,79 ms | 26,16 % | 246,93 Mio | 27 | 55 |
| 25 | 27,42 | 0 % | 64,84 ms | 92,39 ms | 103,97 ms | 58,87 % | 249,31 Mio | 46 | 84 |
| 50 | 54,58 | 0 % | 114,53 ms | 330,93 ms | 381,51 ms | 130,60 % | 258,45 Mio | 71 | 117 |

À 50 agents, la latence p95 est multipliée par 3,58 par rapport à 25 agents et
le processus consomme environ 1,31 cœur. La latence interne de traitement p95
atteint 185,26 ms, contre 71,46 ms à 25 agents. C'est le premier signal de
saturation significatif de ce run court; la campagne a donc été arrêtée avant
100/150/250.

Les files Celery et Hyper-V sont restées à zéro, aucun deadlock ou fichier
temporaire PostgreSQL n'a été observé, et le cache PG est resté à 99,97 % ou
plus. Le générateur a supprimé toutes ses données : zéro tenant `perf-*` et aucun
listener sur le port 8010 après le test.

## Mise en perspective avec le benchmark long existant

Le rapport historique vérifié dans `docs/PERFORMANCE.md` a exécuté 30 secondes
par palier jusqu'à 100 agents. Il a observé 9,35 % d'erreurs à 50 agents et
69,92 % à 100, avec PostgreSQL à 100 connexions et `FATAL: too many clients`.
Le run court frais n'invalide pas cette saturation : il n'a simplement pas duré
assez longtemps pour accumuler autant de connexions persistantes.

Maximum du run frais : **50 agents**, p50 **114,53 ms**, p95 **330,93 ms**, p99
**381,51 ms**, erreur **0 %** sur dix secondes. Maximum historique : **100
agents**, mais avec un taux d'erreur inacceptable de **69,92 %**.

## Reproduction

```powershell
./scripts/run-performance-test.ps1 `
  -Stages '5,10,25,50' `
  -DurationSeconds 10 `
  -IntervalSeconds 1 `
  -HeartbeatIntervalSeconds 60 `
  -CooldownSeconds 2 `
  -Port 8010
```

Le rapport JSON brut reste sous `runtime/performance/`, volontairement ignoré
par Git. Ne pas annoncer 250 agents supportés : ce palier n'a pas été exécuté.

## Recommandations

1. borner le pool de connexions et tester PgBouncer avant de relever la charge;
2. aligner concurrence Daphne/Celery et budget PostgreSQL;
3. rejouer des paliers isolés de 2 à 24 heures;
4. tester ensuite TLS, LAN/WAN, plusieurs générateurs et WebSocket simultané;
5. définir un SLO p95/p99 et un taux d'erreur acceptable avant toute capacité
   officielle.

## Verdict performance

**PARTIAL.** Le banc est reproductible et 25 agents à cadence extrême restent
stables sur ce run. Le plafond durable n'est pas établi; les résultats historiques
prouvent une saturation du budget de connexions à 50-100 agents.
