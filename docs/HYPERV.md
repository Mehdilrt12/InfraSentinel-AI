# Intégration Hyper-V

## Outils réellement utilisés

- PowerShell non interactif.
- Module Hyper-V : `Get-VM`, `Get-VMHardDiskDrive`, `Get-VHD`,
  `Get-VMNetworkAdapterStatistics`.
- CIM/WMI : `Win32_OperatingSystem`, `Win32_LogicalDisk`.
- Performance Counters : Processor et Network Interface.
- PowerShell Remoting/WinRM pour un host distant.

Toutes les commandes se trouvent uniquement dans
`hyperv_connector/scripts/collect.ps1`; le code métier Python ne contient aucune
commande PowerShell dispersée. Le secret distant est injecté temporairement dans
l'environnement du processus et n'apparaît pas dans la ligne de commande.

Hôte : CPU, RAM, disque, réseau, uptime, VM count et disponibilité. VM : état,
CPU, RAM, disque VHD, réseau, uptime et host. Les résultats JSON sont normalisés,
historisés et transmis aux règles/ML. Timeout, retour non nul, JSON invalide et
permissions insuffisantes déclenchent un état d'échec et retry Celery.

Le poste de revue dispose de PowerShell, du module Hyper-V et du service VMMS. Une
collecte réelle a été tentée contre l'hôte local `LEGION`; `Get-VM` a refusé
l'accès faute de permissions Hyper-V. Aucune métrique réelle n'a donc été validée.
La tâche ciblée est routée vers la queue `hyperv`, qui doit être consommée sur
Windows; le worker Docker Linux ne consomme volontairement pas cette queue.

`NOT TESTED — REAL HYPER-V ENVIRONMENT REQUIRED`
