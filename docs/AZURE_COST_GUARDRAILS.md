# Garde-fous de coût Azure for Students

**Crédit observé :** 100 USD disponibles sur 100 USD
**Coût observé avant provisionnement :** 0,00 USD
**Objectif :** aucun débit personnel et consommation de staging inférieure à 20 USD

## Règles non négociables

1. ne jamais convertir l'abonnement en Pay-As-You-Go ;
2. ne jamais ajouter ou modifier un moyen de paiement ;
3. ne créer aucune ressource dont le prix n'est pas visible ou calculable ;
4. ne pas utiliser GPU, base managée, Redis managé, réservation ou Savings Plan ;
5. créer un budget d'alerte avant la VM ;
6. conserver une marge minimale de 80 USD après le staging cible ;
7. arrêter en cas d'écart entre le coût estimé et le portail ;
8. supprimer le groupe de ressources au plus tard après 72 heures.

## Estimation initiale

Le portail a affiché pour `Standard_B2ms` en France Central : 2 vCPU, 8 Gio et **68,91 USD/mois**, hors disque et autres services. Le SKU était alors dans « Size not available » parce que `Microsoft.Compute` n'était pas enregistré ; cette valeur sert uniquement d'ordre de grandeur.

Avec l'hypothèse Azure usuelle de 730 heures par mois :

| Poste | Hypothèse | Estimation 72 h | Statut |
|---|---:|---:|---|
| Compute B2ms | 68,91 USD/mois | 6,80 USD | prix portail observé, capacité non confirmée |
| Disque OS | Standard SSD, taille minimale compatible | à relever dans le récapitulatif Azure | NOT VERIFIED |
| IP publique | SKU compatible, avec nom DNS | à relever dans le récapitulatif Azure | NOT VERIFIED |
| Trafic sortant | démonstration limitée | à surveiller | NOT VERIFIED |
| PostgreSQL/Redis | conteneurs sur VM | 0 USD additionnel | inclus compute/disque |
| Caddy/Let's Encrypt | logiciels gratuits | 0 USD | PASS |

**Plafond de décision :** ne pas créer la VM si le coût total projeté sur 72 heures dépasse 20 USD ou si le crédit restant projeté devient inférieur à 80 USD.

## Budget et alertes

Budget recommandé : 20 USD pour le groupe de ressources ou l'abonnement, avec alertes à 50 %, 75 %, 90 % et 100 %. Un budget Azure n'arrête pas les ressources : les contrôles manuels et la suppression planifiée restent obligatoires.

La création d'une alerte envoyée à une adresse email constitue une inscription à une notification. Elle doit être effectuée seulement après confirmation de l'adresse destinataire dans le portail.

## Relevé quotidien

Consigner dans le rapport final :

- crédit restant ;
- coût réel et forecast ;
- ressources facturables encore présentes ;
- état VM (running/deallocated) ;
- coût du disque et de l'IP ;
- heure prévue de suppression.

## Arrêt et suppression

`Stop` dans le système invité n'est pas une preuve de désallocation. Vérifier l'état `Stopped (deallocated)` dans Azure. Même désalloués, disques et certaines IP peuvent rester facturés. Après export et test de restauration, supprimer le groupe `rg-infrasentinel-pfe-staging` puis vérifier « All resources » et Cost Management.

## Statut actuel

**NO COST INCURRED BY THIS PLAN — NO AZURE RESOURCE CREATED YET.** L'estimation complète reste à finaliser dans l'écran de revue Azure avant toute création.
