# Journal d'audit — InfraSentinel AI

## Objectif

Le journal d'audit fournit une trace centralisée, horodatée, multi-tenant et
append-only des opérations de sécurité et d'administration. Il est distinct des
logs techniques : une ligne d'audit décrit **qui a fait quoi, sur quelle cible,
quand et depuis quelle adresse**, sans enregistrer de secret.

## Modèle

`monitoring.AuditLog` contient :

| Champ | Rôle |
|---|---|
| `customer` | client concerné; nullable uniquement après suppression légitime du tenant |
| `actor` | utilisateur à l'origine de l'action; nul pour un moteur ou un agent |
| `actor_email` | snapshot conservé si le compte est supprimé |
| `action` | identifiant stable de l'événement |
| `target_type`, `target_id`, `target_repr` | type, identifiant et libellé snapshot de la cible |
| `timestamp` | date UTC générée par le serveur |
| `ip_address` | IP validée; `X-Forwarded-For` n'est utilisé que si le nombre de proxies de confiance est configuré |
| `metadata` | contexte JSON borné et nettoyé des secrets |

`created_at`, `context` et `target` restent exposés par le serializer comme alias
de compatibilité API. Les champs canoniques sont `timestamp`, `metadata` et les
trois colonnes de cible.

## Actions

Actions obligatoires implémentées :

- `USER_LOGIN`, `USER_LOGOUT`, `USER_CREATED`, `USER_UPDATED` ;
- `AGENT_ENROLLED`, `AGENT_REVOKED` ;
- `MACHINE_CREATED`, `MACHINE_UPDATED` ;
- `ALERT_CREATED`, `ALERT_ACKNOWLEDGED`, `ALERT_RESOLVED` ;
- `MODEL_TRAINED`, `CONFIG_CHANGED`.

Le vocabulaire comprend aussi les événements utiles `USER_DELETED`,
`MACHINE_DELETED`, `ALERT_IN_PROGRESS`, les planifications ML/collecteur et la
création d'un code d'enrollment. Une alerte créée ou résolue automatiquement et
un modèle entraîné par Celery utilisent un acteur système nul.

## Immutabilité

La sécurité est appliquée à trois niveaux :

1. le ViewSet DRF est strictement en lecture seule ;
2. `save()` et `delete()` refusent toute mutation d'une instance existante ;
3. un trigger PostgreSQL refuse les `UPDATE` et `DELETE`, y compris par
   `QuerySet.update()` ou SQL applicatif.

Le trigger autorise uniquement la mise à `NULL` des foreign keys `actor` ou
`customer` lors d'une suppression légitime. Les snapshots `actor_email`, cible,
action, IP, métadonnées et timestamp restent intacts. Les permissions Django
`change_auditlog` et `delete_auditlog` sont supprimées par migration.

Un administrateur de la base reste techniquement capable de désactiver un
trigger : en production, le rôle PostgreSQL de l'application ne doit donc ni
être propriétaire du schéma ni posséder `ALTER`/`TRIGGER`.

## API et permissions

Routes :

- `GET /api/audit/` : liste paginée ;
- `GET /api/audit/{id}/` : détail ;
- toute méthode d'écriture retourne `405 Method Not Allowed`.

Seuls `ADMIN`, `SUPERVISOR` et le superutilisateur plateforme peuvent lire le
journal. Les résultats restent limités au `customer` courant. Le superutilisateur
peut fournir le filtre `customer=<uuid>`.

Filtres de liste :

| Paramètre | Description |
|---|---|
| `action` | action exacte |
| `actor` | ID utilisateur exact |
| `target_type`, `target_id` | cible exacte |
| `ip_address` | IPv4/IPv6 exacte |
| `from`, `to` | bornes ISO 8601 inclusives |
| `search` | recherche action, email acteur et cible |
| `ordering` | `timestamp`, `-timestamp`, `action`, `-action` |
| `page`, `page_size` | pagination; maximum 200 lignes |

Exemple :

```http
GET /api/audit/?action=AGENT_REVOKED&from=2026-08-01T00:00:00Z&page_size=50
Authorization: Bearer <access-token>
```

## Dashboard

La page `/audit` propose recherche, action, acteur, type de cible, IP, période,
pagination, affichage des métadonnées et états loading/empty/error. Les contrôles
n'offrent aucune mutation.

## Données sensibles et rétention

Les clés contenant `password`, `secret`, `token`, `authorization`, `cookie`,
`credential` ou `api_key` sont remplacées par `[REDACTED]`. Les corps complets,
tokens d'agent, codes d'enrollment, JWT et mots de passe ne doivent jamais être
placés dans les métadonnées.

La durée de rétention doit être fixée selon les obligations de l'organisation.
Une purge éventuelle doit être une opération hors ligne, explicitement autorisée,
documentée et exécutée avec un rôle PostgreSQL dédié; l'API applicative ne fournit
aucune suppression.

## Validation

```powershell
. ./scripts/common.ps1
Import-DotEnv 'backend/.env'
Set-Location backend
../.venv/Scripts/python.exe manage.py migrate --noinput
../.venv/Scripts/python.exe manage.py test monitoring.tests.test_audit_logs -v 2
../.venv/Scripts/python.exe manage.py test -v 1
Set-Location ../frontend
npm test -- --run
npm run lint
npm run build
```
