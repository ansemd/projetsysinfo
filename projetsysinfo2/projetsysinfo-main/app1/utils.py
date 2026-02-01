from datetime import datetime, timedelta
from datetime import date
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Sum
from django.db import transaction
from .models import Chauffeur, Vehicule


class TourneeService:
    """
    Service gérant toutes les opérations liées aux tournées :
    - Validation disponibilité chauffeur/véhicule
    - Calculs kilométrage et consommation
    - Gestion des statuts (ressources + expéditions)
    """
    
    @staticmethod
    def traiter_tournee(tournee):
        """
        Point d'entrée principal pour gérer toute la logique d'une tournée
        Appelé automatiquement par le signal post_save de Tournee
        """

        if tournee.pk is None:
            TourneeService.verifier_disponibilite(tournee)
        
        if tournee.pk is None and not tournee.kilometrage_depart:
            tournee.kilometrage_depart = tournee.vehicule.kilometrage

        if tournee.kilometrage_arrivee and tournee.kilometrage_depart:
            TourneeService.calculer_kilometrage_et_consommation(tournee)

        TourneeService.gerer_statuts_ressources(tournee)
        
        if tournee.statut == 'PREVUE' and timezone.now() >= tournee.date_depart:
            tournee.statut = 'EN_COURS'

    @staticmethod
    @transaction.atomic
    def verifier_disponibilite(tournee):
        """
        Vérifie que chauffeur ET véhicule sont DISPONIBLES
        """
        chauffeur = Chauffeur.objects.select_for_update().get(id=tournee.chauffeur.id)
        vehicule = Vehicule.objects.select_for_update().get(id=tournee.vehicule.id)
        
        if chauffeur.statut_disponibilite != 'DISPONIBLE':
            raise ValidationError(f"Chauffeur {chauffeur} non disponible")
        
        if vehicule.statut != 'DISPONIBLE':
            raise ValidationError(f"Véhicule {vehicule.numero_immatriculation} non disponible")
    
    @staticmethod
    def calculer_kilometrage_et_consommation(tournee):
        """
        Calcule le kilométrage parcouru et la consommation de carburant
        Formule : Consommation = (km parcouru × conso moyenne) / 100
        """
        tournee.kilometrage_parcouru = tournee.kilometrage_arrivee - tournee.kilometrage_depart
        
        if tournee.kilometrage_parcouru > 0:
            tournee.consommation_carburant = (
                Decimal(str(tournee.kilometrage_parcouru)) * 
                tournee.vehicule.consommation_moyenne / 100
            )
    
    @staticmethod
    def gerer_statuts_ressources(tournee):
        """
        Gère les statuts automatiques selon l'état de la tournée
        """
        
        if tournee.statut in ['PREVUE', 'EN_COURS']:
            tournee.chauffeur.statut_disponibilite = 'EN_TOURNEE'
            tournee.vehicule.statut = 'EN_TOURNEE'

            if tournee.statut == 'EN_COURS':
                from .models import TrackingExpedition
                for exp in tournee.expeditions.all():
                    if exp.statut != 'EN_TRANSIT':
                        exp.statut = 'EN_TRANSIT'
                        exp.save(update_fields=['statut'])

                        TrackingService.creer_suivi(
                            exp,
                            'EN_TRANSIT',
                            f"Colis en transit vers {exp.destination.ville}"
                        )

                        ExpeditionService.envoyer_notification_destinataire(exp)
        
        elif tournee.statut == 'TERMINEE':
            tournee.chauffeur.statut_disponibilite = 'DISPONIBLE'
            tournee.vehicule.statut = 'DISPONIBLE'

            if tournee.kilometrage_arrivee:
                tournee.vehicule.kilometrage = tournee.kilometrage_arrivee

            from .models import TrackingExpedition
            expeditions_a_livrer = tournee.expeditions.filter(statut='EN_TRANSIT') 
            for exp in expeditions_a_livrer:
                if exp.statut == 'EN_TRANSIT':
                    exp.statut = 'LIVRE'
                    exp.date_livraison_reelle = timezone.now().date()
                    exp.save(update_fields=['statut', 'date_livraison_reelle'])
                    
                    # Créer suivi de tracking
                    TrackingService.creer_suivi(
                        exp,
                        'LIVRE',
                        f"Colis livré à {exp.nom_destinataire}"
                    )
        
        tournee.chauffeur.save()
        tournee.vehicule.save()

    @staticmethod
    def peut_demarrer(tournee):
        """
        Vérifie si une tournée peut démarrer (utilisé par taches_quotidiennes)
        """
        if not tournee.expeditions.exists():
            return False, "Aucune expédition affectée"
        
        return True, ""

class ExpeditionService:
    """
    Service gérant les opérations sur les expéditions :
    - Validation et calculs de montants
    - Affectation intelligente de tournées
    - Annulation d'expédition avec remboursement proportionnel
    """
    
    @staticmethod
    def valider_expedition(expedition):
        """
        Valide tous les champs avant création/modification
        """
        if expedition.poids <= 0:
            raise ValidationError({'poids': "Le poids doit être supérieur à 0"})

        if expedition.pk:
            from .models import Expedition, Incident
            ancienne = Expedition.objects.get(pk=expedition.pk)
            if ancienne.tournee and ancienne.tournee.statut != 'PREVUE':
                a_incident_actif = Incident.objects.filter(
                    expedition=ancienne,
                ).exists()

            if not a_incident_actif:
                raise ValidationError(
                    "Impossible de modifier : la tournée est déjà en cours ou terminée. "
                )
    
    @staticmethod
    def calculer_montant(expedition):
        """
        Calcule le montant total via la Tarification
        Formule : Montant = Tarif_base + (Poids × Tarif_poids) + (Volume × Tarif_volume)
        """
        from .models import Tarification
        
        tarif = Tarification.objects.filter(
            destination=expedition.destination,
            type_service=expedition.type_service
        ).first()
        
        if tarif:
            volume = expedition.volume or 0
            expedition.montant_total = tarif.calculer_prix(
                expedition.poids,
                volume
            )
        else:
            raise ValidationError("Aucune tarification trouvée pour cette combinaison destination/service")
    
    @staticmethod
    def affecter_tournee_intelligente(expedition):
        """
        Cherche une tournée compatible EXISTANTE ou en crée une nouvelle
        """
        from .models import Tournee
        from django.db.models import Sum

        if expedition.type_service.type_service == 'EXPRESS':
            ExpeditionService.creer_tournee_express(expedition)
            return

        tournees_compatibles = Tournee.objects.filter(
            zone_cible=expedition.destination.zone_logistique,
            statut='PREVUE',
            est_privee=False,
            date_depart__gte=timezone.now()
        ).order_by('date_depart')
        
        for tournee in tournees_compatibles:
            totaux = tournee.expeditions.aggregate(poids_total=Sum('poids'))
            poids_actuel = totaux['poids_total'] or 0 

            if float(poids_actuel) + float(expedition.poids) <= float(tournee.vehicule.capacite_poids):
                expedition.tournee = tournee
                expedition.save()
                return

        ExpeditionService.creer_nouvelle_tournee(expedition)
    
    @staticmethod
    def creer_nouvelle_tournee(expedition):
        """
        Crée une nouvelle tournée PARTAGÉE pour l'expédition STANDARD
        """
        from .models import Tournee, Chauffeur, Vehicule
        
        chauffeur = Chauffeur.objects.filter(statut_disponibilite='DISPONIBLE').first()
        vehicule = Vehicule.objects.filter(statut='DISPONIBLE').first()
        
        if not chauffeur or not vehicule:
            raise ValidationError(
                "⚠️ Aucune tournée compatible et aucun chauffeur/véhicule disponible. "
                "L'expédition sera créée sans tournée. Veuillez l'affecter manuellement plus tard."
            )
        
        zone = expedition.destination.zone_logistique
        if zone == 'CENTRE':
            jours_delai = 1
        elif zone in ['EST', 'OUEST']:
            jours_delai = 2
        elif zone == 'SUD':
            jours_delai = 3
        else:
            jours_delai = 1

        date_depart = timezone.now() + timedelta(days=jours_delai)
        date_depart = date_depart.replace(hour=9, minute=0, second=0)
        
        tournee = Tournee.objects.create(
            chauffeur=chauffeur,
            vehicule=vehicule,
            date_depart=date_depart,
            zone_cible=expedition.destination.zone_logistique,
            statut='PREVUE'
        )
        
        expedition.tournee = tournee
        expedition.save()
    
    @staticmethod
    def creer_tournee_express(expedition):
        """
        Crée une tournée PRIVÉE (dédiée) pour une expédition EXPRESS
        """
        from .models import Tournee, Chauffeur, Vehicule
        
        chauffeur = Chauffeur.objects.filter(statut_disponibilite='DISPONIBLE').first()
        vehicule = Vehicule.objects.filter(statut='DISPONIBLE').first()
        
        if not chauffeur or not vehicule:
            raise ValidationError(
                "Aucun chauffeur ou véhicule disponible pour une expédition EXPRESS. "
                "Veuillez attendre ou passer en STANDARD."
            )

        maintenant = timezone.now()
        if maintenant.hour < 14:
            date_depart = maintenant + timedelta(hours=1)
        else:
            date_depart = maintenant + timedelta(days=1)
            date_depart = date_depart.replace(hour=8, minute=0, second=0)
        
        tournee = Tournee.objects.create(
            chauffeur=chauffeur,
            vehicule=vehicule,
            date_depart=date_depart,
            zone_cible=expedition.destination.zone_logistique,
            est_privee=True,
            remarques=f"Tournée privée EXPRESS vers {expedition.destination.ville}, {expedition.destination.wilaya}",
            statut='PREVUE'
        )
        
        expedition.tournee = tournee
        expedition.save()
    
    @staticmethod
    def calculer_date_livraison(expedition):
        """
        Calcule la date de livraison prévue selon le délai du service
        """
        from .models import Tarification
        
        tarif = Tarification.objects.filter(
            destination=expedition.destination,
            type_service=expedition.type_service
        ).first()
        
        if tarif:
            delai_jours = int(tarif.calculer_delai())
            expedition.date_livraison_prevue = (
                expedition.tournee.date_depart.date() + timedelta(days=delai_jours)
            )
    
    
    @staticmethod
    def envoyer_notification_destinataire(expedition):
        """
        Envoie un email/SMS au destinataire quand sa tournée démarre
        """
        from .notification import ExpeditionEmailService

        ExpeditionEmailService.envoyer_notification_colis_en_route(expedition)

class VehiculeService:
    """
    Service pour gérer les maintenances automatiques des véhicules
    """
    
    @staticmethod
    def verifier_vehicule_libre(vehicule):
        """
        Vérifie si un véhicule n'a pas de tournée EN_COURS ou PREVUE
        """
        from .models import Tournee
        
        tournees_actives = Tournee.objects.filter(
            vehicule=vehicule,
            statut__in=['PREVUE', 'EN_COURS']
        )
        
        return not tournees_actives.exists()
    
    @staticmethod
    def gerer_revision(vehicule):
        """
        Initialise la date de prochaine révision si nécessaire
        """
        if vehicule.date_derniere_revision and not vehicule.date_prochaine_revision:
            vehicule.date_prochaine_revision = vehicule.date_derniere_revision + timedelta(days=180)
    
    @staticmethod
    def confirmer_revision(vehicule):
        """
        Confirme qu'une révision a été effectuée (appelé depuis notification)

        - DPR devient DDR
        - Nouvelle DPR = DDR + 180 jours
        - Véhicule passe DISPONIBLE
        """
        vehicule.date_derniere_revision = vehicule.date_prochaine_revision

        vehicule.date_prochaine_revision = vehicule.date_derniere_revision + timedelta(days=180)

        vehicule.statut = 'DISPONIBLE'
        vehicule.save()
    
    @staticmethod
    def reporter_revision(vehicule, nouvelle_date):
        """
        Agent modifie manuellement la date de prochaine révision
        """
        vehicule.date_prochaine_revision = nouvelle_date
        vehicule.save()
    
    @staticmethod
    def gerer_maintenance_veille_soir():

        from datetime import date, timedelta
        from .models import Vehicule, Notification
        
        demain = date.today() + timedelta(days=1)

        vehicules_maintenance_demain = Vehicule.objects.filter(
            date_prochaine_revision=demain
        )
        
        stats = {
            'notifications_vehicule_en_tournee': 0,
            'notifications_confirmation': 0,
        }
        
        for vehicule in vehicules_maintenance_demain:

            if not VehiculeService.verifier_vehicule_libre(vehicule):
                Notification.objects.create(
                    type_notification='MAINTENANCE_AVANT',
                    titre=f"Véhicule en tournée - {vehicule.numero_immatriculation}",
                    message=f"Le véhicule {vehicule.numero_immatriculation} est actuellement en tournée "
                            f"mais a une maintenance prévue demain ({vehicule.date_prochaine_revision.strftime('%d/%m/%Y')}). "
                            f"Voulez-vous modifier la date de prochaine révision ?",
                    vehicule=vehicule,
                    statut='NON_LUE'
                )
                stats['notifications_vehicule_en_tournee'] += 1
                
            else:
                Notification.objects.create(
                    type_notification='MAINTENANCE_AVANT',
                    titre=f"Confirmation maintenance - {vehicule.numero_immatriculation}",
                    message=f"Le véhicule {vehicule.numero_immatriculation} ({vehicule.marque} {vehicule.modele}) "
                            f"a une maintenance prévue demain ({vehicule.date_prochaine_revision.strftime('%d/%m/%Y')}). "
                            f"Confirmez-vous que le véhicule ira en maintenance demain ?",
                    vehicule=vehicule,
                    statut='NON_LUE'
                )
                stats['notifications_confirmation'] += 1
        
        return stats
    
    @staticmethod
    def gerer_retour_maintenance_matin():

        from datetime import date
        from .models import Vehicule, Notification

        vehicules_en_maintenance = Vehicule.objects.filter(
            statut='EN_MAINTENANCE',
            date_prochaine_revision__lt=date.today()
        )
        
        stats = {
            'notifications_retour': 0,
        }
        
        for vehicule in vehicules_en_maintenance:

            notif_existante = Notification.objects.filter(
                vehicule=vehicule,
                type_notification='MAINTENANCE_APRES',
                statut__in=['NON_LUE', 'LUE']
            ).exists()

            if not notif_existante:
                Notification.objects.create(
                    type_notification='MAINTENANCE_APRES',
                    titre=f"Retour de maintenance - {vehicule.numero_immatriculation}",
                    message=f"Le véhicule {vehicule.numero_immatriculation} ({vehicule.marque} {vehicule.modele}) "
                            f"est en maintenance depuis le {vehicule.date_prochaine_revision.strftime('%d/%m/%Y')}. "
                            f"Est-il revenu de maintenance ?",
                    vehicule=vehicule,
                    statut='NON_LUE'
                )
                stats['notifications_retour'] += 1
        
        return stats

class TrackingService:
    """
    Service pour gérer le suivi (tracking) des expéditions
    """
    
    @staticmethod
    def creer_suivi(expedition, statut_etape, commentaire=None):
        """
        Crée une nouvelle étape de suivi pour une expédition
        """
        from .models import TrackingExpedition
        
        TrackingExpedition.objects.create(
            expedition=expedition,
            statut_etape=statut_etape,
            commentaire=commentaire
        )

class FacturationService:
    """
    Service gérant toutes les opérations liées à la facturation :
    - Calcul des montants (HT, TVA, TTC)
    - Création et mise à jour des factures
    - Gestion des paiements
    - Compensation solde négatif
    - Annulation de factures
    """
    
    @staticmethod
    def calculer_montants_facture(facture):

        from django.db.models import Sum

        montant_ht = facture.expeditions.aggregate(
            total=Sum('montant_total')
        )['total'] or Decimal('0.00')

        montant_tva = montant_ht * (facture.taux_tva / 100)

        montant_ttc = montant_ht + montant_tva

        facture.montant_ht = montant_ht
        facture.montant_tva = montant_tva
        facture.montant_ttc = montant_ttc
        facture.save()
        
        return facture
    
    @staticmethod
    def calculer_montant_restant(facture):
        from django.db.models import Sum
        
        total_paye = facture.paiements.filter(statut='VALIDE').aggregate(
            total=Sum('montant_paye')
        )['total'] or Decimal('0.00')
        
        return facture.montant_ttc - total_paye
    
    @staticmethod
    def mettre_a_jour_statut_facture(facture):
        from datetime import date

        if facture.statut == 'ANNULEE':
            return
        
        montant_restant = FacturationService.calculer_montant_restant(facture)

        if montant_restant <= 0:
            facture.statut = 'PAYEE'

        elif montant_restant < facture.montant_ttc:
            if date.today() > facture.date_echeance:
                facture.statut = 'EN_RETARD'
            else:
                facture.statut = 'PARTIELLEMENT_PAYEE'

        else:
            if date.today() > facture.date_echeance:
                facture.statut = 'EN_RETARD'
            else:
                facture.statut = 'IMPAYEE'
        
        facture.save()
    
    @staticmethod
    def gerer_facture_expedition(expedition, created_by=None):

        from datetime import date, timedelta
        from .models import Facture
        
        client = expedition.client
        aujourd_hui = date.today()

        if expedition.factures.exists():
            return expedition.factures.first()

        facture_du_jour = Facture.objects.filter(
            client=client,
            date_creation__date=aujourd_hui,
            statut__in=['IMPAYEE', 'PARTIELLEMENT_PAYEE']
        ).first()
        
        if facture_du_jour:
            facture_du_jour.expeditions.add(expedition)

            FacturationService.calculer_montants_facture(facture_du_jour)

            montant_exp_tva = expedition.montant_total * (facture_du_jour.taux_tva / 100)
            montant_exp_ttc = expedition.montant_total + montant_exp_tva

            client.solde += montant_exp_ttc
            client.save()

            FacturationService.mettre_a_jour_statut_facture(facture_du_jour)
            
            return facture_du_jour
        
        else:
            facture = Facture.objects.create(
                client=client,
                cree_par=created_by,
                date_echeance=aujourd_hui + timedelta(days=60),
                statut='IMPAYEE',
                taux_tva=Decimal('19.00')
            )

            facture.expeditions.add(expedition)

            FacturationService.calculer_montants_facture(facture)

            client.solde += facture.montant_ttc
            client.save()
            
            return facture

    @staticmethod
    def enregistrer_paiement(facture, montant, mode_paiement, reference=None, remarques=None):

        from .models import Paiement
        
        # Validations
        if facture.statut == 'ANNULEE':
            raise ValidationError("Impossible de payer une facture annulée")
        
        if facture.statut == 'PAYEE':
            raise ValidationError("Cette facture est déjà entièrement payée")
        
        montant_restant = FacturationService.calculer_montant_restant(facture)
        
        if montant_restant <= 0:
            raise ValidationError("Cette facture est déjà entièrement payée")
        
        if montant > montant_restant:
            raise ValidationError(
                f"Le montant ({montant} DA) dépasse le montant restant ({montant_restant} DA)"
            )
        
        if montant <= 0:
            raise ValidationError("Le montant doit être supérieur à 0")

        paiement = Paiement.objects.create(
            facture=facture,
            client=facture.client,
            montant_paye=montant,
            mode_paiement=mode_paiement,
            reference_transaction=reference,
            remarques=remarques,
            statut='VALIDE'
        )

        facture.client.solde -= montant
        facture.client.save()

        FacturationService.mettre_a_jour_statut_facture(facture)
        
        return paiement
    
    @staticmethod
    def annuler_facture_simple(facture):

        from django.db.models import Sum
        
        if facture.statut == 'ANNULEE':
            raise ValidationError("Cette facture est déjà annulée")
        
        nb_expeditions = facture.expeditions.count()
        if nb_expeditions > 1:
            raise ValidationError(
                f"Cette facture contient {nb_expeditions} expéditions. "
                "Veuillez annuler les expéditions individuellement."
            )
        
        if nb_expeditions == 0:
            raise ValidationError("Cette facture ne contient aucune expédition")
        
        expedition = facture.expeditions.first()

        total_paye = facture.paiements.filter(statut='VALIDE').aggregate(
            total=Sum('montant_paye')
        )['total'] or Decimal('0.00')
        
        for paiement in facture.paiements.filter(statut='VALIDE'):
            paiement.statut = 'ANNULE'
            paiement.save()

        facture.client.solde -= total_paye
        
        montant_impaye = facture.montant_ttc - total_paye
        facture.client.solde -= montant_impaye
        
        facture.client.save()
        
        expedition.statut = 'ANNULEE'
        expedition.save()
        
        expedition.suivis.all().delete()
        
        facture.statut = 'ANNULEE'
        facture.save()

class NotificationService:
    """
    Service pour gérer les notifications et leurs traitements
    """
    
    @staticmethod
    @transaction.atomic
    def traiter_action_notification(notification_id, action):
        """
        Traite l'action de l'agent sur une notification
        
        ACTIONS POSSIBLES :
        - Pour SOLDE_NEGATIF : 'OK' (rembourser et mettre solde à 0)
        - Pour MAINTENANCE_AVANT : 'OK' (confirmer) ou 'REPORTER' (rediriger vers modif)
        - Pour MAINTENANCE_APRES : 'OUI' (revenu) ou 'NON' (pas encore)
        - Pour REMBOURSEMENT_REQUIS : 'OK' (rembourser)
        
        """
        from .models import Notification, Client
        from django.utils import timezone
        
        notification = Notification.objects.get(id=notification_id)
        
        if notification.statut == 'TRAITEE':
            return {'success': False, 'message': 'Notification déjà traitée'}
        
        resultat = {}
        
        if notification.type_notification == 'SOLDE_NEGATIF':
            
            if action == 'OK':
                client = Client.objects.select_for_update().get(id=notification.client.id)
                montant_remboursement = abs(client.solde)
                
                client.solde = Decimal('0.00')
                client.save()
                
                notification.statut = 'TRAITEE'
                notification.action_effectuee = 'REMBOURSE'
                notification.commentaire_traitement = f"Remboursement de {montant_remboursement:,.2f} DA effectué"
                notification.date_traitement = timezone.now()
                notification.save()
                
                resultat = {
                    'success': True,
                    'message': f"Remboursement de {montant_remboursement:,.2f} DA effectué au client {client.prenom} {client.nom}"
                }

        elif notification.type_notification == 'MAINTENANCE_AVANT':
            vehicule = notification.vehicule
            
            if action == 'OK':
                vehicule.statut = 'EN_MAINTENANCE'
                vehicule.save()
                
                notification.statut = 'TRAITEE'
                notification.action_effectuee = 'MAINTENANCE_CONFIRMEE'
                notification.commentaire_traitement = f"Véhicule {vehicule.numero_immatriculation} passé EN_MAINTENANCE"
                notification.date_traitement = timezone.now()
                notification.save()
                
                resultat = {
                    'success': True,
                    'message': f"Véhicule {vehicule.numero_immatriculation} mis en maintenance"
                }
            
            elif action == 'REPORTER':
                notification.statut = 'LUE'
                notification.save()
                
                resultat = {
                    'success': True,
                    'message': 'Redirection vers la modification du véhicule',
                    'redirect': f'/vehicules/{vehicule.id}/modifier/' 
                }

        elif notification.type_notification == 'MAINTENANCE_APRES':
            vehicule = notification.vehicule
            
            if action == 'OUI':
                VehiculeService.confirmer_revision(vehicule)
                
                notification.statut = 'TRAITEE'
                notification.action_effectuee = 'RETOUR_CONFIRME'
                notification.commentaire_traitement = f"Véhicule {vehicule.numero_immatriculation} revenu de maintenance"
                notification.date_traitement = timezone.now()
                notification.save()
                
                resultat = {
                    'success': True,
                    'message': f"Véhicule {vehicule.numero_immatriculation} remis en service"
                }
            
            elif action == 'NON':
                notification.statut = 'LUE'
                notification.save()
                
                resultat = {
                    'success': True,
                    'message': '⏳ Notification marquée comme lue. Elle réapparaîtra demain.'
                }
        
        elif notification.type_notification == 'TOURNEE_TERMINEE':
            tournee = notification.tournee
            
            if action == 'OK':
                notification.statut = 'TRAITEE'
                notification.action_effectuee = 'REDIRECTION_FORMULAIRE'
                notification.date_traitement = timezone.now()
                notification.save()
                
                resultat = {
                    'success': True,
                    'message': 'Redirection vers la modification de la tournée',
                    'redirect': f'/tournees/{tournee.id}/terminer/' 
                }

        elif notification.type_notification == 'REMBOURSEMENT_REQUIS':
            
            if action == 'OK':
                client = notification.client
                incident = notification.incident
                if not client:
                    return {'success': False, 'message': 'Client introuvable'}
                if not incident:
                    return {'success': False, 'message': 'Aucun incident trouvé'}
                
                montant_rembourse_physiquement = abs(client.solde) if client.solde < 0 else Decimal('0.00')
        
                client.solde = Decimal('0.00')
                client.save()
        
                incident.remboursement_effectue = True
                incident.save()
                
                notification.statut = 'TRAITEE'
                notification.action_effectuee = 'REMBOURSE'
                notification.commentaire_traitement = f"Remboursement de {incident.montant_rembourse:,.2f} DA effectué physiquement"
                notification.date_traitement = timezone.now()
                notification.save()
                
                resultat = {
                    'success': True,
                    'message': f"Remboursement de {incident.montant_rembourse:,.2f} DA confirmé"
                }

        elif notification.type_notification == 'INCIDENT_CREE':
            
            if action == 'AFFECTER':
                notification.statut = 'LUE'
                notification.save()
                
                resultat = {
                    'success': True,
                    'message': 'Redirection vers l\'affectation',
                    'redirect': f'/incidents/{notification.incident.id}/assigner/'
                }

        elif notification.type_notification == 'INCIDENT_AFFECTE':
            
            if action == 'VOIR':
                notification.statut = 'LUE'
                notification.save()
                
                resultat = {
                    'success': True,
                    'message': 'Redirection vers l\'incident',
                    'redirect': f'/incidents/{notification.incident.id}/'
                }

        elif notification.type_notification == 'RECLAMATION_CREEE':
            
            if action == 'AFFECTER':
                notification.statut = 'LUE'
                notification.save()
                
                resultat = {
                    'success': True,
                    'message': 'Redirection vers l\'affectation',
                    'redirect': f'/reclamations/{notification.reclamation.id}/assigner/'
                }

        elif notification.type_notification == 'RECLAMATION_AFFECTEE':
            
            if action == 'VOIR':
                notification.statut = 'LUE'
                notification.save()
                
                resultat = {
                    'success': True,
                    'message': 'Redirection vers la réclamation',
                    'redirect': f'/reclamations/{notification.reclamation.id}/'
                }

        elif notification.type_notification == 'INCIDENT_RESOLU':
            
            if action == 'CLOTURER':
                notification.statut = 'LUE'
                notification.save()
                
                resultat = {
                    'success': True,
                    'message': 'Redirection vers la clôture',
                    'redirect': f'/incidents/{notification.incident.id}/cloturer/'
                }

        elif notification.type_notification == 'RECLAMATION_RESOLUE':
            
            if action == 'CLOTURER':
                notification.statut = 'LUE'
                notification.save()
                
                resultat = {
                    'success': True,
                    'message': 'Redirection vers la clôture',
                    'redirect': f'/reclamations/{notification.reclamation.id}/cloturer/'
                }

        return resultat
    
    @staticmethod
    def marquer_comme_lue(notification_id):
        """Marque une notification comme lue"""
        from .models import Notification
        
        notification = Notification.objects.get(id=notification_id)
        
        if notification.statut == 'NON_LUE':
            notification.statut = 'LUE'
            notification.save()
        
        return {'success': True}
    
class IncidentService:
   
    TAUX_REMBOURSEMENT = {
        'PERTE': Decimal('100.00'),
        'ENDOMMAGEMENT': Decimal('100.00'),
        'ACCIDENT': Decimal('100.00'),
        'PROBLEME_TECHNIQUE': Decimal('50.00'),
        'RETARD': Decimal('5.00'),
        'REFUS_DESTINATAIRE': Decimal('0.00'),
        'ADRESSE_INCORRECTE': Decimal('0.00'),
        'DESTINATAIRE_ABSENT': Decimal('0.00'),
        'AUTRE': Decimal('0.00'),
    }
    
    INCIDENTS_GRAVES_ANNULATION = ['PERTE', 'ENDOMMAGEMENT', 'PROBLEME_TECHNIQUE', 'ACCIDENT']
    TYPES_REEXPEDITION = ['REFUS_DESTINATAIRE', 'ADRESSE_INCORRECTE', 'DESTINATAIRE_ABSENT']
    INCIDENTS_AVEC_REMBOURSEMENT = ['PERTE', 'ENDOMMAGEMENT', 'ACCIDENT', 'PROBLEME_TECHNIQUE', 'RETARD']
    
    @staticmethod
    def analyser_cause_retard(expedition):
        """Analyse la cause d'un retard"""
        if not expedition.tournee:
            return "Expédition non affectée à une tournée - Colis au dépôt"
        
        tournee = expedition.tournee
        
        if tournee.statut == 'PREVUE':
            from django.utils import timezone
            if timezone.now() < tournee.date_depart:
                return f"Tournée programmée - Départ prévu le {tournee.date_depart.strftime('%d/%m/%Y à %H:%M')}"
            else:
                return "Tournée en retard de départ"
        elif tournee.statut == 'EN_COURS':
            return f"Tournée en cours - Chauffeur: {tournee.chauffeur.prenom} {tournee.chauffeur.nom}"
        elif tournee.statut == 'TERMINEE':
            return "Tournée terminée mais colis non livré"
        
        return "Cause inconnue"
    
    @staticmethod
    def resoudre_incident_complet(incident, donnees_resolution, agent):
        """Résout un incident avec traitement personnalisé selon le type"""
        from django.utils import timezone
        from .models import HistoriqueIncident, Notification, TrackingExpedition
        from decimal import Decimal
        
        expedition = incident.expedition
        type_incident = incident.type_incident
        
        taux = IncidentService.TAUX_REMBOURSEMENT.get(type_incident, Decimal('0.00'))
        montant_rembourse = Decimal('0.00')
        
        if taux > 0 and expedition:
            montant_ht = expedition.montant_total
            montant_tva = montant_ht * Decimal('0.19')
            montant_ttc = montant_ht + montant_tva
            montant_rembourse = montant_ttc * (taux / Decimal('100.00'))
            
            incident.montant_rembourse = montant_rembourse
            incident.remboursement_effectue = False
            
            client = expedition.client
            solde_avant = client.solde
            solde_apres = solde_avant - montant_rembourse
            
            client.solde = solde_apres
            client.save()
            
            if solde_apres < 0:
                montant_a_rembourser_physiquement = abs(solde_apres)
                Notification.objects.create(
                    type_notification='REMBOURSEMENT_REQUIS',
                    titre=f"Remboursement physique requis - {client.nom} {client.prenom}",
                    message=(
                        f"Suite à la résolution de l'incident {incident.numero_incident}, "
                        f"un remboursement physique de {montant_a_rembourser_physiquement:,.2f} DA "
                        f"doit être effectué au client {client.nom} {client.prenom}.\n\n"
                        f"💰 Détails :\n"
                        f"- Montant à rembourser : {montant_rembourse:,.2f} DA ({taux}%)\n"
                        f"- Solde avant : {solde_avant:,.2f} DA\n"
                        f"- Compensation du solde : {solde_avant:,.2f} DA\n"
                        f"- Reste à rembourser : {montant_a_rembourser_physiquement:,.2f} DA\n\n"
                        f"Le solde du client a été mis à {solde_apres:,.2f} DA (crédit)."
                    ),
                    client=client,
                    incident=incident,
                    statut='NON_LUE',
                    requires_action=True
                )
                incident.remboursement_effectue = False
                incident.save()

            else:
                Notification.objects.create(
                    type_notification='REMBOURSEMENT_REQUIS',
                    titre=f"Compensation appliquée - {client.nom} {client.prenom}",
                    message=(
                        f"Suite à la résolution de l'incident {incident.numero_incident}, "
                        f"une compensation de {montant_rembourse:,.2f} DA a été appliquée "
                        f"au solde du client {client.nom} {client.prenom}.\n\n"
                        f"Détails :\n"
                        f"- Montant compensé : {montant_rembourse:,.2f} DA ({taux}%)\n"
                        f"- Solde avant : {solde_avant:,.2f} DA\n"
                        f"- Nouveau solde : {solde_apres:,.2f} DA\n\n"
                        f"Aucun remboursement physique n'est nécessaire."
                    ),
                    client=client,
                    incident=incident,
                    statut='NON_LUE',
                    requires_action=False
                )
            incident.remboursement_effectue = True
            incident.save()
        
        TrackingExpedition.objects.create(
            expedition=expedition,
            statut_etape='INCIDENT',
            commentaire=f"🚨 Incident {incident.numero_incident} ({incident.get_type_incident_display()}) - Cause : {donnees_resolution.get('cause', 'Non spécifiée')}"
        )
        
        nouveau_statut = donnees_resolution.get('nouveau_statut_exp')
        
        if nouveau_statut == 'ANNULE':
            expedition.statut = 'ANNULE'
            expedition.tournee = None
            expedition.save()

            from .models import Facture
            factures = expedition.factures.filter(statut__in=['IMPAYEE', 'PARTIELLEMENT_PAYEE', 'EN_RETARD'])
            for facture in factures:
                facture.statut = 'ANNULEE'
                facture.save()

            TrackingExpedition.objects.create(
                expedition=expedition,
                statut_etape='ANNULE',
                commentaire=f"Expédition annulée suite à incident {incident.numero_incident}"
            )

        elif nouveau_statut == 'REENVOYE':
            expedition.statut = 'REENVOYE'
            expedition.tournee = None
            expedition.save()
            
            from . import utils
            try:
                utils.ExpeditionService.affecter_tournee_intelligente(expedition)
            except:
                pass
            
            if expedition.tournee:
                utils.ExpeditionService.calculer_date_livraison(expedition)
            
            utils.FacturationService.gerer_facture_expedition(expedition, created_by=agent)
            
            TrackingExpedition.objects.create(
                expedition=expedition,
                statut_etape='REENVOYE',
                commentaire=f"Colis réexpédié suite à incident {incident.numero_incident}"
            )
        
        incident.statut = 'RESOLU'
        incident.actions_entreprises = donnees_resolution.get('solution', '')
        incident.date_resolution = timezone.now()
        incident.taux_remboursement = taux
        incident.save()
        
        # Étape 2 : Incident résolu
        TrackingExpedition.objects.create(
            expedition=expedition,
            statut_etape='INCIDENT_RESOLU',
            commentaire=f"Incident {incident.numero_incident} résolu - Solution : {donnees_resolution.get('solution', '')[:100]}"
        )

        from django.contrib.auth import get_user_model
        AgentUtilisateur = get_user_model()
        agent_responsable_principal = AgentUtilisateur.objects.filter(
            is_responsable=True
        ).first()

        if agent_responsable_principal:
            Notification.objects.create(
                type_notification='INCIDENT_RESOLU',
                titre=f"Incident résolu - {incident.numero_incident}",
                message=(
                    f"L'incident {incident.numero_incident} ({incident.get_type_incident_display()}) "
                    f"a été résolu par {agent.first_name} {agent.last_name}.\n\n"
                    f"Expédition : {expedition.get_numero_expedition()}\n"
                    f"Solution : {donnees_resolution.get('solution', '')[:100]}...\n\n"
                    f"Vous pouvez maintenant clôturer cet incident."
                ),
                incident=incident,
                statut='NON_LUE'
            )
        
        details_parts = [f"Type: {incident.get_type_incident_display()}"]
        
        if donnees_resolution.get('cause'):
            details_parts.append(f"Cause: {donnees_resolution['cause']}")
        
        if montant_rembourse > 0:
            details_parts.append(f"Remboursement: {montant_rembourse:.2f} DA ({taux}%)")
        
        if nouveau_statut:
            details_parts.append(f"Expédition → {nouveau_statut}")
        
        HistoriqueIncident.objects.create(
            incident=incident,
            action="Résolution complète",
            auteur=f"{agent.first_name} {agent.last_name}",
            details=" | ".join(details_parts),
            ancien_statut='EN_COURS',
            nouveau_statut='RESOLU'
        )
        
        return True, "Incident résolu avec succès"
    
    @staticmethod
    def cloturer_incident(incident, auteur="Agent"):
        """
        Clôture définitivement un incident
        """
        from django.core.exceptions import ValidationError
        from .models import HistoriqueIncident
        
        if incident.statut != 'RESOLU':
            raise ValidationError("Un incident doit être résolu avant d'être clôturé")
        
        ancien_statut = incident.statut
        incident.statut = 'CLOS'
        incident.save()
        
        HistoriqueIncident.objects.create(
            incident=incident,
            action="Incident clôturé",
            auteur=auteur,
            ancien_statut=ancien_statut,
            nouveau_statut='CLOS'
        )
    
    @staticmethod
    def assigner_agent_incident(incident, agent_nom, auteur="Système"):
        """
        Assigne un agent responsable à un incident
        """
        from .models import HistoriqueIncident
        
        ancien_agent = incident.agent_responsable
        ancien_statut = incident.statut
        
        incident.agent_responsable = agent_nom
        incident.statut = 'EN_COURS'
        incident.save()
        
        details = f"Assigné à {agent_nom}"
        if ancien_agent:
            details += f" (précédemment : {ancien_agent})"
        
        HistoriqueIncident.objects.create(
            incident=incident,
            action="Incident assigné",
            auteur=auteur,
            details=details,
            ancien_statut=ancien_statut,
            nouveau_statut='EN_COURS'
        )
    
    @staticmethod
    def obtenir_taux_remboursement(type_incident):
        """
        Retourne le taux de remboursement pour un type d'incident donné
        """
        return IncidentService.TAUX_REMBOURSEMENT.get(type_incident, 0.00)
    
    @staticmethod
    def peut_etre_annule(incident):
        """
        Vérifie si un incident peut déclencher une annulation automatique
        """
        return incident.type_incident in IncidentService.INCIDENTS_GRAVES_ANNULATION
    
    @staticmethod
    def necessite_remboursement(incident):
        """
        Vérifie si un incident nécessite un remboursement
        """
        return incident.type_incident in IncidentService.INCIDENTS_AVEC_REMBOURSEMENT
    
    @staticmethod
    def statistiques_incidents(date_debut=None, date_fin=None):
        """
        Génère des statistiques sur les incidents
        """
        from django.db.models import Count, Avg, Sum, Q
        from datetime import datetime, timedelta
        from .models import Incident
        
        if not date_fin:
            date_fin = datetime.now()
        if not date_debut:
            date_debut = date_fin - timedelta(days=30)
        
        incidents = Incident.objects.filter(
            date_heure_incident__range=[date_debut, date_fin]
        )
        
        stats = {
            'total_incidents': incidents.count(),
            'par_type': incidents.values('type_incident').annotate(
                count=Count('id')
            ).order_by('-count'),
            'par_severite': incidents.values('severite').annotate(
                count=Count('id')
            ),
            'par_statut': incidents.values('statut').annotate(
                count=Count('id')
            ),
            'cout_total': incidents.aggregate(Sum('cout_estime'))['cout_estime__sum'] or 0,
            'montant_total_rembourse': incidents.aggregate(Sum('montant_rembourse'))['montant_rembourse__sum'] or 0,
            'taux_resolution': incidents.filter(
                statut__in=['RESOLU', 'CLOS']
            ).count() / incidents.count() * 100 if incidents.count() > 0 else 0,
            'incidents_avec_remboursement': incidents.filter(remboursement_effectue=True).count(),
        }
        
        return stats
    
class ReclamationService:
    """
    Service gérant toutes les opérations liées aux réclamations :
    - Création et traitement des réclamations
    - Assignation aux agents
    - Calcul des délais
    - Compensation clients
    - Statistiques et rapports
    """
    
    @staticmethod
    def traiter_nouvelle_reclamation(reclamation):
        """
        Traite une nouvelle réclamation : priorité automatique, assignation, etc.
        """
        from .models import HistoriqueReclamation, Notification
        from django.contrib.auth import get_user_model

        if reclamation.nature in ['COLIS_PERDU', 'COLIS_ENDOMMAGE', 'REMBOURSEMENT']:
            reclamation.priorite = 'HAUTE'
        elif reclamation.nature == 'RETARD_LIVRAISON':
            reclamation.priorite = 'NORMALE'
        
        reclamation.save(update_fields=['priorite'])

        HistoriqueReclamation.objects.create(
            reclamation=reclamation,
            action="Réclamation créée",
            auteur="Système",
            details=f"Réclamation créée par le client {reclamation.client}",
            nouveau_statut='OUVERTE'
        )

        
        from .notification import AlerteEmailService
        AlerteEmailService.envoyer_notification_nouvelle_reclamation(reclamation)
    
    @staticmethod
    def assigner_agent(reclamation, agent_nom):
        """
        Assigne un agent à une réclamation
        """
        from django.utils import timezone
        from .models import HistoriqueReclamation, Notification
        
        ancien_agent = reclamation.agent_responsable
        
        reclamation.agent_responsable = agent_nom
        reclamation.date_assignation = timezone.now()
        reclamation.statut = 'EN_COURS'
        reclamation.save()

        HistoriqueReclamation.objects.create(
            reclamation=reclamation,
            action="Assignation agent",
            auteur="Système",
            details=f"Assigné à {agent_nom}" + (f" (précédemment: {ancien_agent})" if ancien_agent else ""),
            ancien_statut='OUVERTE',
            nouveau_statut='EN_COURS'
        )

    
    @staticmethod
    def repondre_reclamation(reclamation, reponse, solution, auteur):
        """
        Enregistre une réponse à la réclamation
        """
        from .models import HistoriqueReclamation
        
        ancien_statut = reclamation.statut
        
        reclamation.reponse_agent = reponse
        reclamation.solution_proposee = solution
        reclamation.statut = 'EN_ATTENTE_CLIENT'
        reclamation.save()

        HistoriqueReclamation.objects.create(
            reclamation=reclamation,
            action="Réponse envoyée",
            auteur=auteur,
            details=f"Réponse: {reponse[:100]}...",
            ancien_statut=ancien_statut,
            nouveau_statut='EN_ATTENTE_CLIENT'
        )
        
        from .notification import AlerteEmailService
        AlerteEmailService.envoyer_reponse_reclamation_client(reclamation)
    
    @staticmethod
    def resoudre_reclamation(reclamation, auteur, accorder_compensation=False, montant_compensation=0):
        """
        Marque une réclamation comme résolue
        """
        from django.utils import timezone
        from .models import HistoriqueReclamation, Notification
        from django.contrib.auth import get_user_model
        
        ancien_statut = reclamation.statut
        
        reclamation.statut = 'RESOLUE'
        reclamation.date_resolution = timezone.now()
        reclamation.compensation_accordee = accorder_compensation
        reclamation.montant_compensation = Decimal(str(montant_compensation))
        reclamation.save()

        HistoriqueReclamation.objects.create(
            reclamation=reclamation,
            action="Réclamation résolue",
            auteur=auteur,
            details=f"Compensation: {montant_compensation} DA" if accorder_compensation else "Aucune compensation",
            ancien_statut=ancien_statut,
            nouveau_statut='RESOLUE'
        )

        if accorder_compensation and montant_compensation > 0:
            reclamation.client.solde -= Decimal(str(montant_compensation))
            reclamation.client.save()

        AgentUtilisateur = get_user_model()
        agent_responsable_principal = AgentUtilisateur.objects.filter(
            is_responsable=True
        ).first()
        
        if agent_responsable_principal:
            Notification.objects.create(
                type_notification='RECLAMATION_RESOLUE',
                titre=f"Réclamation résolue - {reclamation.numero_reclamation}",
                message=(
                    f"La réclamation {reclamation.numero_reclamation} ({reclamation.get_nature_display()}) "
                    f"a été résolue par {auteur}.\n\n"
                    f"Client : {reclamation.client.prenom} {reclamation.client.nom}\n"
                    f"Solution : {reclamation.solution_proposee[:100] if reclamation.solution_proposee else 'Non spécifiée'}...\n"
                    f"Compensation : {'Oui - ' + str(montant_compensation) + ' DA' if accorder_compensation else 'Non'}\n\n"
                    f"Vous pouvez maintenant clôturer cette réclamation."
                ),
                client=reclamation.client,
                reclamation=reclamation,
                statut='NON_LUE'
            )
    
    @staticmethod
    def cloturer_reclamation(reclamation, auteur):
        """
        Clôture définitivement une réclamation
        """
        from .models import HistoriqueReclamation
        
        if reclamation.statut != 'RESOLUE':
            raise ValidationError("Une réclamation doit être résolue avant d'être clôturée")
        
        ancien_statut = reclamation.statut
        reclamation.statut = 'CLOSE'
        reclamation.save()

        HistoriqueReclamation.objects.create(
            reclamation=reclamation,
            action="Réclamation clôturée",
            auteur=auteur,
            ancien_statut=ancien_statut,
            nouveau_statut='CLOSE'
        )
    
    @staticmethod
    def annuler_reclamation(reclamation, motif, auteur):
        """
        Annule une réclamation (demande infondée, doublon, etc.)
        """
        from .models import HistoriqueReclamation
        
        ancien_statut = reclamation.statut
        reclamation.statut = 'ANNULEE'
        reclamation.remarques = (reclamation.remarques or "") + f"\n[ANNULATION] {motif}"

        HistoriqueReclamation.objects.create(
            reclamation=reclamation,
            action="Réclamation annulée",
            auteur=auteur,
            details=f"Motif: {motif}",
            ancien_statut=ancien_statut,
            nouveau_statut='ANNULEE'
        )
    
    @staticmethod
    def calculer_delai_traitement(reclamation):
        """
        Calcule le délai de traitement en jours
        """
        if reclamation.date_resolution:
            delta = reclamation.date_resolution - reclamation.date_creation
            reclamation.delai_traitement_jours = delta.days
            from django.db.models import F
            from .models import Reclamation
            Reclamation.objects.filter(pk=reclamation.pk).update(
                delai_traitement_jours=reclamation.delai_traitement_jours
)
    
    @staticmethod
    def enregistrer_evaluation_client(reclamation, note, commentaire):
        """
        Enregistre l'évaluation du client sur le traitement de sa réclamation
        """
        from .models import HistoriqueReclamation
        
        if not (1 <= note <= 5):
            raise ValidationError("La note doit être entre 1 et 5")
        
        reclamation.evaluation_client = note
        reclamation.commentaire_client = commentaire
        reclamation.save()

        HistoriqueReclamation.objects.create(
            reclamation=reclamation,
            action="Évaluation client",
            auteur=str(reclamation.client),
            details=f"Note: {note}/5 - {commentaire}"
        )
    
    @staticmethod
    def statistiques_reclamations(date_debut=None, date_fin=None):
        """
        Génère des statistiques sur les réclamations
        """
        from django.db.models import Count, Avg, Sum, Q, F
        from datetime import datetime, timedelta
        from .models import Reclamation

        if not date_fin:
            date_fin = datetime.now()
        if not date_debut:
            date_debut = date_fin - timedelta(days=30)
        
        reclamations = Reclamation.objects.filter(
            date_creation__range=[date_debut, date_fin]
        )
        
        stats = {
            'total_reclamations': reclamations.count(),
            'par_nature': reclamations.values('nature').annotate(
                count=Count('id')
            ).order_by('-count'),
            'par_statut': reclamations.values('statut').annotate(
                count=Count('id')
            ),
            'par_priorite': reclamations.values('priorite').annotate(
                count=Count('id')
            ),
            'delai_moyen_traitement': reclamations.filter(
                delai_traitement_jours__isnull=False
            ).aggregate(Avg('delai_traitement_jours'))['delai_traitement_jours__avg'] or 0,
            'taux_resolution': reclamations.filter(
                statut__in=['RESOLUE', 'CLOSE']
            ).count() / reclamations.count() * 100 if reclamations.count() > 0 else 0,
            'compensation_totale': reclamations.filter(
                compensation_accordee=True
            ).aggregate(Sum('montant_compensation'))['montant_compensation__sum'] or 0,
            'note_moyenne': reclamations.filter(
                evaluation_client__isnull=False
            ).aggregate(Avg('evaluation_client'))['evaluation_client__avg'] or 0,
        }
        
        return stats
    
    @staticmethod
    def top_clients_reclamants(limite=10):
        """
        Retourne les clients ayant le plus de réclamations
        """
        from django.db.models import Count
        from .models import Reclamation
        
        return Reclamation.objects.values(
            'client__prenom',
            'client__nom',
            'client__id'
        ).annotate(
            nb_reclamations=Count('id')
        ).order_by('-nb_reclamations')[:limite]
    
    @staticmethod
    def motifs_recurrents():
        """
        Analyse des motifs de réclamations les plus fréquents
        """
        from django.db.models import Count
        from .models import Reclamation
        
        return Reclamation.objects.values('nature').annotate(
            count=Count('id'),
            pourcentage=Count('id') * 100.0 / Reclamation.objects.count()
        ).order_by('-count')
    
"""
Utilitaire d'export PDF amélioré pour toutes les tables
"""
from reportlab.lib.pagesizes import A4, landscape  # type: ignore
from reportlab.lib import colors  # type: ignore
from reportlab.lib.units import cm  # type: ignore
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak  # type: ignore
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle  # type: ignore
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT  # type: ignore
from io import BytesIO
from datetime import datetime
from django.http import HttpResponse

def generer_pdf_liste(titre_document, headers, data_rows, nom_fichier_base, orientation='portrait'):

    buffer = BytesIO()

    pagesize = landscape(A4) if orientation == 'landscape' else A4
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        topMargin=1.5*cm,
        bottomMargin=2*cm,
        leftMargin=1.5*cm,
        rightMargin=1.5*cm,
    )
    
    elements = []
    styles = getSampleStyleSheet()

    header_style = ParagraphStyle(
        'header_style',
        parent=styles['Normal'],
        fontSize=18,
        textColor=colors.HexColor("#1a5490"),
        fontName='Helvetica-Bold',
        spaceAfter=5,
    )
    
    subtitle_style = ParagraphStyle(
        'subtitle_style',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor("#666666"),
        fontName='Helvetica',
    )
    
    title_style = ParagraphStyle(
        'title_style',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor("#1a5490"),
        alignment=TA_CENTER,
        spaceAfter=20,
        fontName='Helvetica-Bold',
    )

    elements.append(Paragraph("🚚 <b>TransportPro</b>", header_style))
    elements.append(Spacer(1, 0.15*cm)) 
    elements.append(Paragraph(
        f"Document généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}",
        subtitle_style
    ))
    elements.append(Spacer(1, 0.6*cm))

    from reportlab.platypus import HRFlowable
    elements.append(HRFlowable(
        width="100%",
        thickness=2,
        color=colors.HexColor("#1a5490"),
        spaceBefore=5,
        spaceAfter=15
    ))

    elements.append(Paragraph(titre_document, title_style))
    elements.append(Spacer(1, 0.3*cm))

    stats_style = ParagraphStyle(
        'stats',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor("#555555"),
        alignment=TA_RIGHT,
    )
    elements.append(Paragraph(
        f"<b>Total d'enregistrements :</b> {len(data_rows)}",
        stats_style
    ))
    elements.append(Spacer(1, 0.4*cm))

    if not data_rows:
        elements.append(Paragraph(
            "<i>Aucune donnée à afficher</i>",
            styles['Normal']
        ))
    else:
        table_data = [headers] + data_rows

        if orientation == 'landscape':
            largeur_totale = 25 * cm
        else:
            largeur_totale = 18 * cm
        
        nb_colonnes = len(headers)
        largeur_colonne = largeur_totale / nb_colonnes
        col_widths = [largeur_colonne] * nb_colonnes
        
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1a5490")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),

            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),

            ('ROWBACKGROUNDS', (0, 1), (-1, -1), 
             [colors.white, colors.HexColor("#f8f9fa")]),

            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
            ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor("#1a5490")),

            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        
        elements.append(table)

    def draw_footer(canvas, doc):
        canvas.saveState()

        canvas.setStrokeColor(colors.HexColor("#1a5490"))
        canvas.setLineWidth(1)
        canvas.line(1.5*cm, 2.5*cm, pagesize[0] - 1.5*cm, 2.5*cm)

        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#666666"))

        canvas.drawString(1.5*cm, 1.8*cm, "TransportPro - USTHB, Bab Ezzouar")
        canvas.drawString(1.5*cm, 1.4*cm, "Email : transportproalg@usthb.com")

        page_text = f"Page {doc.page}"
        canvas.drawRightString(pagesize[0] - 1.5*cm, 1.8*cm, page_text)
        canvas.drawRightString(
            pagesize[0] - 1.5*cm, 
            1.4*cm, 
            datetime.now().strftime('%d/%m/%Y')
        )
        
        canvas.restoreState()

    doc.build(elements, onFirstPage=draw_footer, onLaterPages=draw_footer)
    buffer.seek(0)

    response = HttpResponse(buffer, content_type="application/pdf")
    nom_fichier = f"TransportPro_{nom_fichier_base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{nom_fichier}"'
    
    return response

def generer_pdf_fiche(titre_document, sections, nom_fichier_base, remarques=None):
    
    buffer = BytesIO()
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=1.5*cm,
        bottomMargin=2*cm,
        leftMargin=2*cm,
        rightMargin=2*cm,
    )
    
    elements = []
    styles = getSampleStyleSheet()

    header_style = ParagraphStyle(
        'header_style',
        parent=styles['Normal'],
        fontSize=18,
        textColor=colors.HexColor("#1a5490"),
        fontName='Helvetica-Bold',
    )
    
    subtitle_style = ParagraphStyle(
        'subtitle_style',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor("#666666"),
    )
    
    title_style = ParagraphStyle(
        'title_style',
        fontSize=16,
        textColor=colors.HexColor("#1a5490"), 
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        spaceAfter=10,
    )
    
    section_style = ParagraphStyle(
        'section_style',
        fontSize=13,
        textColor=colors.white,
        fontName='Helvetica-Bold',
        leftIndent=10,
        spaceBefore=15,
        spaceAfter=8,
    )
    
    elements.append(Paragraph("🚚 <b>TransportPro</b>", header_style))
    elements.append(Spacer(1, 0.15*cm))  # Espace entre le titre et la date
    elements.append(Paragraph(
        f"Document généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}",
        subtitle_style
    ))
    elements.append(Spacer(1, 0.5*cm))
    
    from reportlab.platypus import HRFlowable
    elements.append(HRFlowable(
        width="100%",
        thickness=2,
        color=colors.HexColor("#1a5490"),
        spaceBefore=5,
        spaceAfter=15
    ))

    elements.append(Paragraph(titre_document, title_style))
    elements.append(Spacer(1, 0.5*cm))

    for idx, section in enumerate(sections):

        section_table = Table(
            [[Paragraph(section['titre'], section_style)]],
            colWidths=[17*cm]
        )
        section_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#1a5490")),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(section_table)
        elements.append(Spacer(1, 0.2*cm))
        
        data_table = Table(section['data'], colWidths=[6*cm, 11*cm])
        data_table.setStyle(TableStyle([

            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#e9ecef")),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (0, -1), 10),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor("#495057")),

            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (1, 0), (1, -1), 10),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),

            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        
        elements.append(data_table)
        elements.append(Spacer(1, 0.5*cm))

    if remarques:
        remarques_style = ParagraphStyle(
            'remarques_style',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor("#495057"),
            leftIndent=10,
            rightIndent=10,
            spaceAfter=10,
        )
        
        elements.append(Spacer(1, 0.3*cm))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
        elements.append(Spacer(1, 0.3*cm))
        elements.append(Paragraph("<b>📝 Remarques</b>", section_style))
        elements.append(Spacer(1, 0.2*cm))
        elements.append(Paragraph(remarques, remarques_style))

    def draw_footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#1a5490"))
        canvas.setLineWidth(1)
        canvas.line(2*cm, 2.5*cm, A4[0] - 2*cm, 2.5*cm)
        
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(2*cm, 1.8*cm, "TransportPro - USTHB, Bab Ezzouar")
        canvas.drawString(2*cm, 1.4*cm, "Email : transportproalg@usthb.com")
        
        page_text = f"Page {doc.page}"
        canvas.drawRightString(A4[0] - 2*cm, 1.8*cm, page_text)
        canvas.drawRightString(A4[0] - 2*cm, 1.4*cm, datetime.now().strftime('%d/%m/%Y'))
        
        canvas.restoreState()

    doc.build(elements, onFirstPage=draw_footer, onLaterPages=draw_footer)
    buffer.seek(0)

    response = HttpResponse(buffer, content_type="application/pdf")
    nom_fichier = f"TransportPro_{nom_fichier_base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{nom_fichier}"'
    
    return response