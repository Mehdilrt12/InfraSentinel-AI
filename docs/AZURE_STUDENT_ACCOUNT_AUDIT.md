# Audit du compte Azure for Students

**Date d'observation :** 27 août 2026
**Méthode :** portail Azure, lecture seule
**Identifiants :** volontairement masqués ; aucun identifiant complet d'abonnement ou de tenant n'est enregistré dans Git

## État observé

| Contrôle | Résultat | Statut |
|---|---|---|
| Offre | Azure for Students / Azure Plan | PASS |
| État de l'abonnement | Active | PASS |
| Rôle de l'utilisateur | Owner | PASS fonctionnel / HIGH privilège |
| MFA | active | PASS |
| Crédit disponible | 100 USD sur 100 USD | PASS |
| Coût août 2026 | 0,00 USD | PASS à l'instant du contrôle |
| Expiration affichée | 26 août 2027 | PASS |
| Durée restante affichée | 365 jours | PASS |
| Ressources existantes | 0 | PASS — aucun périmètre tiers à modifier |
| Services gratuits | 58 non utilisés, 0 utilisé/dépassé | INFORMATION |
| Provider Compute | non enregistré | BLOCKER technique initial |
| Quotas VM | aucune donnée exploitable avant enregistrement du provider | NOT VERIFIED |
| Defender for Cloud | non activé | INFORMATION — option payante non activée |

## Contraintes de sécurité financière

- ne jamais sélectionner une mise à niveau Pay-As-You-Go ;
- ne jamais ajouter ou modifier un moyen de paiement dans le cadre de ce déploiement ;
- ne jamais créer de réservation, Savings Plan, GPU ou service managé non chiffré ;
- arrêter le provisionnement si le coût total n'est plus couvert par le crédit visible ;
- considérer le budget Azure comme une alerte, pas comme une limite technique de dépense ;
- vérifier Cost Management après chaque création et au moins quotidiennement pendant le staging ;
- supprimer le groupe de ressources de staging au plus tard 72 heures après sa création, sauf décision explicite ultérieure.

## Providers requis

L'architecture mono-VM requiert normalement :

- `Microsoft.Compute` pour la VM et le disque ;
- `Microsoft.Network` pour le réseau virtuel, le NSG et l'IP publique ;
- `Microsoft.Storage` seulement si un stockage ou une destination de sauvegarde Azure est ajouté.

L'enregistrement d'un provider ne crée pas de ressource facturable. Il doit néanmoins être tracé, puis les quotas et tailles réellement disponibles doivent être revérifiés avant toute VM.

## Risques

### CRITICAL

- passage volontaire vers une offre payante ou ajout d'un moyen de paiement ; cette action est hors périmètre et interdite sans nouvelle autorisation explicite.

### HIGH

- rôle Owner très large ; aucun second principal ne doit être ajouté sans besoin démontré ;
- quota Compute inconnu ; une taille visible dans le catalogue n'est pas une preuve de disponibilité ;
- le crédit de 100 USD ne permet pas de laisser une VM 8 Gio active toute l'année.

### MEDIUM

- coût du disque et de l'IP pouvant continuer après arrêt ou désallocation de la VM ;
- alertes budgétaires informatives seulement ;
- services de sécurité avancés potentiellement payants et non nécessaires à ce staging.

## Verdict

**ACCOUNT ELIGIBLE, ZERO CURRENT COST, QUOTA NOT YET VERIFIED.** Le compte permet un staging temporaire couvert par crédit, sous réserve de disponibilité réelle du SKU et de contrôle du coût complet avant création.
