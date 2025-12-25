from decimal import Decimal
from django.utils import timezone
from django.core.exceptions import ValidationError


class TourneeService:
    
    @staticmethod
    def traiter_tournee(tournee):
        ### Gère toute la logique d'une tournée
        
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
        ### Vérifie que chauffeur et véhicule sont disponibles
        if tournee.chauffeur.statut_disponibilite != 'DISPONIBLE':
            raise ValidationError(f"Chauffeur {tournee.chauffeur} non disponible")
        
        if tournee.vehicule.statut != 'DISPONIBLE':
            raise ValidationError(f"Véhicule {tournee.vehicule.numero_immatriculation} non disponible")
    
    @staticmethod
    def calculer_kilometrage_et_consommation(tournee):
        ### Calcule kilométrage parcouru et consommation
        tournee.kilometrage_parcouru = tournee.kilometrage_arrivee - tournee.kilometrage_depart
        
        if tournee.kilometrage_parcouru > 0:
            tournee.consommation_carburant = (
                Decimal(str(tournee.kilometrage_parcouru)) * 
                tournee.vehicule.consommation_moyenne / 100
            )
    
    @staticmethod
    def gerer_statuts_ressources(tournee):
        ### Gère les statuts du chauffeur et véhicule
        if tournee.statut in ['PREVUE', 'EN_COURS']:
            tournee.chauffeur.statut_disponibilite = 'EN_TOURNEE'
            tournee.vehicule.statut = 'EN_TOURNEE'
        
        elif tournee.statut == 'TERMINEE':
            tournee.chauffeur.statut_disponibilite = 'DISPONIBLE'
            tournee.vehicule.statut = 'DISPONIBLE'
            
            if tournee.kilometrage_arrivee:
                tournee.vehicule.kilometrage = tournee.kilometrage_arrivee
        
        tournee.chauffeur.save()
        tournee.vehicule.save()
