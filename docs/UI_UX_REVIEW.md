# Revue UI/UX InfraSentinel-AI

Date : 28 août 2026

Branche : `codex/local-enterprise-lab`

Commit de référence : `24fe96748f66e4482dc46e5ebe495bef1cbee6b2`

## Périmètre et méthode

La revue a porté sur toutes les routes React/Vite, les composants partagés, les
styles, les graphiques Recharts, l'authentification navigateur, le WebSocket et
les contrats Django REST consommés par le frontend. Aucun enregistrement de
démonstration n'a été ajouté. Les valeurs restent numériques dans PostgreSQL et
l'API ; les conversions sont uniquement des conversions de présentation.

Baseline avant les nouveaux changements :

- 24 tests frontend découverts et réussis ;
- lint et build Vite réussis ;
- 191 tests Django découverts ;
- première exécution Django bloquée par PostgreSQL/Docker arrêté, et non par le code ;
- 25 tests de l'agent Windows disponibles.

Les cinq fichiers frontend déjà modifiés avant cet audit provenaient de la
correction précédente des grands nombres. Ils ont été conservés puis inclus
dans la revue.

## Contrat des unités vérifié

| Famille | Producteurs | Valeur API | Affichage attendu |
|---|---|---|---|
| CPU/RAM/disque/GPU | Windows, VMware, Hyper-V | `%`, échelle 0–100 | `%`, une décimale maximum |
| Capacité | trois sources | `bytes` | `o`, `Ko`, `Mo`, `Go`, `To` |
| I/O et réseau | trois sources | `bytes/s` | `o/s`, `Ko/s`, `Mo/s`, `Go/s` |
| Latence | Windows | `ms` | `ms`, puis `s` à partir de 1 000 ms |
| Uptime | trois sources | `seconds` | durée composée `j h min s` |
| Processus/VM | Windows/connecteurs | `count` | entier sans unité de stockage |
| Service/VM | Windows/connecteurs | `state` + `status` | libellé opérationnel |
| Score ML | Isolation Forest | sans unité, non borné à 0–1 | score technique et relation au seuil |
| Risque prédictif | analyse temporelle | 0–100 | niveau textuel et pourcentage |

Les collecteurs réels confirment que les pourcentages sont déjà en échelle
0–100. Le frontend ne les multiplie donc jamais implicitement par 100. Une
fraction n'est convertie que pour un champ dont le contrat l'indique, comme la
contamination ML.

## Audit initial par page

### Connexion et inscription

- Labels et contrôle d'affichage du mot de passe présents.
- Toutes les erreurs HTTP étaient présentées comme un mauvais mot de passe.
- L'inscription ne bloquait pas la double soumission.
- La police dépendait d'une ressource Google externe, fragile hors ligne.

### Vue globale

- Les compteurs provenaient bien de `/api/dashboard/`.
- Une courbe reliait CPU, octets, débits, latence, uptime et compteurs sur un
  axe unique : représentation mathématiquement invalide.
- Le badge `LIVE` ne reflétait pas le vrai état WebSocket.
- Le chargement des métriques n'était pas isolé de celui des statistiques.

### Machines et détail machine

- La liste affichait machine, source, IP, état et dernier contact.
- Système d'exploitation et version agent étaient sous-exploités.
- Les lignes ouvrables n'étaient pas accessibles au clavier.
- Le détail ne mettait pas en avant les dernières valeurs.
- `Number(null)` pouvait transformer une mesure absente en zéro.
- Les tendances affichaient une variation sans unité.
- Alertes et anomalies omettaient mesure, seuil et interprétation du score.

### Agents

- Hostname, version, autorisation et heartbeat étaient visibles.
- Aucun parcours frontend ne permettait de générer le code d'enrôlement fourni
  par l'API.
- Le token agent n'était pas exposé, ce qui était correct.
- La révocation n'était pas pilotable depuis l'interface.

### Alertes

- Sévérité, machine, message, occurrences et état étaient visibles.
- Type, source, date, valeur, seuil et recommandation étaient incomplets.
- Le statut `IN_PROGRESS` n'était pas proposé.
- Les mutations rechargeaient la page et masquaient leurs erreurs.

### Anomalies et Machine Learning

- Les scores étaient affichés bruts, sans explication.
- Les features réelles de `explanation.features` n'étaient pas présentées.
- Un modèle actif était représenté par une sévérité `HIGH`.
- Les actions Celery n'avaient aucun feedback.
- Un dataset synthétique n'était pas assez clairement distingué.

### VMware et Hyper-V

- Les inventaires provenaient des endpoints réels ; aucun hôte factice.
- Les détails affichaient encore valeur, unité et metadata JSON brutes.
- Les collectes n'avaient ni progression, ni succès, ni erreur visible.
- Les états vides étaient de simples paragraphes.

### Utilisateurs, configuration et audit

- Rôles et actions d'audit restaient principalement en enum anglais.
- Le menu était filtré par rôle, mais les routes n'avaient pas de garde UX.
- Les règles acceptaient un nom de métrique libre sans unité de seuil.
- Plusieurs formulaires utilisaient `window.location.reload()`.
- Les timestamps étaient formatés indépendamment sur chaque page.

## Priorisation des problèmes

### Critiques

1. Graphique global multi-unité trompeur.
2. Valeur absente susceptible d'être présentée comme zéro.

### Élevés

1. Formatage central incomplet et absent des détails virtualisation.
2. États affichés comme `0 state` ou `1 state`.
3. Actions métier sans feedback.
4. Scores ML sans contexte explicable.

### Moyens

1. Toutes les requêtes de la page réexécutées à chaque événement WebSocket.
2. Tables dépendantes du scroll horizontal sur mobile.
3. Focus et réduction des animations non définis.
4. États loading/error/empty sans reprise cohérente.
5. Metadata technique utilisée comme interface principale.

## Décisions retenues

- Centraliser les conversions dans `frontend/src/metricFormatting.js`.
- Utiliser le nom et l'unité du contrat API, jamais seulement la magnitude.
- Remplacer la courbe globale par un flux de mesures récentes.
- Regrouper les graphiques seulement par unités compatibles.
- Partager timestamp, valeur métrique, statut, sévérité, feedback et états.
- Conserver les détails bruts dans des sections progressives.
- Regrouper les événements WebSocket et invalider les ressources concernées.
- Transformer les tableaux en cartes lisibles sous 620 px.
- Ne jamais ajouter de donnée factice pour remplir un écran.

## Limites API constatées

- `MachineSerializer` ne renvoie pas les dernières métriques : les ajouter à la
  liste nécessiterait un endpoint agrégé ou des requêtes N+1, évitées ici.
- La pagination métrique est limitée à 100 côté DRF.
- Les agrégats ne portent pas encore unité et `source_type`.
- Le contrat producteur définit les pourcentages 0–100, mais le normalizer ne
  borne pas encore ces valeurs.
- Le disque d'une VM VMware décrit l'allocation datastore, pas le filesystem invité.
- Le réseau VM Hyper-V est une moyenne depuis le démarrage, signalée en metadata.
