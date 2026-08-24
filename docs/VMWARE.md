# Intégration VMware

Le module `vmware_connector` utilise réellement pyVmomi : `SmartConnect`, vues
`vim.HostSystem`/`vim.VirtualMachine` et `PerformanceManager`. La configuration
contient endpoint, utilisateur, TLS, timeout et `secret_ref`; le mot de passe est
lu depuis la variable nommée par `secret_ref`.

Hôtes : CPU, mémoire, stockage utilisé/libre, réseau reçu/transmis, uptime,
health, modèle, vendor et nombre de VM. VM : CPU, RAM, disque, réseau, uptime,
power state, hôte parent, guest et datastores. Les datastores sont aussi découverts
comme assets avec capacité libre, taux d'utilisation, accessibilité, type et URL.
Les compteurs réseau vSphere en KiB/s sont convertis en `bytes/s`. Les compteurs
indisponibles restent `null` : aucune valeur n'est inventée.

La découverte crée/met à jour `VirtualAsset` et `Machine`, puis normalise les
mesures avant PostgreSQL, règles, ML et dashboard. Les erreurs connexion/auth/TLS,
timeouts et ressources indisponibles sont enregistrées dans `CollectionRun` et le
connecteur. Celery applique retry/backoff.

Les tests mock prouvent orchestration, idempotence, calcul datastore et erreurs,
mais pas une session vCenter réelle.

`NOT TESTED — REAL VMWARE ENVIRONMENT REQUIRED`
