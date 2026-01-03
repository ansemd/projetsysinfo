from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from decimal import Decimal
from .models import Destination, TypeService, Tarification, Expedition, Tournee, Client, Paiement
from django.db import transaction


# ========== SIGNAL 1 : Création automatique des tarifications ==========
@receiver(post_save, sender=Destination)
def creer_tarifications_automatiquement(sender, instance, created, **kwargs):
    """
    Dès qu'une nouvelle Destination est créée,
    on crée automatiquement ses tarifications pour chaque type de service
    
    LOGIQUE :
    - Si zone INTERNATIONALE → Créer tarif INTERNATIONAL uniquement
    - Sinon → Créer tarifs STANDARD et EXPRESS
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
@transaction.atomic
def gerer_suppression_expedition(sender, instance, **kwargs):
    """
    Signal appelé AVANT la suppression d'une expédition.
    Gère TOUTE la logique : validation + facture + solde + notification
    """
    from .models import Facture, Notification, Client
    from django.db.models import Sum
    from datetime import date
    
    # ========== VALIDATIONS ==========
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
    
    if instance.tournee and date.today() >= instance.tournee.date_depart.date():
        raise ValidationError(
            "Impossible d'annuler : la date de départ de la tournée est dépassée"
        )
    
    # ========== GESTION FACTURE + REMBOURSEMENT ==========
    
    if not instance.factures.exists():
        # Pas de facture → juste supprimer le tracking
        instance.suivis.all().delete()
        return  # Le delete() se fera automatiquement après le signal
    
    facture = instance.factures.filter(
        statut__in=['IMPAYEE', 'PARTIELLEMENT_PAYEE', 'PAYEE', 'EN_RETARD']
    ).first()
    
    if not facture:
        instance.suivis.all().delete()
        return
    
    # ========== CALCULS REMBOURSEMENT PROPORTIONNEL ==========
    
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
    
    # ========== MISE À JOUR SOLDE CLIENT ==========
    
    client = Client.objects.select_for_update().get(id=instance.client.id)
    
    # CRÉDIT CLIENT
    client.solde -= montant_paye_pour_exp
    client.solde -= montant_non_paye_pour_exp
    client.save()
    
    # ========== MISE À JOUR FACTURE ==========
    
    facture.expeditions.remove(instance)
    
    if facture.expeditions.count() == 0:
        # Plus d'expéditions → Annuler la facture
        for paiement in facture.paiements.filter(statut='VALIDE'):
            paiement.statut = 'ANNULE'
            paiement.save()
        
        facture.statut = 'ANNULEE'
        facture.montant_ht = Decimal('0.00')
        facture.montant_tva = Decimal('0.00')
        facture.montant_ttc = Decimal('0.00')
        facture.save()
    else:
        # Recalculer la facture
        from .utils import FacturationService
        FacturationService.calculer_montants_facture(facture)
        FacturationService.mettre_a_jour_statut_facture(facture)
    
    # Supprimer le tracking
    instance.suivis.all().delete()
    
    # ========== NOTIFICATION SI SOLDE NÉGATIF ==========
    
    if client.solde < 0:
        Notification.objects.create(
            type_notification='SOLDE_NEGATIF',
            titre=f"Client en crédit - {client.nom} {client.prenom}",
            message=f"Le client {client.nom} {client.prenom} a un solde de {client.solde} DA "
                    f"suite à l'annulation de l'expédition {instance.get_numero_expedition()}. "
                    f"Souhaitez-vous compenser sur la prochaine facture ou rembourser le client ?",
            client=client,
            statut='NON_LUE'
        )


# ========== SIGNAL 3 : Gestion suppression tournée ==========
@receiver(pre_delete, sender=Tournee)
def gerer_suppression_tournee(sender, instance, **kwargs):
    """
    RÔLE : GARDIEN + Libération des ressources
    
    Ce signal gère 2 choses :
    1. BLOQUER la suppression si tournée EN_COURS ou TERMINEE
    2. LIBÉRER les ressources (chauffeur + véhicule) si tournée PREVUE
    
    LOGIQUE :
    - Tournée EN_COURS ou TERMINEE → ❌ ERREUR, suppression bloquée
    - Tournée PREVUE → ✅ OK, on libère chauffeur et véhicule puis suppression
    """
    
    # Validation : Empêcher suppression si tournée en cours ou terminée
    if instance.statut in ['EN_COURS', 'TERMINEE']:
        raise ValidationError(
            f"Impossible de supprimer : la tournée est {instance.get_statut_display()}. "
            "Seules les tournées PREVUES peuvent être supprimées."
        )
    
    # Libération des ressources si tournée PREVUE
    if instance.statut == 'PREVUE':
        # Remettre le chauffeur DISPONIBLE
        instance.chauffeur.statut_disponibilite = 'DISPONIBLE'
        instance.chauffeur.save()
        
        # Remettre le véhicule DISPONIBLE
        instance.vehicule.statut = 'DISPONIBLE'
        instance.vehicule.save()
    
# ========== SIGNAL 4 : Gestion suppression paiement ==========
@receiver(pre_delete, sender=Paiement)
@transaction.atomic
def gerer_suppression_paiement(sender, instance, **kwargs):
    """
    Avant de supprimer un paiement :
    1. Remettre le montant dans le solde du client (annuler la diminution)
    2. Mettre à jour le statut de la facture
    """
    from .models import Paiement
    
    # Seulement si le paiement était VALIDE
    if instance.statut == 'VALIDE':
        # Lock le client pour éviter les race conditions
        client = Client.objects.select_for_update().get(id=instance.client.id)
        
        # ANNULER la diminution du solde (remettre la dette)
        client.solde += instance.montant_paye
        client.save()
        
        # Mettre à jour le statut de la facture après suppression
        from .utils import FacturationService
        FacturationService.mettre_a_jour_statut_facture(instance.facture)