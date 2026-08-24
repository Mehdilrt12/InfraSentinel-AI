# Intégration VMware

Le module `vmware_connector` utilise réellement pyVmomi : `SmartConnect`, vues
`vim.HostSystem`/`vim.VirtualMachine` et `PerformanceManager`. La configuration
contient endpoint, utilisateur, TLS, timeout et `secret_ref`; le mot de passe est
lu depuis la variable nommée par `secret_ref`.

Hôtes : CPU, mémoire, stockage utilisé/libre, réseau reçu/transmis, uptime,
health, modèle, vendor et nombre de VM. VM : CPU, RAM, disque, réseau, uptime,
power state, hôte parent, guest et datastores. Les compteurs indisponibles restent
`null` : aucune valeur n'est inventée.

La découverte crée/met à jour `VirtualAsset` et `Machine`, puis normalise les
mesures avant PostgreSQL, règles, ML et dashboard. Les erreurs connexion/auth/TLS,
timeouts et ressources indisponibles sont enregistrées dans `CollectionRun` et le
connecteur. Celery applique retry/backoff.

Le test mock prouve l'orchestration et l'idempotence. Aucune donnée vCenter réelle
n'a été collectée dans cet environnement; lancer une collecte avec un compte
vSphere lecture seule pour obtenir la preuve propre à l'installation.

