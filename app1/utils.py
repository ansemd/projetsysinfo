from datetime import datetime, timedelta
from datetime import date
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Sum



class TourneeService:
    
    @staticmethod
    def traiter_tournee(tournee):
        """Gère toute la logique d'une tournée"""
        
        # 1. Vérifier disponibilité (nouvelle tournée uniquement)
        if tournee.pk is None:
            TourneeService.verifier_disponibilite(tournee)
        
        # 2. Kilométrage départ
        if tournee.pk is None and not tournee.kilometrage_depart:
            tournee.kilometrage_depart = tournee.vehicule.kilometrage
        
        # 3. Calculs kilométrage et consommation
        if tournee.kilometrage_arrivee and tournee.kilometrage_depart:
            TourneeService.calculer_kilometrage_et_consommation(tournee)
        
        # 4. Gérer statuts ressources
        TourneeService.gerer_statuts_ressources(tournee)
        
        # 5. Vérifier si date départ atteinte
        if tournee.statut == 'PREVUE' and timezone.now() >= tournee.date_depart:
            tournee.statut = 'EN_COURS'
    
    @staticmethod
    def verifier_disponibilite(tournee):
        """Vérifie que chauffeur et véhicule sont disponibles"""
        if tournee.chauffeur.statut_disponibilite != 'DISPONIBLE':
            raise ValidationError(f"Chauffeur {tournee.chauffeur} non disponible")
        
        if tournee.vehicule.statut != 'DISPONIBLE':
            raise ValidationError(f"Véhicule {tournee.vehicule.numero_immatriculation} non disponible")
    
    @staticmethod
    def calculer_kilometrage_et_consommation(tournee):
        """Calcule kilométrage parcouru et consommation"""
        tournee.kilometrage_parcouru = tournee.kilometrage_arrivee - tournee.kilometrage_depart
        
        if tournee.kilometrage_parcouru > 0:
            tournee.consommation_carburant = (
                Decimal(str(tournee.kilometrage_parcouru)) * 
                tournee.vehicule.consommation_moyenne / 100
            )
    
    @staticmethod
    def gerer_statuts_ressources(tournee):
        """Gère les statuts du chauffeur, véhicule ET expéditions"""
        
        if tournee.statut in ['PREVUE', 'EN_COURS']:
            tournee.chauffeur.statut_disponibilite = 'EN_TOURNEE'
            tournee.vehicule.statut = 'EN_TOURNEE'
            
            # Si tournée passe EN_COURS → mettre expéditions EN_TRANSIT
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
        
        elif tournee.statut == 'TERMINEE':
            tournee.chauffeur.statut_disponibilite = 'DISPONIBLE'
            tournee.vehicule.statut = 'DISPONIBLE'
            
            if tournee.kilometrage_arrivee:
                tournee.vehicule.kilometrage = tournee.kilometrage_arrivee
            
            # Tournée terminée → marquer expéditions comme LIVREES par défaut
            from .models import TrackingExpedition
            for exp in tournee.expeditions.all():
                if exp.statut == 'EN_TRANSIT':
                    exp.statut = 'LIVRE'
                    exp.date_livraison_reelle = timezone.now().date()
                    exp.save(update_fields=['statut', 'date_livraison_reelle'])
                    
                    TrackingService.creer_suivi(
                        exp,
                        'LIVRE',
                        f"Colis livré à {exp.nom_destinataire}"
                    )
        
        tournee.chauffeur.save()
        tournee.vehicule.save()

class ExpeditionService:
    """
    Service gérant les opérations sur les expéditions :
    - Validation et calculs
    - Affectation intelligente de tournées
    - Annulation d'expédition avec remboursement proportionnel
    - Notifications
    """
    
    @staticmethod
    def valider_expedition(expedition):
        """Valide tous les champs de l'expédition"""
        
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
        """Calcule le montant total via Tarification"""
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
        """Cherche et affecte automatiquement la meilleure tournée"""
        from .models import Tournee
        
        tournees_compatibles = Tournee.objects.filter(
            zone_cible=expedition.destination.zone_logistique,
            statut='PREVUE',
            date_depart__gte=timezone.now()
        ).order_by('date_depart')
        
        for tournee in tournees_compatibles:
            totaux = tournee.expeditions.aggregate(poids_total=Sum('poids'))
            poids_actuel = totaux['poids_total'] or 0
            
            if float(poids_actuel) + float(expedition.poids) <= float(tournee.vehicule.capacite_poids):
                expedition.tournee = tournee
                return
        
        ExpeditionService.creer_nouvelle_tournee(expedition)
    
    @staticmethod
    def creer_nouvelle_tournee(expedition):
        """Crée une nouvelle tournée pour l'expédition STANDARD"""
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
    
    @staticmethod
    def creer_tournee_express(expedition):
        """Crée une tournée privée pour une expédition EXPRESS"""
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
        """Calcule la date de livraison prévue"""
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
    def annuler_expedition(expedition):
        """Annuler une expédition avec logique de remboursement proportionnel"""
        from .models import Facture, Paiement
        from datetime import date
        from django.db.models import Sum
        
        if expedition.statut == 'ANNULEE':
            raise ValidationError("Cette expédition est déjà annulée")
        
        if expedition.statut not in ['EN_ATTENTE', 'COLIS_CREE']:
            raise ValidationError(
                "Impossible d'annuler : l'expédition est déjà en transit, livrée ou en échec"
            )
        
        if expedition.tournee and expedition.tournee.statut != 'PREVUE':
            raise ValidationError(
                "Impossible d'annuler : la tournée est déjà en cours ou terminée"
            )
        
        if expedition.tournee and date.today() >= expedition.tournee.date_depart.date():
            raise ValidationError(
                "Impossible d'annuler : la date de départ de la tournée est dépassée"
            )
        
        facture = expedition.factures.filter(
            statut__in=['IMPAYEE', 'PARTIELLEMENT_PAYEE', 'PAYEE', 'EN_RETARD']
        ).first()
        
        if not facture:
            # Pas de facture → suppression simple
            expedition.suivis.all().delete()
            super(type(expedition), expedition).delete()
            return
        
        montant_exp_ht = expedition.montant_total
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
        
        expedition.client.solde -= montant_paye_pour_exp
        expedition.client.solde -= montant_non_paye_pour_exp
        expedition.client.save()
        
        facture.expeditions.remove(expedition)
        
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
        
        # Supprimer les trackings
        expedition.suivis.all().delete()
        
        # Supprimer l'expédition (appel direct pour éviter boucle)
        super(type(expedition), expedition).delete()
    
    
    @staticmethod
    def envoyer_notification_destinataire(expedition):
        """Placeholder pour notifications"""
        pass

class VehiculeService:
    
    @staticmethod
    def gerer_revision(vehicule):
        """Gère les révisions du véhicule avec déblocage automatique"""
        
        # 1. Première fois : calculer date prochaine révision
        if vehicule.date_derniere_revision and not vehicule.date_prochaine_revision:
            vehicule.date_prochaine_revision = vehicule.date_derniere_revision + timedelta(days=180)
        
        # 2. Vérifier le statut selon la date
        if vehicule.date_prochaine_revision:
            jours_restants = (vehicule.date_prochaine_revision - date.today()).days
            
            # CAS 1 : Révision proche (≤ 2 jours) → Bloquer
            if jours_restants <= 2 and jours_restants >= 0 and vehicule.statut == 'DISPONIBLE':
                vehicule.statut = 'EN_MAINTENANCE'
            
            # CAS 2 : Date de révision dépassée → Débloquer automatiquement
            elif jours_restants < 0 and vehicule.statut == 'EN_MAINTENANCE':
                # Automatiquement confirmer la révision
                vehicule.date_derniere_revision = vehicule.date_prochaine_revision
                vehicule.date_prochaine_revision = vehicule.date_derniere_revision + timedelta(days=180)
                vehicule.statut = 'DISPONIBLE'
    
    @staticmethod
    def confirmer_revision(vehicule):
        """
        Confirme qu'une révision a été effectuée (action manuelle)
        """
        vehicule.date_derniere_revision = vehicule.date_prochaine_revision
        vehicule.date_prochaine_revision = vehicule.date_derniere_revision + timedelta(days=180)
        
        if vehicule.statut == 'EN_MAINTENANCE':
            vehicule.statut = 'DISPONIBLE'
        
        vehicule.save()
    
    @staticmethod
    def reporter_revision(vehicule, nouvelle_date):
        """Agent saisit manuellement une nouvelle date"""
        vehicule.date_prochaine_revision = nouvelle_date
        
        jours_restants = (nouvelle_date - date.today()).days
        
        if jours_restants > 2 and vehicule.statut == 'EN_MAINTENANCE':
            vehicule.statut = 'DISPONIBLE'
        
        vehicule.save()

class TrackingService:
    
    @staticmethod
    def creer_suivi(expedition, statut_etape, commentaire=None):
        """Crée une nouvelle étape de suivi"""
        from .models import TrackingExpedition
        
        TrackingExpedition.objects.create(
            expedition=expedition,
            statut_etape=statut_etape,
            commentaire=commentaire
        )

# ========== SECTION 3 : SERVICES FACTURATION ==========

class FacturationService:
    """
    Service gérant toutes les opérations liées à la facturation :
    - Calcul des montants (HT, TVA, TTC)
    - Création et mise à jour des factures
    - Gestion des paiements
    - Annulation de factures
    """
    
    @staticmethod
    def calculer_montants_facture(facture):
        """
        Calculer les montants HT, TVA et TTC d'une facture
        en fonction des expéditions qu'elle contient
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
        Calculer le montant restant à payer pour une facture
        = Montant TTC - Somme des paiements valides
        """
        from django.db.models import Sum
        
        total_paye = facture.paiements.filter(statut='VALIDE').aggregate(
            total=Sum('montant_paye')
        )['total'] or Decimal('0.00')
        
        return facture.montant_ttc - total_paye
    
    
    @staticmethod
    def mettre_a_jour_statut_facture(facture):
        """
        Mettre à jour automatiquement le statut de la facture selon :
        - Le montant payé
        - La date d'échéance
        
        Statuts possibles :
        - IMPAYEE : Aucun paiement, dans les délais
        - PARTIELLEMENT_PAYEE : Paiement partiel, dans les délais
        - PAYEE : Paiement complet
        - EN_RETARD : Impayée ou partielle, échéance dépassée
        - ANNULEE : Facture annulée
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
            # Vérifier si en retard
            if date.today() > facture.date_echeance:
                facture.statut = 'EN_RETARD'
            else:
                facture.statut = 'PARTIELLEMENT_PAYEE'
        
        # Sinon impayée
        else:
            # Vérifier si en retard
            if date.today() > facture.date_echeance:
                facture.statut = 'EN_RETARD'
            else:
                facture.statut = 'IMPAYEE'
        
        facture.save()
    
    
    @staticmethod
    def gerer_facture_expedition(expedition):
        """
        Créer une nouvelle facture OU ajouter l'expédition à une facture existante.
        
        Logique de regroupement :
        - Si une facture IMPAYEE ou PARTIELLEMENT_PAYEE existe AUJOURD'HUI pour ce client
          → Ajouter l'expédition à cette facture
        - Sinon → Créer une nouvelle facture
        
        Cette logique permet de regrouper toutes les expéditions d'un client
        créées le même jour dans une seule facture.
        """
        from datetime import date, timedelta
        from .models import Facture
        
        client = expedition.client
        aujourd_hui = date.today()
        
        # Chercher une facture existante pour ce client, créée aujourd'hui, non payée
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
            
            # Mettre à jour le statut de la facture
            FacturationService.mettre_a_jour_statut_facture(facture_du_jour)
            
            return facture_du_jour
        
        else:
            # CRÉER une NOUVELLE facture
            facture = Facture.objects.create(
                client=client,
                date_echeance=aujourd_hui + timedelta(days=30),  # Échéance dans 30 jours
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
            
            return facture
    
    
    @staticmethod
    def enregistrer_paiement(facture, montant, mode_paiement, reference=None, remarques=None):
        """
        Enregistrer un paiement pour une facture.
        
        Validations :
        - La facture ne doit pas être annulée
        - La facture ne doit pas être déjà payée
        - Le montant doit être > 0
        - Le montant ne doit pas dépasser le montant restant
        
        Actions :
        - Créer l'objet Paiement
        - Diminuer le solde du client
        - Mettre à jour le statut de la facture
        """
        from .models import Paiement
        # Vérifier que la facture n'est pas annulée
        if facture.statut == 'ANNULEE':
            raise ValidationError("Impossible de payer une facture annulée")
        
        # Vérifier que la facture n'est pas déjà payée
        if facture.statut == 'PAYEE':
            raise ValidationError("Cette facture est déjà entièrement payée")
        
        montant_restant = FacturationService.calculer_montant_restant(facture)
        
        # Vérifier que le montant restant est > 0 (sécurité supplémentaire)
        if montant_restant <= 0:
            raise ValidationError("Cette facture est déjà entièrement payée")
        
        # Vérifier que le montant ne dépasse pas le restant
        if montant > montant_restant:
            raise ValidationError(
                f"Le montant ({montant} DA) dépasse le montant restant ({montant_restant} DA)"
            )
        
        # Vérifier que le montant est positif
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
        Annuler une facture contenant UNE SEULE expédition.
        
        Pour les factures contenant plusieurs expéditions,
        il faut annuler les expéditions une par une (voir ExpeditionService.annuler_expedition)
        
        Actions :
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

# ========== SECTION 4 : SERVICES INCIDENTS ==========

class IncidentService:
    """
    Service gérant toutes les opérations liées aux incidents :
    - Création et traitement des incidents
    - Mise à jour automatique des statuts d'expéditions
    - Génération d'alertes
    - Statistiques et analyses
    """
    
    @staticmethod
    def traiter_nouvel_incident(incident):
        """
        Traite un nouvel incident : mise à jour des statuts, alertes, etc.
        """
        from .models import TrackingExpedition
        from django.utils import timezone
        
        # Mise à jour du statut de l'expédition concernée
        if incident.expedition:
            if incident.type_incident in ['PERTE', 'ENDOMMAGEMENT']:
                # Incidents graves → marquer comme ÉCHEC
                incident.expedition.statut = 'ECHEC'
                incident.expedition.save(update_fields=['statut'])
                
                # Créer un suivi
                TrackingService.creer_suivi(
                    incident.expedition,
                    'ECHEC',
                    f"Incident: {incident.get_type_incident_display()} - {incident.titre}"
                )
            
            elif incident.type_incident == 'RETARD':
                # Pour les retards, ajouter simplement un suivi
                TrackingService.creer_suivi(
                    incident.expedition,
                    incident.expedition.statut,  # Garder le statut actuel
                    f"Retard signalé: {incident.description[:100]}"
                )
        
        # Définir la sévérité automatiquement selon le type
        if incident.type_incident in ['PERTE', 'ACCIDENT']:
            incident.severite = 'CRITIQUE'
            incident.alerte_direction = True
            incident.alerte_client = True
        elif incident.type_incident in ['ENDOMMAGEMENT', 'PROBLEME_TECHNIQUE']:
            incident.severite = 'ELEVEE'
            incident.alerte_direction = True
        elif incident.type_incident == 'RETARD':
            incident.severite = 'MOYENNE'
        
        incident.save(update_fields=['severite', 'alerte_direction', 'alerte_client'])
        
        # Générer les alertes si nécessaire
        if incident.alerte_direction:
            IncidentService.envoyer_alerte_direction(incident)
        
        if incident.alerte_client and incident.expedition:
            IncidentService.envoyer_alerte_client(incident)
    
    @staticmethod
    def resoudre_incident(incident, solution, agent):
        """
        Marque un incident comme résolu
        """
        from django.utils import timezone
        
        incident.statut = 'RESOLU'
        incident.actions_entreprises = solution
        incident.agent_responsable = agent
        incident.date_resolution = timezone.now()
        incident.save()
    
    @staticmethod
    def cloturer_incident(incident):
        """
        Clôture définitivement un incident
        """
        if incident.statut != 'RESOLU':
            raise ValidationError("Un incident doit être résolu avant d'être clôturé")
        
        incident.statut = 'CLOS'
        incident.save()

    @staticmethod
    def envoyer_alerte_direction(incident):
        """
        Placeholder pour l'envoi d'alertes à la direction
        Dans une vraie application : envoi d'email, notification système, SMS, etc.
        """
        # TODO: Implémenter l'envoi réel d'alertes
        print(f" ALERTE DIRECTION: Incident {incident.numero_incident} - {incident.titre}")
        print(f" Sévérité: {incident.severite}")
        print(f" Type: {incident.get_type_incident_display()}")
        if incident.expedition:
            print(f" Expédition concernée: {incident.expedition.get_numero_expedition()}")
        if incident.tournee:
            print(f" Tournée concernée: Tournée #{incident.tournee.id}")
    
    @staticmethod
    def envoyer_alerte_client(incident):
        """
        Placeholder pour l'envoi d'alertes au client
        """
        # TODO: Implémenter l'envoi réel d'alertes (email, SMS)
        client = incident.expedition.client
        print(f" ALERTE CLIENT: {client.prenom} {client.nom}")
        print(f" Incident sur votre expédition {incident.expedition.get_numero_expedition()}")
        print(f" Type: {incident.get_type_incident_display()}")
        print(f" Description: {incident.description[:100]}")
    
    @staticmethod
    def statistiques_incidents(date_debut=None, date_fin=None):
        """
        Génère des statistiques sur les incidents
        """
        from django.db.models import Count, Avg, Sum, Q
        from datetime import datetime, timedelta
        from .models import Incident
        
        # Définir la période par défaut (30 derniers jours)
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
            'taux_resolution': incidents.filter(
                statut__in=['RESOLU', 'CLOS']
            ).count() / incidents.count() * 100 if incidents.count() > 0 else 0,
        }
        
        return stats
    
    @staticmethod
    def incidents_par_chauffeur():
        """
        Analyse des incidents par chauffeur
        """
        from django.db.models import Count
        from .models import Incident
        
        return Incident.objects.filter(
            tournee__isnull=False
        ).values(
            'tournee__chauffeur__prenom',
            'tournee__chauffeur__nom'
        ).annotate(
            nb_incidents=Count('id')
        ).order_by('-nb_incidents')


# ========== SECTION 5 : SERVICES RÉCLAMATIONS ==========

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
        from .models import HistoriqueReclamation
        
        # Définir la priorité automatiquement selon la nature
        if reclamation.nature in ['COLIS_PERDU', 'COLIS_ENDOMMAGE', 'REMBOURSEMENT']:
            reclamation.priorite = 'HAUTE'
        elif reclamation.nature == 'RETARD_LIVRAISON':
            reclamation.priorite = 'NORMALE'
        
        reclamation.save(update_fields=['priorite'])
        
        # Créer une entrée dans l'historique
        HistoriqueReclamation.objects.create(
            reclamation=reclamation,
            action="Réclamation créée",
            auteur="Système",
            details=f"Réclamation créée par le client {reclamation.client}",
            nouveau_statut='OUVERTE'
        )
        
        # Notification (placeholder)
        ReclamationService.notifier_nouvelle_reclamation(reclamation)
    
    @staticmethod
    def assigner_agent(reclamation, agent_nom):
        """
        Assigne un agent à une réclamation
        """
        from django.utils import timezone
        from .models import HistoriqueReclamation
        
        ancien_agent = reclamation.agent_responsable
        
        reclamation.agent_responsable = agent_nom
        reclamation.date_assignation = timezone.now()
        reclamation.statut = 'EN_COURS'
        reclamation.save()
        
        # Historique
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
        
        # Historique
        HistoriqueReclamation.objects.create(
            reclamation=reclamation,
            action="Réponse envoyée",
            auteur=auteur,
            details=f"Réponse: {reponse[:100]}...",
            ancien_statut=ancien_statut,
            nouveau_statut='EN_ATTENTE_CLIENT'
        )
        
        # Notifier le client (placeholder)
        ReclamationService.notifier_client_reponse(reclamation)
    
    @staticmethod
    def resoudre_reclamation(reclamation, auteur, accorder_compensation=False, montant_compensation=0):
        """
        Marque une réclamation comme résolue
        """
        from django.utils import timezone
        from .models import HistoriqueReclamation
        
        ancien_statut = reclamation.statut
        
        reclamation.statut = 'RESOLUE'
        reclamation.date_resolution = timezone.now()
        reclamation.compensation_accordee = accorder_compensation
        reclamation.montant_compensation = Decimal(str(montant_compensation))
        reclamation.save()
        
        # Calculer le délai de traitement
        ReclamationService.calculer_delai_traitement(reclamation)
        
        # Historique
        HistoriqueReclamation.objects.create(
            reclamation=reclamation,
            action="Réclamation résolue",
            auteur=auteur,
            details=f"Compensation: {montant_compensation} DA" if accorder_compensation else "Aucune compensation",
            ancien_statut=ancien_statut,
            nouveau_statut='RESOLUE'
        )
        
        # Si compensation accordée, créditer le client
        if accorder_compensation and montant_compensation > 0:
            reclamation.client.solde -= Decimal(str(montant_compensation))
            reclamation.client.save()
    
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
        
        # Historique
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
        reclamation.save()
        
        # Historique
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
            reclamation.save(update_fields=['delai_traitement_jours'])
    
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
        
        # Historique
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
        
        # Définir la période par défaut (30 derniers jours)
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
    
    @staticmethod
    def notifier_nouvelle_reclamation(reclamation):
        """
        Placeholder pour notification de nouvelle réclamation
        """
        # TODO: Implémenter notifications réelles
        print(f" NOUVELLE RÉCLAMATION: {reclamation.numero_reclamation}")
        print(f" Client: {reclamation.client}")
        print(f" Nature: {reclamation.get_nature_display()}")
        print(f" Priorité: {reclamation.priorite}")
    
    @staticmethod
    def notifier_client_reponse(reclamation):
        """
        Placeholder pour notification au client
        """
        # TODO: Implémenter envoi email/SMS au client
        print(f" Notification envoyée au client {reclamation.client}")
        print(f" Réclamation: {reclamation.numero_reclamation}")
        print(f" Réponse disponible")