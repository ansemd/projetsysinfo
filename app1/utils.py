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
        
        # 1. Vérifier disponibilité (nouvelle tournée uniquement)
        if tournee.pk is None:
            TourneeService.verifier_disponibilite(tournee)
        
        # 2. Kilométrage départ (enregistrer le km actuel du véhicule)
        if tournee.pk is None and not tournee.kilometrage_depart:
            tournee.kilometrage_depart = tournee.vehicule.kilometrage
        
        # 3. Calculs kilométrage et consommation (si tournée terminée)
        if tournee.kilometrage_arrivee and tournee.kilometrage_depart:
            TourneeService.calculer_kilometrage_et_consommation(tournee)
        
        # 4. Gérer statuts ressources (chauffeur, véhicule, expéditions)
        TourneeService.gerer_statuts_ressources(tournee)
        
        # 5. Auto-démarrage si date départ atteinte
        if tournee.statut == 'PREVUE' and timezone.now() >= tournee.date_depart:
            tournee.statut = 'EN_COURS'

    @staticmethod
    @transaction.atomic
    def verifier_disponibilite(tournee):
        """
        Vérifie que chauffeur ET véhicule sont DISPONIBLES
        
        IMPORTANT : Utilise select_for_update() pour éviter les RACE CONDITIONS
        (2 agents ne peuvent pas affecter le même chauffeur/véhicule simultanément)
        """
        # Lock les ressources (personne d'autre ne peut les modifier pendant la vérification)
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
        
        LOGIQUE :
        - PREVUE / EN_COURS → Chauffeur + Véhicule = EN_TOURNEE
        - EN_COURS → Expéditions = EN_TRANSIT
        - TERMINEE → Chauffeur + Véhicule = DISPONIBLE, Expéditions = LIVRE
        """
        
        if tournee.statut in ['PREVUE', 'EN_COURS']:
            # Réserver les ressources
            tournee.chauffeur.statut_disponibilite = 'EN_TOURNEE'
            tournee.vehicule.statut = 'EN_TOURNEE'
            
            # Si tournée démarre → mettre expéditions EN_TRANSIT
            if tournee.statut == 'EN_COURS':
                from .models import TrackingExpedition
                for exp in tournee.expeditions.all():
                    if exp.statut != 'EN_TRANSIT':
                        exp.statut = 'EN_TRANSIT'
                        exp.save(update_fields=['statut'])
                        
                        # Créer suivi de tracking
                        TrackingService.creer_suivi(
                            exp,
                            'EN_TRANSIT',
                            f"Colis en transit vers {exp.destination.ville}"
                        )
        
        elif tournee.statut == 'TERMINEE':
            # Libérer les ressources
            tournee.chauffeur.statut_disponibilite = 'DISPONIBLE'
            tournee.vehicule.statut = 'DISPONIBLE'
            
            # Mettre à jour le kilométrage du véhicule
            if tournee.kilometrage_arrivee:
                tournee.vehicule.kilometrage = tournee.kilometrage_arrivee
            
            # Marquer expéditions comme LIVREES
            from .models import TrackingExpedition
            for exp in tournee.expeditions.all():
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
        
        # Sauvegarder les changements
        tournee.chauffeur.save()
        tournee.vehicule.save()

    @staticmethod
    def peut_demarrer(tournee):
        """
        Vérifie si une tournée peut démarrer (utilisé par taches_quotidiennes)
        
        RÈGLE : Une tournée ne peut démarrer que si elle a au moins 1 expédition
        
        Returns:
            (bool, str) - (peut_démarrer, raison_si_non)
        """
        if not tournee.expedition_set.exists():
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
        # Validation poids
        if expedition.poids <= 0:
            raise ValidationError({'poids': "Le poids doit être supérieur à 0"})
        
        # Vérifier modification si tournée en cours/terminée
        if expedition.pk:
            from .models import Expedition
            ancienne = Expedition.objects.get(pk=expedition.pk)
            if ancienne.tournee and ancienne.tournee.statut != 'PREVUE':
                raise ValidationError(
                    "Impossible de modifier : la tournée est déjà en cours ou terminée"
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
        
        CRITÈRES DE COMPATIBILITÉ :
        - Même zone géographique
        - Statut PREVUE
        - Capacité suffisante
        """
        from .models import Tournee
        
        tournees_compatibles = Tournee.objects.filter(
            zone_cible=expedition.destination.zone_logistique,
            statut='PREVUE',
            date_depart__gte=timezone.now()
        ).order_by('date_depart')
        
        # Chercher une tournée avec capacité suffisante
        for tournee in tournees_compatibles:
            totaux = tournee.expeditions.aggregate(poids_total=Sum('poids'))
            poids_actuel = totaux['poids_total'] or 0
            
            if float(poids_actuel) + float(expedition.poids) <= float(tournee.vehicule.capacite_poids):
                expedition.tournee = tournee
                return
        
        # Aucune tournée compatible → en créer une nouvelle
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
        
        # Calculer délai selon la zone
        zone = expedition.destination.zone_logistique
        if zone == 'CENTRE':
            jours_delai = 1
        elif zone in ['EST', 'OUEST']:
            jours_delai = 2
        elif zone == 'SUD':
            jours_delai = 3
        else:
            jours_delai = 1
        
        # Date de départ = maintenant + délai
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
        
        # Départ immédiat si avant 14h, sinon demain matin 8h
        maintenant = timezone.now()
        if maintenant.hour < 14:
            date_depart = maintenant
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
        Placeholder pour envoyer email/SMS au destinataire
        TODO : Implémenter avec Gmail ou service SMS
        """
        pass

class VehiculeService:
    """
    Service pour gérer les maintenances automatiques des véhicules
    """
    
    @staticmethod
    def verifier_vehicule_libre(vehicule):
        """
        Vérifie si un véhicule n'a pas de tournée EN_COURS ou PREVUE
        
        Returns:
            bool: True si libre, False si occupé
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
        
        Note : Les changements de statut EN_MAINTENANCE et DISPONIBLE sont maintenant
        gérés UNIQUEMENT par :
        1. Les notifications + validation agent (maintenance)
        2. La fin de tournée (passage DISPONIBLE automatique)
        """
        # Première fois : calculer date prochaine révision
        if vehicule.date_derniere_revision and not vehicule.date_prochaine_revision:
            vehicule.date_prochaine_revision = vehicule.date_derniere_revision + timedelta(days=180)
    
    @staticmethod
    def confirmer_revision(vehicule):
        """
        Confirme qu'une révision a été effectuée (appelé depuis notification)
        
        ACTIONS :
        - DPR devient DDR
        - Nouvelle DPR = DDR + 180 jours
        - Véhicule passe DISPONIBLE
        """
        # DPR devient DDR
        vehicule.date_derniere_revision = vehicule.date_prochaine_revision
        
        # Calculer nouvelle DPR (+180 jours)
        vehicule.date_prochaine_revision = vehicule.date_derniere_revision + timedelta(days=180)
        
        # Passer DISPONIBLE
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
        """
        ⏰ Exécuté à 17h30 (J-1) par le scheduler
        
        Vérifie les véhicules dont la maintenance est DEMAIN et crée les notifications
        
        2 CAS :
        1. Véhicule EN TOURNÉE → Notification "Véhicule occupé, modifier DPR ?"
        2. Véhicule DISPONIBLE → Notification "Confirmer maintenance demain ?"
        """
        from datetime import date, timedelta
        from .models import Vehicule, Notification
        
        demain = date.today() + timedelta(days=1)
        
        # Trouver tous les véhicules avec DPR = demain
        vehicules_maintenance_demain = Vehicule.objects.filter(
            date_prochaine_revision=demain
        )
        
        stats = {
            'notifications_vehicule_en_tournee': 0,
            'notifications_confirmation': 0,
        }
        
        for vehicule in vehicules_maintenance_demain:
            
            # Check si le véhicule est en tournée
            if not VehiculeService.verifier_vehicule_libre(vehicule):
                # ⚠️ CAS 1 : VÉHICULE EN TOURNÉE
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
                # ✅ CAS 2 : VÉHICULE DISPONIBLE
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
        """
        ⏰ Exécuté à 8h (J+1, J+2, J+3...) par le scheduler
        
        Vérifie les véhicules EN_MAINTENANCE et demande s'ils sont revenus
        
        IMPORTANT : Ne crée PAS de notification si une existe déjà (NON_LUE ou LUE)
        pour éviter le spam quotidien
        """
        from datetime import date
        from .models import Vehicule, Notification
        
        # Tous les véhicules EN_MAINTENANCE dont la DPR est PASSÉE
        vehicules_en_maintenance = Vehicule.objects.filter(
            statut='EN_MAINTENANCE',
            date_prochaine_revision__lt=date.today()
        )
        
        stats = {
            'notifications_retour': 0,
        }
        
        for vehicule in vehicules_en_maintenance:
            
            # Vérifier si une notification existe déjà pour ce véhicule
            notif_existante = Notification.objects.filter(
                vehicule=vehicule,
                type_notification='MAINTENANCE_APRES',
                statut__in=['NON_LUE', 'LUE']
            ).exists()
            
            # Ne créer notification que si pas déjà une en cours
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
        """
        Recalcule les montants HT, TVA et TTC d'une facture
        en fonction des expéditions qu'elle contient
        
        Formules :
        - Montant HT = Somme des montants des expéditions
        - Montant TVA = Montant HT × 19%
        - Montant TTC = Montant HT + Montant TVA
        """
        from django.db.models import Sum
        
        # Montant HT = somme des montants de toutes les expéditions
        montant_ht = facture.expeditions.aggregate(
            total=Sum('montant_total')
        )['total'] or Decimal('0.00')
        
        # TVA = Montant HT × taux de TVA
        montant_tva = montant_ht * (facture.taux_tva / 100)
        
        # TTC = HT + TVA
        montant_ttc = montant_ht + montant_tva
        
        # Mettre à jour la facture
        facture.montant_ht = montant_ht
        facture.montant_tva = montant_tva
        facture.montant_ttc = montant_ttc
        facture.save()
        
        return facture
    
    @staticmethod
    def calculer_montant_restant(facture):
        """
        Calcule le montant restant à payer
        
        Formule : Montant TTC - Somme des paiements valides
        """
        from django.db.models import Sum
        
        total_paye = facture.paiements.filter(statut='VALIDE').aggregate(
            total=Sum('montant_paye')
        )['total'] or Decimal('0.00')
        
        return facture.montant_ttc - total_paye
    
    @staticmethod
    def mettre_a_jour_statut_facture(facture):
        """
        Met à jour automatiquement le statut de la facture
        
        LOGIQUE :
        - Montant restant = 0 → PAYEE
        - Montant restant < Montant TTC → PARTIELLEMENT_PAYEE (ou EN_RETARD si échéance passée)
        - Montant restant = Montant TTC → IMPAYEE (ou EN_RETARD si échéance passée)
        """
        from datetime import date
        
        # Ne pas modifier une facture annulée
        if facture.statut == 'ANNULEE':
            return
        
        montant_restant = FacturationService.calculer_montant_restant(facture)
        
        # Vérifier si payée complètement
        if montant_restant <= 0:
            facture.statut = 'PAYEE'
        
        # Vérifier si partiellement payée
        elif montant_restant < facture.montant_ttc:
            if date.today() > facture.date_echeance:
                facture.statut = 'EN_RETARD'
            else:
                facture.statut = 'PARTIELLEMENT_PAYEE'
        
        # Sinon impayée
        else:
            if date.today() > facture.date_echeance:
                facture.statut = 'EN_RETARD'
            else:
                facture.statut = 'IMPAYEE'
        
        facture.save()
    
    @staticmethod
    def gerer_facture_expedition(expedition):
        """
        Crée une nouvelle facture OU ajoute l'expédition à une facture existante
        
        LOGIQUE DE REGROUPEMENT :
        - Si une facture IMPAYEE/PARTIELLEMENT_PAYEE existe AUJOURD'HUI
          → Ajouter l'expédition à cette facture
        - Sinon → Créer une nouvelle facture
        
        ✅ AVEC COMPENSATION AUTOMATIQUE si client a solde négatif (crédit)
        """
        from datetime import date, timedelta
        from .models import Facture
        
        client = expedition.client
        aujourd_hui = date.today()
        
        # Chercher une facture existante du jour pour ce client
        facture_du_jour = Facture.objects.filter(
            client=client,
            date_creation__date=aujourd_hui,
            statut__in=['IMPAYEE', 'PARTIELLEMENT_PAYEE']
        ).first()
        
        if facture_du_jour:
            # AJOUTER à la facture existante
            facture_du_jour.expeditions.add(expedition)
            
            # Recalculer les montants
            FacturationService.calculer_montants_facture(facture_du_jour)
            
            # Calculer le montant TTC de cette expédition
            montant_exp_tva = expedition.montant_total * (facture_du_jour.taux_tva / 100)
            montant_exp_ttc = expedition.montant_total + montant_exp_tva
            
            # Mettre à jour le solde du client (augmenter la dette)
            client.solde += montant_exp_ttc
            client.save()
            
            # ✅ COMPENSATION si solde négatif
            if client.solde < 0:
                FacturationService.appliquer_compensation_solde(client, facture_du_jour)
            
            # Mettre à jour le statut de la facture
            FacturationService.mettre_a_jour_statut_facture(facture_du_jour)
            
            return facture_du_jour
        
        else:
            # CRÉER une NOUVELLE facture
            facture = Facture.objects.create(
                client=client,
                date_echeance=aujourd_hui + timedelta(days=30),
                statut='IMPAYEE',
                taux_tva=Decimal('19.00')
            )
            
            # Ajouter l'expédition
            facture.expeditions.add(expedition)
            
            # Calculer les montants
            FacturationService.calculer_montants_facture(facture)
            
            # Mettre à jour le solde du client (augmenter la dette)
            client.solde += facture.montant_ttc
            client.save()
            
            # ✅ COMPENSATION si solde négatif
            if client.solde < 0:
                FacturationService.appliquer_compensation_solde(client, facture)
            
            return facture
    
    @staticmethod
    def appliquer_compensation_solde(client, facture):
        """
        ✅ COMPENSATION AUTOMATIQUE du solde négatif (crédit client)
        
        Cette fonction est appelée AUTOMATIQUEMENT quand :
        - Agent a choisi "Compenser" dans la notification solde négatif
        - Client crée une nouvelle expédition
        
        LOGIQUE :
        - Client a solde = -5000 DA (crédit)
        - Nouvelle facture = 8000 DA
        - Montant TTC après compensation = 8000 - 5000 = 3000 DA
        - Nouveau solde = 0 DA
        
        IMPORTANT : Cette compensation ne se fait QUE si l'agent a validé
        via la notification (bouton "Compenser")
        Si agent a choisi "Rembourser", le solde est déjà à 0
        """
        # ✅ VÉRIFICATION : Compensation autorisée ?
        if not client.compensation_autorisee:
            # Agent a choisi "Rembourser" ou n'a pas encore traité
            return
        
        if client.solde >= 0:
            # Pas de crédit à compenser
            return
        
        credit_client = abs(client.solde)  # Montant du crédit
        montant_avant = facture.montant_ttc
        
        if credit_client >= facture.montant_ttc:
            # Le crédit couvre TOUTE la facture
            facture.montant_ttc = Decimal('0.00')
            client.solde += montant_avant  # Diminuer le crédit
        else:
            # Le crédit couvre PARTIELLEMENT la facture
            facture.montant_ttc -= credit_client
            client.solde = Decimal('0.00')  # Crédit épuisé
        
        facture.save()
        client.save()
        
        # Log pour l'agent (optionnel)
        facture.remarques = (facture.remarques or '') + f"\n[Compensation : {credit_client} DA de crédit utilisé]"
        facture.save()
    
    @staticmethod
    def enregistrer_paiement(facture, montant, mode_paiement, reference=None, remarques=None):
        """
        Enregistre un paiement pour une facture
        
        VALIDATIONS :
        - Facture non annulée
        - Facture non déjà payée
        - Montant > 0
        - Montant <= Montant restant
        
        ACTIONS :
        - Créer objet Paiement
        - Diminuer solde client
        - Mettre à jour statut facture
        """
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
        
        # Créer le paiement
        paiement = Paiement.objects.create(
            facture=facture,
            client=facture.client,
            montant_paye=montant,
            mode_paiement=mode_paiement,
            reference_transaction=reference,
            remarques=remarques,
            statut='VALIDE'
        )
        
        # Mettre à jour le solde du client (diminuer la dette)
        facture.client.solde -= montant
        facture.client.save()
        
        # Mettre à jour le statut de la facture
        FacturationService.mettre_a_jour_statut_facture(facture)
        
        return paiement
    
    @staticmethod
    def annuler_facture_simple(facture):
        """
        Annule une facture contenant UNE SEULE expédition
        
        Pour les factures contenant plusieurs expéditions,
        il faut annuler les expéditions une par une
        
        ACTIONS :
        - Annuler tous les paiements
        - Rembourser le client (crédit)
        - Marquer l'expédition comme annulée
        - Marquer la facture comme annulée
        """
        from django.db.models import Sum
        
        if facture.statut == 'ANNULEE':
            raise ValidationError("Cette facture est déjà annulée")
        
        # Vérifier qu'il n'y a qu'une seule expédition
        nb_expeditions = facture.expeditions.count()
        if nb_expeditions > 1:
            raise ValidationError(
                f"Cette facture contient {nb_expeditions} expéditions. "
                "Veuillez annuler les expéditions individuellement."
            )
        
        if nb_expeditions == 0:
            raise ValidationError("Cette facture ne contient aucune expédition")
        
        # Récupérer l'expédition
        expedition = facture.expeditions.first()
        
        # Calculer le total payé
        total_paye = facture.paiements.filter(statut='VALIDE').aggregate(
            total=Sum('montant_paye')
        )['total'] or Decimal('0.00')
        
        # Annuler tous les paiements
        for paiement in facture.paiements.filter(statut='VALIDE'):
            paiement.statut = 'ANNULE'
            paiement.save()
        
        # Rembourser au client le total payé (crédit)
        facture.client.solde -= total_paye
        
        # Enlever le montant non payé du solde
        montant_impaye = facture.montant_ttc - total_paye
        facture.client.solde -= montant_impaye
        
        facture.client.save()
        
        # Marquer l'expédition comme annulée
        expedition.statut = 'ANNULEE'
        expedition.save()
        
        # Supprimer les trackings de l'expédition
        expedition.suivis.all().delete()
        
        # Marquer la facture comme annulée
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
        - Pour SOLDE_NEGATIF : 'COMPENSER' ou 'REMBOURSER'
        - Pour MAINTENANCE_AVANT : 'CONFIRMER_MAINTENANCE' ou 'REPORTER_MAINTENANCE'
        - Pour MAINTENANCE_APRES : 'CONFIRMER_RETOUR' ou 'PAS_ENCORE_RETOUR'
        
        Returns:
            dict: Résultat du traitement {'success': bool, 'message': str}
        """
        from .models import Notification, Client
        from django.utils import timezone
        
        notification = Notification.objects.get(id=notification_id)
        
        if notification.statut == 'TRAITEE':
            return {'success': False, 'message': 'Notification déjà traitée'}
        
        resultat = {}
        
        # ========== NOTIFICATIONS SOLDE NÉGATIF ==========
        if notification.type_notification == 'SOLDE_NEGATIF':
            client = Client.objects.select_for_update().get(id=notification.client.id)
            
            if action == 'COMPENSER':
                # ✅ Agent a choisi de COMPENSER sur prochaines factures
                client.compensation_autorisee = True
                client.save()
                
                notification.statut = 'TRAITEE'
                notification.action_effectuee = 'COMPENSATION_AUTORISEE'
                notification.commentaire_traitement = f"Compensation autorisée pour crédit de {abs(client.solde):,.2f} DA"
                notification.date_traitement = timezone.now()
                notification.save()
                
                resultat = {
                    'success': True,
                    'message': f"Compensation autorisée pour {abs(client.solde):,.2f} DA"
                }
            
            elif action == 'REMBOURSER':
                # ✅ Agent a choisi de REMBOURSER en argent
                montant_remboursement = abs(client.solde)
                
                # TODO: Générer ordre de virement / chèque
                # RemboursementService.creer_ordre_remboursement(client, montant_remboursement)
                
                # Remettre solde à 0
                client.solde = Decimal('0.00')
                client.compensation_autorisee = False  # Pas de compensation (déjà remboursé)
                client.save()
                
                notification.statut = 'TRAITEE'
                notification.action_effectuee = 'REMBOURSE'
                notification.commentaire_traitement = f"Remboursement de {montant_remboursement:,.2f} DA effectué"
                notification.date_traitement = timezone.now()
                notification.save()
                
                resultat = {
                    'success': True,
                    'message': f"Remboursement de {montant_remboursement:,.2f} DA effectué"
                }
        
        # ========== NOTIFICATIONS MAINTENANCE AVANT (J-1) ==========
        elif notification.type_notification == 'MAINTENANCE_AVANT':
            vehicule = notification.vehicule
            
            if action == 'CONFIRMER_MAINTENANCE':
                # ✅ Confirmer que le véhicule ira en maintenance demain
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
            
            elif action == 'REPORTER_MAINTENANCE':
                # ✅ Reporter la maintenance (l'agent doit fournir nouvelle date)
                # Cette action sera gérée depuis la vue avec une nouvelle date
                notification.statut = 'TRAITEE'
                notification.action_effectuee = 'MAINTENANCE_REPORTEE'
                notification.date_traitement = timezone.now()
                # commentaire_traitement sera rempli depuis la vue avec la nouvelle date
                notification.save()
                
                resultat = {
                    'success': True,
                    'message': 'Maintenance reportée'
                }
        
        # ========== NOTIFICATIONS MAINTENANCE APRÈS (J+1, J+2...) ==========
        elif notification.type_notification == 'MAINTENANCE_APRES':
            vehicule = notification.vehicule
            
            if action == 'CONFIRMER_RETOUR':
                # ✅ Confirmer que le véhicule est revenu de maintenance
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
            
            elif action == 'PAS_ENCORE_RETOUR':
                # ✅ Le véhicule n'est pas encore revenu
                notification.statut = 'LUE'
                notification.save()
                
                resultat = {
                    'success': True,
                    'message': 'Notification marquée comme lue'
                }
        
        return resultat
    
    @staticmethod
    def reporter_maintenance_vehicule(vehicule, nouvelle_date, commentaire=None):
        """
        Permet à l'agent de reporter manuellement une maintenance
        
        Args:
            vehicule: Instance de Vehicule
            nouvelle_date: date object de la nouvelle DPR
            commentaire: Raison du report (optionnel)
        """
        from datetime import date
        from .models import Notification
        
        ancienne_date = vehicule.date_prochaine_revision
        
        VehiculeService.reporter_revision(vehicule, nouvelle_date)
        
        # Log dans une notification
        Notification.objects.create(
            type_notification='INFO',
            titre=f"Maintenance reportée - {vehicule.numero_immatriculation}",
            message=f"Date de prochaine révision modifiée de {ancienne_date.strftime('%d/%m/%Y')} "
                    f"à {nouvelle_date.strftime('%d/%m/%Y')}"
                    + (f"\nRaison : {commentaire}" if commentaire else ""),
            vehicule=vehicule,
            statut='LUE'
        )
    
    @staticmethod
    def marquer_comme_lue(notification_id):
        """
        Marque une notification comme lue (sans la traiter)
        """
        from .models import Notification
        
        notification = Notification.objects.get(id=notification_id)
        
        if notification.statut == 'NON_LUE':
            notification.statut = 'LUE'
            notification.save()
        
        return {'success': True}
    
"""
Utilitaire d'export PDF générique pour toutes les tables
"""
from reportlab.lib.pagesizes import A4 # type: ignore
from reportlab.lib import colors # type: ignore
from reportlab.lib.units import cm # type: ignore
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer # type: ignore
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle # type: ignore
from io import BytesIO
from datetime import datetime
from django.http import HttpResponse

def generer_pdf_liste(titre_document, headers, data_rows, nom_fichier_base):
    """
    Fonction générique pour générer un PDF professionnel (LISTE/TABLEAU)
    
    Args:
        titre_document (str): Titre principal du document (ex: "Liste des Clients")
        headers (list): Liste des en-têtes de colonnes (ex: ['Nom', 'Prénom', 'Téléphone'])
        data_rows (list of lists): Données du tableau (chaque ligne = liste de valeurs)
        nom_fichier_base (str): Nom de base du fichier (ex: "clients")
    
    Returns:
        HttpResponse: Réponse HTTP avec le PDF
    
    Exemple d'utilisation:
        headers = ['Nom', 'Prénom', 'Téléphone', 'Solde']
        data = [
            ['Benali', 'Ahmed', '0555123456', '5000 DA'],
            ['Kaci', 'Fatima', '0666789012', '-2000 DA'],
        ]
        return generer_pdf_liste(
            "Liste des Clients",
            headers,
            data,
            "clients"
        )
    """
    
    buffer = BytesIO()
    
    # ========== DOCUMENT ==========
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=2*cm,
        bottomMargin=2.5*cm,
        leftMargin=2*cm,
        rightMargin=2*cm,
    )
    
    styles = getSampleStyleSheet()
    elements = []
    
    # ========== STYLES ==========
    company_style = ParagraphStyle(
        'company_style',
        parent=styles['Normal'],
        fontSize=14,
        textColor=colors.HexColor("#2c3e50"),
    )
    
    small_grey = ParagraphStyle(
        'small_grey',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.grey,
    )
    
    title_style = ParagraphStyle(
        'title_style',
        parent=styles['Title'],
        alignment=1,  # centered
        fontSize=16,
    )
    
    # ========== HEADER ==========
    elements.append(Paragraph("<b>TransportPro</b>", company_style))
    elements.append(
        Paragraph(
            f"Extrait généré le : {datetime.now().strftime('%d/%m/%Y à %H:%M')}",
            small_grey
        )
    )
    elements.append(Spacer(1, 0.8*cm))
    
    # ========== MAIN TITLE ==========
    elements.append(
        Paragraph(f"<b>{titre_document}</b>", title_style)
    )
    elements.append(Spacer(1, 0.5*cm))
    
    # ========== TABLE ==========
    # Construire les données du tableau (en-têtes + lignes)
    table_data = [headers] + data_rows
    
    # Calculer la largeur des colonnes automatiquement
    nb_colonnes = len(headers)
    largeur_totale = 17 * cm  # Largeur utilisable (A4 - marges)
    largeur_colonne = largeur_totale / nb_colonnes
    col_widths = [largeur_colonne] * nb_colonnes
    
    table = Table(table_data, colWidths=col_widths)
    
    # Style du tableau
    table.setStyle(TableStyle([
        # En-tête
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        
        # Corps du tableau
        ('ROWBACKGROUNDS', (0, 1), (-1, -1),
         [colors.whitesmoke, colors.HexColor("#f5f6fa")]),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
        
        # Padding
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        
        # Grille
        ('GRID', (0, 0), (-1, -1), 0.4, colors.grey),
    ]))
    
    elements.append(table)
    
    # ========== FOOTER FUNCTION ==========
    def draw_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 9)
        footer_y = 1.3 * cm
        canvas.drawCentredString(A4[0] / 2, footer_y, "USTHB, Bab Ezzouar")
        canvas.drawCentredString(A4[0] / 2, footer_y - 0.45 * cm, "projetsysinfo@usthb.com")
        canvas.restoreState()
    
    # ========== BUILD PDF ==========
    doc.build(
        elements,
        onFirstPage=draw_footer,
        onLaterPages=draw_footer,
    )
    
    buffer.seek(0)
    
    # ========== RESPONSE ==========
    response = HttpResponse(buffer, content_type="application/pdf")
    nom_fichier = f"TransportPro_{nom_fichier_base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{nom_fichier}"'
    
    return response

def generer_pdf_fiche(titre_document, sections, nom_fichier_base, remarques=None):
    """
    Fonction générique pour générer un PDF professionnel (FICHE DÉTAILLÉE)
    
    Args:
        titre_document (str): Titre principal (ex: "Fiche Client - Ahmed Benali")
        sections (list of dict): Liste des sections à afficher
            Chaque section = {
                'titre': 'Nom de la section',
                'data': [['Label', 'Valeur'], ...]
            }
        nom_fichier_base (str): Nom de base du fichier (ex: "client_benali")
        remarques (str, optional): Texte de remarques à afficher à la fin
    
    Returns:
        HttpResponse: Réponse HTTP avec le PDF
    
    Exemple d'utilisation:
        sections = [
            {
                'titre': 'Informations Personnelles',
                'data': [
                    ['Nom', 'Benali'],
                    ['Prénom', 'Ahmed'],
                    ['Téléphone', '0555123456']
                ]
            },
            {
                'titre': 'Informations Financières',
                'data': [
                    ['Solde', '5000 DA']
                ]
            }
        ]
        return generer_pdf_fiche(
            "Fiche Client - Ahmed Benali",
            sections,
            "client_benali",
            remarques="Client fidèle depuis 2020"
        )
    """
    
    buffer = BytesIO()
    
    # ========== DOCUMENT ==========
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=2*cm,
        bottomMargin=2.5*cm,
        leftMargin=2*cm,
        rightMargin=2*cm,
    )
    
    styles = getSampleStyleSheet()
    elements = []
    
    # ========== STYLES ==========
    company_style = ParagraphStyle(
        'company_style',
        parent=styles['Normal'],
        fontSize=14,
        textColor=colors.HexColor("#2c3e50"),
    )
    
    small_grey = ParagraphStyle(
        'small_grey',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.grey,
    )
    
    title_style = ParagraphStyle(
        'title_style',
        parent=styles['Title'],
        alignment=1,  # centered
        fontSize=16,
    )
    
    section_title = ParagraphStyle(
        'section_title',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=colors.HexColor("#2c3e50"),
        spaceAfter=10,
    )
    
    # ========== HEADER ==========
    elements.append(Paragraph("<b>TransportPro</b>", company_style))
    elements.append(
        Paragraph(
            f"Extrait généré le : {datetime.now().strftime('%d/%m/%Y à %H:%M')}",
            small_grey
        )
    )
    elements.append(Spacer(1, 0.8*cm))
    
    # ========== MAIN TITLE ==========
    elements.append(
        Paragraph(f"<b>{titre_document}</b>", title_style)
    )
    elements.append(Spacer(1, 0.5*cm))
    
    # ========== SECTIONS ==========
    for section in sections:
        # Titre de la section
        elements.append(Paragraph(f"<b>{section['titre']}</b>", section_title))
        
        # Tableau de la section
        table = Table(section['data'], colWidths=[5*cm, 12*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#ecf0f1")),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.grey),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        elements.append(table)
        elements.append(Spacer(1, 0.5*cm))
    
    # ========== REMARQUES ==========
    if remarques:
        elements.append(Paragraph("<b>Remarques</b>", section_title))
        elements.append(Paragraph(remarques, styles['Normal']))
    
    # ========== FOOTER FUNCTION ==========
    def draw_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 9)
        footer_y = 1.3 * cm
        canvas.drawCentredString(A4[0] / 2, footer_y, "USTHB, Bab Ezzouar")
        canvas.drawCentredString(A4[0] / 2, footer_y - 0.45 * cm, "projetsysinfo@usthb.com")
        canvas.restoreState()
    
    # ========== BUILD PDF ==========
    doc.build(
        elements,
        onFirstPage=draw_footer,
        onLaterPages=draw_footer,
    )
    
    buffer.seek(0)
    
    # ========== RESPONSE ==========
    response = HttpResponse(buffer, content_type="application/pdf")
    nom_fichier = f"TransportPro_{nom_fichier_base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{nom_fichier}"'
    
    return response