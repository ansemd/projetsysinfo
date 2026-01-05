from django.db.models import Count, Sum, Avg, Max, Min, Q, F, ExpressionWrapper, DecimalField
from django.db.models.functions import TruncMonth, TruncYear, TruncDay, TruncWeek
from datetime import datetime, timedelta
from decimal import Decimal
from app1.models import (
    Expedition, Tournee, Client, Destination, Chauffeur, 
    Vehicule, Incident, Facture, Paiement, Reclamation
)


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
        expeditions = Expedition.objects.all()
        tournees = Tournee.objects.all()
        factures = Facture.objects.all()
        
        if date_debut and date_fin:
            expeditions = expeditions.filter(date_creation__range=[date_debut, date_fin])
            tournees = tournees.filter(date_depart__range=[date_debut, date_fin])
            factures = factures.filter(date_emission__range=[date_debut, date_fin])
        
        return {
            'total_expeditions': expeditions.count(),
            'total_clients': Client.objects.filter(is_active=True).count(),
            'total_chauffeurs': Chauffeur.objects.filter(disponibilite=True).count(),
            'total_vehicules': Vehicule.objects.filter(etat='OPERATIONNEL').count(),
            'total_tournees': tournees.count(),
            'ca_total': factures.aggregate(total=Sum('montant_ttc'))['total'] or 0,
            'expeditions_en_cours': expeditions.filter(
                statut__in=['EN_ATTENTE', 'EN_TRANSIT', 'EN_LIVRAISON']
            ).count(),
            'incidents_actifs': Incident.objects.filter(statut='EN_COURS').count(),
            'reclamations_ouvertes': Reclamation.objects.filter(
                statut__in=['EN_COURS', 'EN_ATTENTE']
            ).count(),
        }
    
    # ==================== KPI (Indicateurs Clés de Performance) ====================
    
    @staticmethod
    def kpi_expeditions(annee=None):
        """
        Calcule les KPI liés aux expéditions
        """
        expeditions = Expedition.objects.all()
        
        if annee:
            expeditions = expeditions.filter(date_creation__year=annee)
        
        total = expeditions.count()
        
        return {
            'delai_moyen_livraison': StatsService._calculer_delai_moyen(expeditions),
            'taux_ponctualite': StatsService._calculer_taux_ponctualite(expeditions),
            'panier_moyen': expeditions.aggregate(
                avg=Avg('montant_total')
            )['avg'] or 0,
            'poids_moyen': expeditions.aggregate(
                avg=Avg('poids')
            )['avg'] or 0,
            'volume_moyen': expeditions.aggregate(
                avg=Avg('volume')
            )['avg'] or 0,
            'repartition_types': expeditions.values('type_service__libelle').annotate(
                count=Count('id'),
                pourcentage=Count('id') * 100.0 / total if total > 0 else 0
            ),
            'repartition_statuts': expeditions.values('statut').annotate(
                count=Count('id'),
                pourcentage=Count('id') * 100.0 / total if total > 0 else 0
            )
        }
    
    @staticmethod
    def kpi_financiers(annee=None):
        """
        Calcule les KPI financiers
        """
        factures = Facture.objects.all()
        paiements = Paiement.objects.all()
        
        if annee:
            factures = factures.filter(date_emission__year=annee)
            paiements = paiements.filter(date_paiement__year=annee)
        
        ca_total = factures.aggregate(total=Sum('montant_ttc'))['total'] or 0
        ca_encaisse = paiements.aggregate(total=Sum('montant'))['total'] or 0
        
        factures_payees = factures.filter(statut='PAYEE').count()
        factures_impayees = factures.filter(statut__in=['IMPAYEE', 'PARTIELLE']).count()
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
            'montant_moyen_paiement': paiements.aggregate(avg=Avg('montant'))['avg'] or 0,
            'clients_debiteurs': Client.objects.filter(solde__gt=0).count(),
            'total_creances': Client.objects.aggregate(total=Sum('solde'))['total'] or 0
        }
    
    @staticmethod
    def kpi_operationnels(annee=None):
        """
        Calcule les KPI opérationnels (tournées, véhicules, chauffeurs)
        """
        tournees = Tournee.objects.all()
        
        if annee:
            tournees = tournees.filter(date_depart__year=annee)
        
        tournees_terminees = tournees.filter(statut='TERMINEE')
        
        return {
            'nb_tournees_total': tournees.count(),
            'nb_tournees_terminees': tournees_terminees.count(),
            'km_total': tournees_terminees.aggregate(total=Sum('kilometrage_parcouru'))['total'] or 0,
            'km_moyen_tournee': tournees_terminees.aggregate(avg=Avg('kilometrage_parcouru'))['avg'] or 0,
            'duree_moyenne_tournee': tournees_terminees.aggregate(avg=Avg('duree_trajet'))['avg'] or 0,
            'consommation_moyenne': tournees_terminees.aggregate(
                avg=Avg('consommation_carburant')
            )['avg'] or 0,
            'cout_moyen_tournee': StatsService._calculer_cout_moyen_tournee(tournees_terminees),
            'taux_utilisation_vehicules': StatsService._calculer_taux_utilisation_vehicules(annee),
            'taux_disponibilite_chauffeurs': StatsService._calculer_taux_disponibilite_chauffeurs(),
            'incidents_par_tournee': StatsService._calculer_incidents_par_tournee(annee)
        }
    
    @staticmethod
    def kpi_qualite(annee=None):
        """
        Calcule les KPI de qualité de service
        """
        incidents = Incident.objects.all()
        reclamations = Reclamation.objects.all()
        
        if annee:
            incidents = incidents.filter(date_heure_incident__year=annee)
            reclamations = reclamations.filter(date_reclamation__year=annee)
        
        return {
            'nb_incidents_total': incidents.count(),
            'incidents_par_type': incidents.values('type_incident').annotate(
                count=Count('id')
            ),
            'incidents_par_severite': incidents.values('severite').annotate(
                count=Count('id')
            ),
            'taux_incidents': StatsService._calculer_taux_incidents(annee),
            'nb_reclamations': reclamations.count(),
            'reclamations_resolues': reclamations.filter(statut='RESOLUE').count(),
            'delai_moyen_resolution': StatsService._calculer_delai_moyen_resolution(reclamations),
            'satisfaction_client': StatsService._calculer_satisfaction_client(annee)
        }
    
    # ==================== COMPARAISONS TEMPORELLES ====================
    
    @staticmethod
    def comparaison_periodes(date_debut1, date_fin1, date_debut2, date_fin2):
        """
        Compare les performances entre deux périodes
        """
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
    
    # ==================== ANALYSES AVANCÉES ====================
    
    @staticmethod
    def analyse_saisonnalite(annee):
        """
        Analyse la saisonnalité des expéditions par trimestre et mois
        """
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
    
    # ==================== MÉTHODES UTILITAIRES PRIVÉES ====================
    
    @staticmethod
    def _calculer_delai_moyen(expeditions):
        """Calcule le délai moyen de livraison en jours"""
        livrees = expeditions.filter(
            statut='LIVRE',
            date_livraison__isnull=False
        )
        
        if not livrees.exists():
            return 0
        
        delais = []
        for exp in livrees:
            delai = (exp.date_livraison - exp.date_creation.date()).days
            delais.append(delai)
        
        return sum(delais) / len(delais) if delais else 0
    
    @staticmethod
    def _calculer_taux_ponctualite(expeditions):
        """Calcule le taux de ponctualité des livraisons"""
        livrees = expeditions.filter(statut='LIVRE')
        total = livrees.count()
        
        if total == 0:
            return 0
        
        # Considérer comme ponctuel si livré dans les 3 jours
        ponctuelles = livrees.filter(
            date_livraison__lte=F('date_creation') + timedelta(days=3)
        ).count()
        
        return (ponctuelles / total * 100) if total > 0 else 0
    
    @staticmethod
    def _calculer_cout_moyen_tournee(tournees):
        """Calcule le coût moyen d'une tournée"""
        if not tournees.exists():
            return 0
        
        # Coût carburant moyen (estimation: 1.5 DA/litre)
        cout_carburant = tournees.aggregate(
            total=Sum('consommation_carburant')
        )['total'] or 0
        
        return (cout_carburant * 1.5) / tournees.count() if tournees.count() > 0 else 0
    
    @staticmethod
    def _calculer_taux_utilisation_vehicules(annee=None):
        """Calcule le taux d'utilisation des véhicules"""
        vehicules_total = Vehicule.objects.filter(etat='OPERATIONNEL').count()
        
        if vehicules_total == 0:
            return 0
        
        tournees = Tournee.objects.all()
        if annee:
            tournees = tournees.filter(date_depart__year=annee)
        
        vehicules_utilises = tournees.values('vehicule').distinct().count()
        
        return (vehicules_utilises / vehicules_total * 100) if vehicules_total > 0 else 0
    
    @staticmethod
    def _calculer_taux_disponibilite_chauffeurs():
        """Calcule le taux de disponibilité des chauffeurs"""
        total = Chauffeur.objects.count()
        disponibles = Chauffeur.objects.filter(disponibilite=True).count()
        
        return (disponibles / total * 100) if total > 0 else 0
    
    @staticmethod
    def _calculer_incidents_par_tournee(annee=None):
        """Calcule le nombre moyen d'incidents par tournée"""
        tournees = Tournee.objects.all()
        incidents = Incident.objects.all()
        
        if annee:
            tournees = tournees.filter(date_depart__year=annee)
            incidents = incidents.filter(date_heure_incident__year=annee)
        
        nb_tournees = tournees.count()
        nb_incidents = incidents.count()
        
        return (nb_incidents / nb_tournees) if nb_tournees > 0 else 0
    
    @staticmethod
    def _calculer_taux_incidents(annee=None):
        """Calcule le taux d'incidents par rapport aux expéditions"""
        expeditions = Expedition.objects.all()
        incidents = Incident.objects.filter(expedition__isnull=False)
        
        if annee:
            expeditions = expeditions.filter(date_creation__year=annee)
            incidents = incidents.filter(date_heure_incident__year=annee)
        
        total_exp = expeditions.count()
        total_incidents = incidents.count()
        
        return (total_incidents / total_exp * 100) if total_exp > 0 else 0
    
    @staticmethod
    def _calculer_delai_moyen_resolution(reclamations):
        """Calcule le délai moyen de résolution des réclamations"""
        resolues = reclamations.filter(
            statut='RESOLUE',
            date_resolution__isnull=False
        )
        
        if not resolues.exists():
            return 0
        
        delais = []
        for rec in resolues:
            delai = (rec.date_resolution - rec.date_reclamation).days
            delais.append(delai)
        
        return sum(delais) / len(delais) if delais else 0
    
    @staticmethod
    def _calculer_satisfaction_client(annee=None):
        """Calcule un score de satisfaction client basé sur les réclamations"""
        expeditions = Expedition.objects.all()
        reclamations = Reclamation.objects.all()
        
        if annee:
            expeditions = expeditions.filter(date_creation__year=annee)
            reclamations = reclamations.filter(date_reclamation__year=annee)
        
        total_exp = expeditions.count()
        total_rec = reclamations.count()
        
        # Score de satisfaction (100 - taux de réclamation)
        taux_reclamation = (total_rec / total_exp * 100) if total_exp > 0 else 0
        
        return max(0, 100 - taux_reclamation)
    
    @staticmethod
    def _calculer_variation(valeur1, valeur2):
        """Calcule la variation en pourcentage entre deux valeurs"""
        if valeur1 == 0:
            return 0 if valeur2 == 0 else 100
        
        return ((valeur2 - valeur1) / valeur1) * 100