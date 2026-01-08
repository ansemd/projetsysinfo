from django.db.models import Count, Sum, Avg, Q, F
from django.db.models.functions import TruncMonth, TruncYear
from datetime import datetime, timedelta
from decimal import Decimal
from app1.models import Expedition, Tournee, Client, Destination, Chauffeur, Incident


class AnalyticsService:
    """
    Service pour les analyses et statistiques avancées
    """

    @staticmethod
    def evolution_expeditions(annee_debut, annee_fin=None):
        """
        Calcule l'évolution du nombre d'expéditions sur plusieurs années
        Returns: {
            'par_mois': [...],  # Données mensuelles
            'par_annee': [...], # Données annuelles
            'taux_evolution': 15.5  # Pourcentage d'évolution
        }
        """
        if not annee_fin:
            annee_fin = annee_debut
        
        # Données mensuelles
        expeditions_mois = Expedition.objects.filter(
            date_creation__year__gte=annee_debut,
            date_creation__year__lte=annee_fin
        ).annotate(
            mois=TruncMonth('date_creation')
        ).values('mois').annotate(
            nombre=Count('id'),
            ca=Sum('montant_total')
        ).order_by('mois')
        
        # Données annuelles
        expeditions_annee = Expedition.objects.filter(
            date_creation__year__gte=annee_debut,
            date_creation__year__lte=annee_fin
        ).annotate(
            annee=TruncYear('date_creation')
        ).values('annee').annotate(
            nombre=Count('id'),
            ca=Sum('montant_total')
        ).order_by('annee')
        
        # Calculer le taux d'évolution
        taux_evolution = 0
        if len(expeditions_annee) >= 2:
            premiere_annee = expeditions_annee[0]['nombre']
            derniere_annee = expeditions_annee[-1]['nombre']
            if premiere_annee > 0:
                taux_evolution = ((derniere_annee - premiere_annee) / premiere_annee) * 100
        
        return {
            'par_mois': list(expeditions_mois),
            'par_annee': list(expeditions_annee),
            'taux_evolution': round(taux_evolution, 2)
        }
    
    @staticmethod
    def evolution_chiffre_affaires(annee_debut, annee_fin=None):
        """
        Calcule l'évolution du chiffre d'affaires
        """
        if not annee_fin:
            annee_fin = annee_debut
        
        ca_mois = Expedition.objects.filter(
            date_creation__year__gte=annee_debut,
            date_creation__year__lte=annee_fin
        ).annotate(
            mois=TruncMonth('date_creation')
        ).values('mois').annotate(
            ca_ht=Sum('montant_total'),
            ca_ttc=Sum('montant_total') * Decimal('1.19')  # Avec TVA 19%
        ).order_by('mois')
        
        ca_annee = Expedition.objects.filter(
            date_creation__year__gte=annee_debut,
            date_creation__year__lte=annee_fin
        ).annotate(
            annee=TruncYear('date_creation')
        ).values('annee').annotate(
            ca_ht=Sum('montant_total'),
            ca_ttc=Sum('montant_total') * Decimal('1.19')
        ).order_by('annee')
        
        # Taux d'évolution CA
        taux_evolution_ca = 0
        if len(ca_annee) >= 2:
            premiere = float(ca_annee[0]['ca_ttc'] or 0)
            derniere = float(ca_annee[-1]['ca_ttc'] or 0)
            if premiere > 0:
                taux_evolution_ca = ((derniere - premiere) / premiere) * 100
        
        return {
            'par_mois': list(ca_mois),
            'par_annee': list(ca_annee),
            'taux_evolution': round(taux_evolution_ca, 2)
        }
    
    @staticmethod
    def top_clients(limite=10, annee=None):
        """
        Retourne les meilleurs clients (par volume ou valeur)
        """
        expeditions = Expedition.objects.all()
        
        if annee:
            expeditions = expeditions.filter(date_creation__year=annee)
        
        top_volume = expeditions.values(
            'client__id',
            'client__prenom',
            'client__nom',
            'client__telephone'
        ).annotate(
            nb_expeditions=Count('id'),
            ca_total=Sum('montant_total')
        ).order_by('-nb_expeditions')[:limite]
        
        top_valeur = expeditions.values(
            'client__id',
            'client__prenom',
            'client__nom',
            'client__telephone'
        ).annotate(
            nb_expeditions=Count('id'),
            ca_total=Sum('montant_total')
        ).order_by('-ca_total')[:limite]
        
        return {
            'par_volume': list(top_volume),
            'par_valeur': list(top_valeur)
        }
    
    @staticmethod
    def destinations_populaires(limite=10, annee=None):
        """
        Retourne les destinations les plus sollicitées
        """
        expeditions = Expedition.objects.all()
        
        if annee:
            expeditions = expeditions.filter(date_creation__year=annee)
        
        destinations = expeditions.values(
            'destination__ville',
            'destination__wilaya',
            'destination__zone_logistique'
        ).annotate(
            nb_expeditions=Count('id'),
            ca_total=Sum('montant_total')
        ).order_by('-nb_expeditions')[:limite]
        
        return list(destinations)
    
    @staticmethod
    def evolution_tournees(annee_debut, annee_fin=None):
        """
        Calcule l'évolution du nombre de tournées
        """
        if not annee_fin:
            annee_fin = annee_debut
        
        tournees_mois = Tournee.objects.filter(
            date_depart__year__gte=annee_debut,
            date_depart__year__lte=annee_fin
        ).annotate(
            mois=TruncMonth('date_depart')
        ).values('mois').annotate(
            nombre=Count('id')
        ).order_by('mois')
        
        tournees_annee = Tournee.objects.filter(
            date_depart__year__gte=annee_debut,
            date_depart__year__lte=annee_fin
        ).annotate(
            annee=TruncYear('date_depart')
        ).values('annee').annotate(
            nombre=Count('id')
        ).order_by('annee')
        
        # Taux d'évolution
        taux_evolution = 0
        if len(tournees_annee) >= 2:
            premiere = tournees_annee[0]['nombre']
            derniere = tournees_annee[-1]['nombre']
            if premiere > 0:
                taux_evolution = ((derniere - premiere) / premiere) * 100
        
        return {
            'par_mois': list(tournees_mois),
            'par_annee': list(tournees_annee),
            'taux_evolution': round(taux_evolution, 2)
        }
    
    @staticmethod
    def taux_reussite_livraisons(annee=None):
        """
        Calcule le taux de réussite des livraisons
        Returns: {
            'livrees': 850,
            'echecs': 50,
            'en_cours': 100,
            'taux_reussite': 94.4
        }
        """
        expeditions = Expedition.objects.all()
        
        if annee:
            expeditions = expeditions.filter(date_creation__year=annee)
        
        total = expeditions.count()
        livrees = expeditions.filter(statut='LIVRE').count()
        echecs = expeditions.filter(statut='ECHEC').count()
        en_cours = expeditions.filter(statut__in=['EN_ATTENTE', 'EN_TRANSIT']).count()
        
        taux_reussite = (livrees / total * 100) if total > 0 else 0
        
        return {
            'total': total,
            'livrees': livrees,
            'echecs': echecs,
            'en_cours': en_cours,
            'taux_reussite': round(taux_reussite, 2),
            'taux_echec': round((echecs / total * 100) if total > 0 else 0, 2)
        }
    
    @staticmethod
    def top_chauffeurs(limite=10, annee=None):
        """
        Retourne les meilleurs chauffeurs par performance
        """
        tournees = Tournee.objects.filter(statut='TERMINEE')
        
        if annee:
            tournees = tournees.filter(date_depart__year=annee)
        
        chauffeurs = tournees.values(
            'chauffeur__id',
            'chauffeur__prenom',
            'chauffeur__nom'
        ).annotate(
            nb_tournees=Count('id'),
            km_total=Sum('kilometrage_parcouru'),
            nb_livraisons=Count('expeditions', filter=Q(expeditions__statut='LIVRE')),
            nb_echecs=Count('expeditions', filter=Q(expeditions__statut='ECHEC'))
        ).order_by('-nb_tournees')[:limite]
        
        # Calculer le taux de réussite pour chaque chauffeur
        for chauffeur in chauffeurs:
            total_livraisons = chauffeur['nb_livraisons'] + chauffeur['nb_echecs']
            if total_livraisons > 0:
                chauffeur['taux_reussite'] = round(
                    (chauffeur['nb_livraisons'] / total_livraisons) * 100, 2
                )
            else:
                chauffeur['taux_reussite'] = 0
        
        return list(chauffeurs)
    
    @staticmethod
    def zones_incidents(limite=10, annee=None):
        """
        Retourne les zones avec le plus d'incidents
        """
        incidents = Incident.objects.filter(expedition__isnull=False)
        
        if annee:
            incidents = incidents.filter(date_heure_incident__year=annee)
        
        zones = incidents.values(
            'expedition__destination__ville',
            'expedition__destination__wilaya',
            'expedition__destination__zone_logistique'
        ).annotate(
            nb_incidents=Count('id'),
            incidents_critiques=Count('id', filter=Q(severite='CRITIQUE'))
        ).order_by('-nb_incidents')[:limite]
        
        return list(zones)
    
    @staticmethod
    def periodes_forte_activite(annee):
        """
        Identifie les périodes de forte activité (par mois)
        """
        activite_mois = Expedition.objects.filter(
            date_creation__year=annee
        ).annotate(
            mois=TruncMonth('date_creation')
        ).values('mois').annotate(
            nb_expeditions=Count('id'),
            nb_tournees=Count('tournee', distinct=True),
            ca=Sum('montant_total')
        ).order_by('mois')
        
        return list(activite_mois)
    
    @staticmethod
    def tableau_bord_global(annee=None):
        """
        Retourne toutes les statistiques pour le tableau de bord principal
        """
        if not annee:
            annee = datetime.now().year
        
        return {
            'evolution_expeditions': AnalyticsService.evolution_expeditions(annee),
            'evolution_ca': AnalyticsService.evolution_chiffre_affaires(annee),
            'top_clients': AnalyticsService.top_clients(10, annee),
            'destinations_populaires': AnalyticsService.destinations_populaires(10, annee),
            'evolution_tournees': AnalyticsService.evolution_tournees(annee),
            'taux_reussite': AnalyticsService.taux_reussite_livraisons(annee),
            'top_chauffeurs': AnalyticsService.top_chauffeurs(10, annee),
            'zones_incidents': AnalyticsService.zones_incidents(10, annee),
            'periodes_activite': AnalyticsService.periodes_forte_activite(annee)
        }