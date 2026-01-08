from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from decimal import Decimal
from .models import Destination, TypeService, Tarification, Expedition, Tournee, Client, Paiement, Incident
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
        return
    
    facture = instance.factures.filter(
        statut__in=['IMPAYEE', 'PARTIELLEMENT_PAYEE', 'PAYEE', 'EN_RETARD']
    ).first()
    
    if not facture:
        instance.suivis.all().delete()
        return
    
    # ========== CALCULS POUR LE MONTANT DE L'EXPÉDITION ==========
    
    montant_exp_ht = instance.montant_total
    montant_exp_tva = montant_exp_ht * (facture.taux_tva / 100)
    montant_exp_ttc = montant_exp_ht + montant_exp_tva
    
    # ========== MISE À JOUR SOLDE CLIENT ==========
    
    client = Client.objects.select_for_update().get(id=instance.client.id)
    
    # ✅ LOGIQUE CORRECTE :
    # Quand on supprime une expédition, on retire toute sa contribution du solde
    # Si le client avait payé pour cette expédition, il sera crédité (solde négatif)
    # Exemple : solde = 1000.45 DA, expédition = 1100.45 DA, payé = 100 DA
    # Nouveau solde = 1000.45 - 1100.45 = -100 DA (crédit de 100 DA) ✅
    
    client.solde -= montant_exp_ttc
    client.save()
    
    # ========== MISE À JOUR FACTURE ==========
    
    facture.expeditions.remove(instance)
    
    if facture.expeditions.count() == 0:
        # Plus d'expéditions → Annuler la facture
        
        # ✅ Annuler les paiements (changer le statut uniquement, ne PAS les supprimer)
        # Cela permet de garder l'historique des paiements
        for paiement in facture.paiements.filter(statut='VALIDE'):
            paiement.statut = 'ANNULE'
            paiement.save()
        
        facture.statut = 'ANNULEE'
        facture.montant_ht = Decimal('0.00')
        facture.montant_tva = Decimal('0.00')
        facture.montant_ttc = Decimal('0.00')
        facture.save()
    else:
        # Recalculer la facture avec les expéditions restantes
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
            message=(
                f"Le client {client.nom} {client.prenom} a un crédit de "
                f"{abs(client.solde):,.2f} DA suite à l'annulation de l'expédition "
                f"{instance.get_numero_expedition()}.\n\n"
                "Un remboursement doit être effectué."
            ),
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

   # ======= SIGNAL POUR REMBOURSEMENT AUTOMATIQUE =======

# ======= SIGNAL POUR REMBOURSEMENT AUTOMATIQUE =======
@receiver(post_save, sender=Incident)
def appliquer_remboursement_automatique(sender, instance, created, **kwargs):
    """
    Signal déclenché à la CRÉATION d'un incident
    Crée une NOTIFICATION pour l'agent au lieu de rembourser automatiquement
    """
    if created:  # Seulement à la création
        from .utils import IncidentService
        
        # Vérifier si l'incident nécessite un remboursement
        if IncidentService.necessite_remboursement(instance):
            # CRÉER UNE NOTIFICATION au lieu de rembourser automatiquement
            from .models import Notification
            
            if not instance.expedition:
                return
            
            client = instance.expedition.client
            montant_ht = instance.expedition.montant_total
            montant_tva = montant_ht * Decimal('0.19')
            montant_ttc = montant_ht + montant_tva
            taux = instance.taux_remboursement
            montant_a_rembourser = montant_ttc * (taux / Decimal('100.00'))
            
            Notification.objects.create(
                type_notification='REMBOURSEMENT_REQUIS',
                titre=f"Remboursement requis - {client.nom} {client.prenom}",
                message=f"L'incident {instance.numero_incident} ({instance.get_type_incident_display()}) "
                        f"nécessite un remboursement de {montant_a_rembourser:,.2f} DA "
                        f"(taux: {taux}%) au client {client.nom} {client.prenom}.\n\n"
                        f"Expédition concernée: {instance.expedition.get_numero_expedition()}\n"
                        f"Montant original: {montant_ttc:,.2f} DA\n\n"
                        f"Cliquez sur 'Traiter' pour valider le remboursement.",
                client=client,
                statut='NON_LUE'
            )
            
            print(f"Notification de remboursement créée pour incident {instance.numero_incident}")

# ========== SIGNAL 5 : Notification kilométrage tournée terminée ==========
@receiver(post_save, sender=Tournee)
def notifier_tournee_terminee(sender, instance, created, **kwargs):
    """
    Quand une tournée passe à TERMINEE, créer une notification
    pour demander le kilométrage d'arrivée
    """
    if not created:  # Seulement lors d'une modification
        from .models import Notification
        
        # Vérifier si la tournée vient de passer à TERMINEE
        if instance.statut == 'TERMINEE':
            # Vérifier si le kilométrage d'arrivée n'est pas déjà renseigné
            if not instance.kilometrage_arrivee:
                # Créer une notification
                Notification.objects.get_or_create(
                    type_notification='TOURNEE_TERMINEE',
                    tournee=instance,
                    statut='NON_LUE',
                    defaults={
                        'titre': f"Tournée terminée - {instance.get_numero_tournee()}",
                        'message': (
                            f"La tournée {instance.get_numero_tournee()} est terminée.\n\n"
                            f"Chauffeur : {instance.chauffeur.prenom} {instance.chauffeur.nom}\n"
                            f"Véhicule : {instance.vehicule.numero_immatriculation}\n"
                            f"Kilométrage départ : {instance.kilometrage_depart} km\n\n"
                            f"Veuillez renseigner le kilométrage d'arrivée pour finaliser la tournée."
                        ),
                        'vehicule': instance.vehicule,
                    }
                )