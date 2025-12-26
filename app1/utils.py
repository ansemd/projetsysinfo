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
    
    @staticmethod
    def avant_sauvegarde(expedition):
        """Appelé avant save() - Toute la logique de validation et calculs"""
        
        # 1. Validations
        ExpeditionService.valider_expedition(expedition)
        
        # 2. Calculer montant (toujours, même en modification)
        ExpeditionService.calculer_montant(expedition)
        
        # 3. Affectation tournée (nouvelle expédition uniquement)
        if expedition.pk is None:
            if expedition.type_service.type_service == 'EXPRESS':
                ExpeditionService.creer_tournee_express(expedition)
            else:
                ExpeditionService.affecter_tournee_intelligente(expedition)
        
        # 4. Calculer date livraison (toujours si tournée existe)
        if expedition.tournee:
            ExpeditionService.calculer_date_livraison(expedition)
            
            # Mettre à jour statut selon tournée
            if expedition.tournee.statut == 'EN_COURS':
                expedition.statut = 'EN_TRANSIT'
            elif expedition.tournee.statut == 'PREVUE':
                expedition.statut = 'EN_ATTENTE'
    
    @staticmethod
    def avant_suppression(expedition):
        """Appelé avant delete() - Vérifier qu'on peut supprimer"""
        if expedition.tournee and expedition.tournee.statut != 'PREVUE':
            raise ValidationError(
                "Impossible de supprimer : la tournée est déjà en cours ou terminée"
            )
    
    @staticmethod
    def valider_expedition(expedition):
        """Valide tous les champs de l'expédition"""
        
        # Validation poids
        if expedition.poids <= 0:
            raise ValidationError({'poids': "Le poids doit être supérieur à 0"})
        
        # Vérifier modification si tournée en cours/terminée
        if expedition.pk:  # Modification d'une expédition existante
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
            volume = expedition.volume or 0  # Si volume null, utiliser 0
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
        
        # Chercher tournées compatibles (futures uniquement)
        tournees_compatibles = Tournee.objects.filter(
            zone_cible=expedition.destination.zone_logistique,
            statut='PREVUE',
            date_depart__gte=timezone.now()  # Futures uniquement
        ).order_by('date_depart')
        
        # Tester chaque tournée
        for tournee in tournees_compatibles:
            totaux = tournee.expeditions.aggregate(poids_total=Sum('poids'))
            poids_actuel = totaux['poids_total'] or 0
            
            if float(poids_actuel) + float(expedition.poids) <= float(tournee.vehicule.capacite_poids):
                expedition.tournee = tournee
                return
        
        # Aucune tournée compatible → créer nouvelle
        ExpeditionService.creer_nouvelle_tournee(expedition)
    
    @staticmethod
    def creer_nouvelle_tournee(expedition):
        """Crée une nouvelle tournée pour l'expédition STANDARD"""
        from .models import Tournee, Chauffeur, Vehicule
        
        # Trouver chauffeur et véhicule disponibles
        chauffeur = Chauffeur.objects.filter(statut_disponibilite='DISPONIBLE').first()
        vehicule = Vehicule.objects.filter(statut='DISPONIBLE').first()
        
        if not chauffeur or not vehicule:
            raise ValidationError(
                "⚠️ Aucune tournée compatible et aucun chauffeur/véhicule disponible. "
                "L'expédition sera créée sans tournée. Veuillez l'affecter manuellement plus tard."
            )
        
        # Déterminer le délai selon la zone
        zone = expedition.destination.zone_logistique
        if zone == 'CENTRE':
            jours_delai = 1  # Lendemain
        elif zone in ['EST', 'OUEST']:
            jours_delai = 2  # Après 2 jours
        elif zone == 'SUD':
            jours_delai = 3  # Après 3 jours
        else:
            jours_delai = 1  # Par défaut
        
        # Calculer date de départ
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
        
        # Trouver chauffeur et véhicule disponibles
        chauffeur = Chauffeur.objects.filter(statut_disponibilite='DISPONIBLE').first()
        vehicule = Vehicule.objects.filter(statut='DISPONIBLE').first()
        
        if not chauffeur or not vehicule:
            raise ValidationError(
                "Aucun chauffeur ou véhicule disponible pour une expédition EXPRESS. "
                "Veuillez attendre ou passer en STANDARD."
            )
        
        # Déterminer date de départ
        maintenant = timezone.now()
        if maintenant.hour < 14:
            date_depart = maintenant
        else:
            date_depart = maintenant + timedelta(days=1)
            date_depart = date_depart.replace(hour=8, minute=0, second=0)
        
        # Créer la tournée privée EXPRESS
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
        
        # Récupérer le délai depuis Tarification
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
        """Envoie un email au destinataire 1 jour avant le départ de la tournée"""
        from django.core.mail import send_mail
        from django.conf import settings
        
        if not expedition.tournee or not expedition.date_livraison_prevue:
            return
        
        jours_restants = (expedition.date_livraison_prevue - timezone.now().date()).days
        
        sujet = f"Votre colis arrive bientôt - Expédition #{expedition.id}"
        message = f"""
Bonjour {expedition.nom_destinataire},

Votre colis est en route !

📦 Numéro d'expédition : #{expedition.id}
📍 Destination : {expedition.destination.ville}
📅 Date de livraison prévue : {expedition.date_livraison_prevue.strftime('%d/%m/%Y')}
⏰ Arrivée estimée dans : {jours_restants} jour(s)

Description : {expedition.description or 'Non spécifiée'}

Merci de votre confiance !

L'équipe Transport Express
        """
        
        try:
            send_mail(
                sujet,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [expedition.email_destinataire],
                fail_silently=False,
            )
        except Exception as e:
            print(f"Erreur envoi email : {e}")

class VehiculeService:
    
    @staticmethod
    def gerer_revision(vehicule):
        """Gère les révisions du véhicule"""
        
        # 1. Première fois : calculer date prochaine révision
        if vehicule.date_derniere_revision and not vehicule.date_prochaine_revision:
            vehicule.date_prochaine_revision = vehicule.date_derniere_revision + timedelta(days=180)
        
        # 2. Vérifier si révision proche (< 2 jours) → bloquer véhicule
        if vehicule.date_prochaine_revision:
            jours_restants = (vehicule.date_prochaine_revision - date.today()).days
            
            # Bloquer SEULEMENT si le véhicule est DISPONIBLE
            if jours_restants <= 2 and vehicule.statut == 'DISPONIBLE':
                vehicule.statut = 'EN_MAINTENANCE'
    
    @staticmethod
    def confirmer_revision(vehicule):
        """
        Confirme qu'une révision a été effectuée
        La date prochaine devient la date dernière
        """
        # L'ancienne "prochaine révision" devient "dernière révision"
        vehicule.date_derniere_revision = vehicule.date_prochaine_revision
        
        # Calculer nouvelle prochaine révision (+6 mois)
        vehicule.date_prochaine_revision = vehicule.date_derniere_revision + timedelta(days=180)
        
        # Remettre disponible SEULEMENT si c'était EN_MAINTENANCE
        if vehicule.statut == 'EN_MAINTENANCE':
            vehicule.statut = 'DISPONIBLE'
        
        vehicule.save()
    
    @staticmethod
    def reporter_revision(vehicule, nouvelle_date):
        """Agent saisit manuellement une nouvelle date"""
        vehicule.date_prochaine_revision = nouvelle_date
        
        # Vérifier si on peut remettre disponible
        jours_restants = (nouvelle_date - date.today()).days
        
        # Remettre disponible SEULEMENT si EN_MAINTENANCE et délai > 2 jours
        if jours_restants > 2 and vehicule.statut == 'EN_MAINTENANCE':
            vehicule

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