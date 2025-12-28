from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from decimal import Decimal
from .models import Destination, TypeService, Tarification, Expedition


@receiver(post_save, sender=Destination)
def creer_tarifications_automatiquement(sender, instance, created, **kwargs):
    """
    Dès qu'une nouvelle Destination est créée,
    on crée automatiquement ses tarifications
    """
    
    # Seulement si c'est une NOUVELLE destination (pas une modification)
    if created:
        
        if instance.zone_geographique == 'INTERNATIONALE':
            # Destination internationale → INTERNATIONAL uniquement
            international = TypeService.objects.get(type_service='INTERNATIONAL')
            Tarification.objects.get_or_create(
                destination=instance,
                type_service=international,
                defaults={
                    'tarif_poids': 25.00,
                    'tarif_volume': 50.00
                }
            )
        
        else:
            # Destination nationale → STANDARD et EXPRESS
            standard = TypeService.objects.get(type_service='STANDARD')
            express = TypeService.objects.get(type_service='EXPRESS')
            
            Tarification.objects.get_or_create(
                destination=instance,
                type_service=standard,
                defaults={
                    'tarif_poids': 10.00,
                    'tarif_volume': 20.00
                }
            )
            
            Tarification.objects.get_or_create(
                destination=instance,
                type_service=express,
                defaults={
                    'tarif_poids': 10.00,
                    'tarif_volume': 20.00
                }
            )


@receiver(pre_delete, sender=Expedition)
def gerer_suppression_expedition(sender, instance, **kwargs):
    """
    Signal appelé AVANT la suppression d'une expédition.
    Gère l'annulation et la mise à jour de la facture.
    """
    # Si l'expédition a une facture, gérer l'annulation
    if instance.factures.exists():
        from .utils import FacturationService
        from django.db.models import Sum
        
        facture = instance.factures.filter(
            statut__in=['IMPAYEE', 'PARTIELLEMENT_PAYEE', 'PAYEE', 'EN_RETARD']
        ).first()
        
        if facture:
            # Calculer le montant TTC de cette expédition
            montant_exp_ht = instance.montant_total
            montant_exp_tva = montant_exp_ht * (facture.taux_tva / 100)
            montant_exp_ttc = montant_exp_ht + montant_exp_tva
            
            # Calculer le total payé pour la facture
            total_paye_facture = facture.paiements.filter(statut='VALIDE').aggregate(
                total=Sum('montant_paye')
            )['total'] or Decimal('0.00')
            
            # Calcul proportionnel
            if facture.montant_ttc > 0:
                proportion_payee = total_paye_facture / facture.montant_ttc
            else:
                proportion_payee = Decimal('0.00')
            
            montant_paye_pour_exp = montant_exp_ttc * proportion_payee
            montant_non_paye_pour_exp = montant_exp_ttc - montant_paye_pour_exp
            
            # Rembourser le client
            instance.client.solde -= montant_paye_pour_exp
            instance.client.solde -= montant_non_paye_pour_exp
            instance.client.save()
            
            # Retirer l'expédition de la facture
            facture.expeditions.remove(instance)
            
            # Recalculer la facture
            if facture.expeditions.count() == 0:
                # Facture vide → Annuler
                for paiement in facture.paiements.filter(statut='VALIDE'):
                    paiement.statut = 'ANNULE'
                    paiement.save()
                
                facture.statut = 'ANNULEE'
                facture.montant_ht = Decimal('0.00')
                facture.montant_tva = Decimal('0.00')
                facture.montant_ttc = Decimal('0.00')
                facture.save()
            else:
                # Recalculer les montants
                FacturationService.calculer_montants_facture(facture)
                FacturationService.mettre_a_jour_statut_facture(facture)
            
            # Supprimer les trackings
            instance.suivis.all().delete()