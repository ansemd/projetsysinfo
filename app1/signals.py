from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from decimal import Decimal
from .models import Destination, TypeService, Tarification, Expedition, Tournee


# ========== SIGNAL 1 : Création automatique des tarifications ==========
@receiver(post_save, sender=Destination)
def creer_tarifications_automatiquement(sender, instance, created, **kwargs):
    """
    Dès qu'une nouvelle Destination est créée,
    on crée automatiquement ses tarifications
    """
    if created:
        if instance.zone_geographique == 'INTERNATIONALE':
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


# ========== SIGNAL 2 : Validation suppression expédition ==========
@receiver(pre_delete, sender=Expedition)
def valider_suppression_expedition(sender, instance, **kwargs):
    """
    Empêcher la suppression d'expéditions en cours ou livrées
    """
    if instance.statut in ['EN_TRANSIT', 'LIVRE']:
        raise ValidationError(
            f"Impossible de supprimer : l'expédition est {instance.get_statut_display()}. "
            "Seules les expéditions EN_ATTENTE ou COLIS_CREE peuvent être supprimées."
        )
    
    if instance.tournee and instance.tournee.statut != 'PREVUE':
        raise ValidationError(
            f"Impossible de supprimer : la tournée est {instance.tournee.get_statut_display()}. "
            "Seules les expéditions de tournées PREVUES peuvent être supprimées."
        )


# ========== SIGNAL 3 : Gestion suppression expédition (facture) ==========
@receiver(pre_delete, sender=Expedition)
def gerer_suppression_expedition(sender, instance, **kwargs):
    """
    Signal appelé AVANT la suppression d'une expédition.
    Gère l'annulation et la mise à jour de la facture.
    """
    if instance.factures.exists():
        from .utils import FacturationService
        from django.db.models import Sum
        
        facture = instance.factures.filter(
            statut__in=['IMPAYEE', 'PARTIELLEMENT_PAYEE', 'PAYEE', 'EN_RETARD']
        ).first()
        
        if facture:
            montant_exp_ht = instance.montant_total
            montant_exp_tva = montant_exp_ht * (facture.taux_tva / 100)
            montant_exp_ttc = montant_exp_ht + montant_exp_tva
            
            total_paye_facture = facture.paiements.filter(statut='VALIDE').aggregate(
                total=Sum('montant_paye')
            )['total'] or Decimal('0.00')
            
            if facture.montant_ttc > 0:
                proportion_payee = total_paye_facture / facture.montant_ttc
            else:
                proportion_payee = Decimal('0.00')
            
            montant_paye_pour_exp = montant_exp_ttc * proportion_payee
            montant_non_paye_pour_exp = montant_exp_ttc - montant_paye_pour_exp
            
            instance.client.solde -= montant_paye_pour_exp
            instance.client.solde -= montant_non_paye_pour_exp
            instance.client.save()
            
            facture.expeditions.remove(instance)
            
            if facture.expeditions.count() == 0:
                for paiement in facture.paiements.filter(statut='VALIDE'):
                    paiement.statut = 'ANNULE'
                    paiement.save()
                
                facture.statut = 'ANNULEE'
                facture.montant_ht = Decimal('0.00')
                facture.montant_tva = Decimal('0.00')
                facture.montant_ttc = Decimal('0.00')
                facture.save()
            else:
                FacturationService.calculer_montants_facture(facture)
                FacturationService.mettre_a_jour_statut_facture(facture)
            
            instance.suivis.all().delete()


# ========== SIGNAL 4 : Gestion suppression tournée ==========
@receiver(pre_delete, sender=Tournee)
def gerer_suppression_tournee(sender, instance, **kwargs):
    """
    Empêcher la suppression de tournées en cours/terminées
    ET remettre chauffeur/véhicule à DISPONIBLE si tournée PREVUE
    """
    if instance.statut in ['EN_COURS', 'TERMINEE']:
        raise ValidationError(
            f"Impossible de supprimer : la tournée est {instance.get_statut_display()}. "
            "Seules les tournées PREVUES peuvent être supprimées."
        )
    
    if instance.statut == 'PREVUE':
        instance.chauffeur.statut_disponibilite = 'DISPONIBLE'
        instance.chauffeur.save()
        
        instance.vehicule.statut = 'DISPONIBLE'
        instance.vehicule.save()