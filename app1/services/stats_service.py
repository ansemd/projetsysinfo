"""
stats_service.py - Service pour les statistiques détaillées et KPI

UTILISATION :
Ce service calcule les indicateurs clés de performance (KPI)

EXEMPLES :
- StatsService.kpi_expeditions(2025) → Délai moyen, taux ponctualité
- StatsService.kpi_financiers(2025) → CA, taux recouvrement
- StatsService.kpi_operationnels(2025) → Km total, consommation
"""

from django.db.models import Count, Sum, Avg, Q, F
from datetime import datetime, timedelta
from decimal import Decimal


class StatsService:
    """
    Service pour les statistiques détaillées et indicateurs clés de performance (KPI)
    """
    
    # ==================== STATISTIQUES GÉNÉRALES ====================
    
    @staticmethod
    def statistiques_generales(date_debut=None, date_fin=None):
        """
        Retourne les statistiques générales du système
        """
        from app1.models import Expedition, Tournee, Client, Chauffeur, Vehicule, Incident, Facture, Reclamation
        
        expeditions = Expedition.objects.all()
        tournees = Tournee.objects.all()
        factures = Facture.objects.all()
        
        if date_debut and date_fin:
            expeditions = expeditions.filter(date_creation__range=[date_debut, date_fin])
            tournees = tournees.filter(date_depart__range=[date_debut, date_fin])
            factures = factures.filter(date_creation__range=[date_debut, date_fin])
        
        return {
            'total_expeditions': expeditions.count(),
            'total_clients': Client.objects.filter(est_actif=True).count(),
            'total_chauffeurs': Chauffeur.objects.filter(disponibilite=True).count(),
            'total_vehicules': Vehicule.objects.filter(etat='OPERATIONNEL').count(),
            'total_tournees': tournees.count(),
            'ca_total': factures.aggregate(total=Sum('montant_ttc'))['total'] or 0,
            'expeditions_en_cours': expeditions.filter(
                statut__in=['EN_ATTENTE', 'EN_TRANSIT', 'EN_LIVRAISON']
            ).count(),
            'incidents_actifs': Incident.objects.filter(statut='EN_COURS').count(),
            'reclamations_ouvertes': Reclamation.objects.filter(
                statut__in=['OUVERTE', 'EN_COURS']
            ).count(),
        }
    
    # ==================== KPI EXPÉDITIONS ====================
    
    @staticmethod
    def kpi_expeditions(annee=None):
        """
        Calcule les KPI liés aux expéditions
        """
        from app1.models import Expedition
        
        expeditions = Expedition.objects.all()
        
        if annee:
            expeditions = expeditions.filter(date_creation__year=annee)
        
        total = expeditions.count()
        
        return {
            'panier_moyen': expeditions.aggregate(avg=Avg('montant_total'))['avg'] or 0,
            'poids_moyen': expeditions.aggregate(avg=Avg('poids'))['avg'] or 0,
            'volume_moyen': expeditions.aggregate(avg=Avg('volume'))['avg'] or 0,
            'repartition_statuts': expeditions.values('statut').annotate(
                count=Count('id'),
                pourcentage=Count('id') * 100.0 / total if total > 0 else 0
            )
        }
    
    # ==================== KPI FINANCIERS ====================
    
    @staticmethod
    def kpi_financiers(annee=None):
        """
        Calcule les KPI financiers
        """
        from app1.models import Facture, Paiement, Client
        
        factures = Facture.objects.all()
        paiements = Paiement.objects.all()
        
        if annee:
            factures = factures.filter(date_creation__year=annee)
            paiements = paiements.filter(date_paiement__year=annee)
        
        ca_total = factures.aggregate(total=Sum('montant_ttc'))['total'] or 0
        ca_encaisse = paiements.aggregate(total=Sum('montant_paye'))['total'] or 0
        
        factures_payees = factures.filter(statut='PAYEE').count()
        factures_impayees = factures.filter(statut__in=['IMPAYEE', 'PARTIELLEMENT_PAYEE']).count()
        total_factures = factures.count()
        
        return {
            'ca_total': ca_total,
            'ca_encaisse': ca_encaisse,
            'ca_restant': ca_total - ca_encaisse,
            'taux_recouvrement': (ca_encaisse / ca_total * 100) if ca_total > 0 else 0,
            'nb_factures_payees': factures_payees,
            'nb_factures_impayees': factures_impayees,
            'taux_paiement': (factures_payees / total_factures * 100) if total_factures > 0 else 0,
            'montant_moyen_facture': factures.aggregate(avg=Avg('montant_ttc'))['avg'] or 0,
            'clients_debiteurs': Client.objects.filter(solde__gt=0).count(),
            'total_creances': Client.objects.aggregate(total=Sum('solde'))['total'] or 0
        }
    
    # ==================== KPI OPÉRATIONNELS ====================
    
    @staticmethod
    def kpi_operationnels(annee=None):
        """
        Calcule les KPI opérationnels (tournées, véhicules, chauffeurs)
        """
        from app1.models import Tournee, Vehicule, Chauffeur
        
        tournees = Tournee.objects.all()
        
        if annee:
            tournees = tournees.filter(date_depart__year=annee)
        
        tournees_terminees = tournees.filter(statut='TERMINEE')
        
        return {
            'nb_tournees_total': tournees.count(),
            'nb_tournees_terminees': tournees_terminees.count(),
            'km_total': tournees_terminees.aggregate(total=Sum('kilometrage_parcouru'))['total'] or 0,
            'km_moyen_tournee': tournees_terminees.aggregate(avg=Avg('kilometrage_parcouru'))['avg'] or 0,
            'consommation_moyenne': tournees_terminees.aggregate(
                avg=Avg('consommation_carburant')
            )['avg'] or 0,
            'taux_disponibilite_chauffeurs': StatsService._calculer_taux_disponibilite_chauffeurs(),
        }
    
    # ==================== KPI QUALITÉ ====================
    
    @staticmethod
    def kpi_qualite(annee=None):
        """
        Calcule les KPI de qualité de service
        """
        from app1.models import Incident, Reclamation
        
        incidents = Incident.objects.all()
        reclamations = Reclamation.objects.all()
        
        if annee:
            incidents = incidents.filter(date_heure_incident__year=annee)
            reclamations = reclamations.filter(date_creation__year=annee)
        
        return {
            'nb_incidents_total': incidents.count(),
            'incidents_par_severite': incidents.values('severite').annotate(
                count=Count('id')
            ),
            'taux_incidents': StatsService._calculer_taux_incidents(annee),
            'nb_reclamations': reclamations.count(),
            'reclamations_resolues': reclamations.filter(statut='RESOLUE').count(),
        }
    
    # ==================== MÉTHODES UTILITAIRES PRIVÉES ====================
    
    @staticmethod
    def _calculer_taux_disponibilite_chauffeurs():
        """Calcule le taux de disponibilité des chauffeurs"""
        from app1.models import Chauffeur
        
        total = Chauffeur.objects.count()
        disponibles = Chauffeur.objects.filter(disponibilite=True).count()
        
        return (disponibles / total * 100) if total > 0 else 0
    
    @staticmethod
    def _calculer_taux_incidents(annee=None):
        """Calcule le taux d'incidents par rapport aux expéditions"""
        from app1.models import Expedition, Incident
        
        expeditions = Expedition.objects.all()
        incidents = Incident.objects.filter(expedition__isnull=False)
        
        if annee:
            expeditions = expeditions.filter(date_creation__year=annee)
            incidents = incidents.filter(date_heure_incident__year=annee)
        
        total_exp = expeditions.count()
        total_incidents = incidents.count()
        
        return (total_incidents / total_exp * 100) if total_exp > 0 else 0
    
    # ==================== COMPARAISONS TEMPORELLES ====================
    
    @staticmethod
    def comparaison_periodes(date_debut1, date_fin1, date_debut2, date_fin2):
        """
        Compare les performances entre deux périodes
        """
        from app1.models import Expedition
        
        # Période 1
        exp1 = Expedition.objects.filter(date_creation__range=[date_debut1, date_fin1])
        ca1 = exp1.aggregate(total=Sum('montant_total'))['total'] or 0
        
        # Période 2
        exp2 = Expedition.objects.filter(date_creation__range=[date_debut2, date_fin2])
        ca2 = exp2.aggregate(total=Sum('montant_total'))['total'] or 0
        
        return {
            'periode1': {
                'nb_expeditions': exp1.count(),
                'ca': ca1,
                'panier_moyen': exp1.aggregate(avg=Avg('montant_total'))['avg'] or 0
            },
            'periode2': {
                'nb_expeditions': exp2.count(),
                'ca': ca2,
                'panier_moyen': exp2.aggregate(avg=Avg('montant_total'))['avg'] or 0
            },
            'evolution': {
                'expeditions': StatsService._calculer_variation(exp1.count(), exp2.count()),
                'ca': StatsService._calculer_variation(float(ca1), float(ca2))
            }
        }
    
    @staticmethod
    def _calculer_variation(valeur1, valeur2):
        """Calcule la variation en pourcentage entre deux valeurs"""
        if valeur1 == 0:
            return 0 if valeur2 == 0 else 100
        
        return ((valeur2 - valeur1) / valeur1) * 100
    
    # ==================== ANALYSES AVANCÉES ====================
    
    @staticmethod
    def analyse_saisonnalite(annee):
        """
        Analyse la saisonnalité des expéditions par trimestre et mois
        """
        from app1.models import Expedition
        from django.db.models.functions import TruncMonth
        
        expeditions = Expedition.objects.filter(date_creation__year=annee)
        
        # Par trimestre
        par_trimestre = []
        for trimestre in range(1, 5):
            debut_mois = (trimestre - 1) * 3 + 1
            fin_mois = trimestre * 3
            
            exp_trimestre = expeditions.filter(
                date_creation__month__gte=debut_mois,
                date_creation__month__lte=fin_mois
            )
            
            par_trimestre.append({
                'trimestre': f'T{trimestre}',
                'nb_expeditions': exp_trimestre.count(),
                'ca': exp_trimestre.aggregate(total=Sum('montant_total'))['total'] or 0
            })
        
        # Par mois
        par_mois = expeditions.annotate(
            mois=TruncMonth('date_creation')
        ).values('mois').annotate(
            nb_expeditions=Count('id'),
            ca=Sum('montant_total')
        ).order_by('mois')
        
        return {
            'par_trimestre': par_trimestre,
            'par_mois': list(par_mois)
        }
    
    @staticmethod
    def analyse_rentabilite_destinations(annee=None):
        """
        Analyse la rentabilité par destination
        """
        from app1.models import Expedition
        
        expeditions = Expedition.objects.all()
        
        if annee:
            expeditions = expeditions.filter(date_creation__year=annee)
        
        rentabilite = expeditions.values(
            'destination__ville',
            'destination__wilaya',
            'destination__zone_logistique'
        ).annotate(
            nb_expeditions=Count('id'),
            ca_total=Sum('montant_total'),
            ca_moyen=Avg('montant_total'),
            poids_total=Sum('poids')
        ).order_by('-ca_total')
        
        return list(rentabilite)
    
    @staticmethod
    def analyse_performance_vehicules(annee=None):
        """
        Analyse les performances des véhicules
        """
        from app1.models import Tournee
        
        tournees = Tournee.objects.filter(statut='TERMINEE')
        
        if annee:
            tournees = tournees.filter(date_depart__year=annee)
        
        performance = tournees.values(
            'vehicule__immatriculation',
            'vehicule__marque',
            'vehicule__modele'
        ).annotate(
            nb_tournees=Count('id'),
            km_total=Sum('kilometrage_parcouru'),
            consommation_totale=Sum('consommation_carburant'),
            consommation_moyenne=Avg('consommation_carburant')
        ).order_by('-nb_tournees')
        
        return list(performance)