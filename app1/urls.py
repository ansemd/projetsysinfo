from django.urls import path
from . import views

urlpatterns = [
    path('clients/', views.liste_clients, name='liste_clients'),
    path('clients/<int:client_id>/', views.detail_client, name='detail_client'),
    path('clients/creer/', views.creer_client, name='creer_client'),
    path('clients/<int:client_id>/modifier/', views.modifier_client, name='modifier_client'),
    path('clients/<int:client_id>/supprimer/', views.supprimer_client, name='supprimer_client'),

    path('chauffeurs/', views.liste_chauffeurs, name='liste_chauffeurs'),
    path('chauffeurs/<int:chauffeur_id>/', views.detail_chauffeur, name='detail_chauffeur'),
    path('chauffeurs/creer/', views.creer_chauffeur, name='creer_chauffeur'),
    path('chauffeurs/<int:chauffeur_id>/modifier/', views.modifier_chauffeur, name='modifier_chauffeur'),
    path('chauffeurs/<int:chauffeur_id>/supprimer/', views.supprimer_chauffeur, name='supprimer_chauffeur'),
    path('chauffeurs/<int:chauffeur_id>/modifier-statut/', views.modifier_statut_chauffeur, name='modifier_statut_chauffeur'),

    path('incidents/', views.liste_incidents, name='liste_incidents'),
    path('incidents/creer/', views.creer_incident, name='creer_incident'),
    path('incidents/<int:incident_id>/', views.detail_incident, name='detail_incident'),
    path('incidents/<int:incident_id>/modifier/', views.modifier_incident, name='modifier_incident'),
    path('incidents/<int:incident_id>/resoudre/', views.resoudre_incident, name='resoudre_incident'),
    path('incidents/<int:incident_id>/cloturer/', views.cloturer_incident, name='cloturer_incident'),
    path('incidents/<int:incident_id>/supprimer/', views.supprimer_incident, name='supprimer_incident'),
    
    path('reclamations/', views.liste_reclamations, name='liste_reclamations'),
    path('reclamations/creer/', views.creer_reclamation, name='creer_reclamation'),
    path('reclamations/<int:reclamation_id>/', views.detail_reclamation, name='detail_reclamation'),
    path('reclamations/<int:reclamation_id>/modifier/', views.modifier_reclamation, name='modifier_reclamation'),
    path('reclamations/<int:reclamation_id>/assigner/', views.assigner_reclamation, name='assigner_reclamation'),
    path('reclamations/<int:reclamation_id>/resoudre/', views.resoudre_reclamation, name='resoudre_reclamation'),
    path('reclamations/<int:reclamation_id>/cloturer/', views.cloturer_reclamation, name='cloturer_reclamation'),
    path('reclamations/<int:reclamation_id>/supprimer/', views.supprimer_reclamation, name='supprimer_reclamation'),

    path('emails', views.emails_view, name='emails'),

    # ==================== PAGES PRINCIPALES ====================
    
    # Tableau de bord principal
    path('analytics/dashboard/', views.dashboard_analytics, name='dashboard'),

    # Analyse commerciale
    path('analytics/commerciale/', views.analyse_commerciale, name='commerciale'),
    
    # Analyse opérationnelle
    path('analytics/operationnelle/', views.analyse_operationnelle, name='operationnelle'),
    
    # Statistiques et KPI
    path('analytics/kpi/', views.statistiques_kpi, name='kpi'),
    
    # Analyses avancées
    path('analytics/avancees/', views.analyses_avancees, name='avancees'),
    
    
    # ==================== API ANALYSE COMMERCIALE ====================
    
    # Évolution des expéditions
    path('analytics/api/evolution-expeditions/', 
         views.api_evolution_expeditions, 
         name='api_evolution_expeditions'),
    
    # Évolution du chiffre d'affaires
    path('analytics/api/evolution-ca/', 
         views.api_evolution_ca, 
         name='api_evolution_ca'),
    
    # Top clients
    path('analytics/api/top-clients/', 
         views.api_top_clients, 
         name='api_top_clients'),
    
    # Destinations populaires
    path('analytics/api/destinations-populaires/', 
         views.api_destinations_populaires, 
         name='api_destinations_populaires'),
    
    
    # ==================== API ANALYSE OPÉRATIONNELLE ====================
    
    # Évolution des tournées
    path('analytics/api/evolution-tournees/', 
         views.api_evolution_tournees, 
         name='api_evolution_tournees'),
    
    # Taux de réussite des livraisons
    path('analytics/api/taux-reussite/', 
         views.api_taux_reussite, 
         name='api_taux_reussite'),
    
    # Top chauffeurs
    path('analytics/api/top-chauffeurs/', 
         views.api_top_chauffeurs, 
         name='api_top_chauffeurs'),
    
    # Zones avec incidents
    path('analytics/api/zones-incidents/', 
         views.api_zones_incidents, 
         name='api_zones_incidents'),
    
    # Périodes de forte activité
    path('analytics/api/periodes-activite/', 
         views.api_periodes_activite, 
         name='api_periodes_activite'),
    
    
    # ==================== API STATISTIQUES ET KPI ====================
    
    # Statistiques générales
    path('analytics/api/stats-generales/', 
         views.api_stats_generales, 
         name='api_stats_generales'),
    
    # KPI Expéditions
    path('analytics/api/kpi-expeditions/', 
         views.api_kpi_expeditions, 
         name='api_kpi_expeditions'),
    
    # KPI Financiers
    path('analytics/api/kpi-financiers/', 
         views.api_kpi_financiers, 
         name='api_kpi_financiers'),
    
    # KPI Opérationnels
    path('analytics/api/kpi-operationnels/', 
         views.api_kpi_operationnels, 
         name='api_kpi_operationnels'),
    
    # KPI Qualité
    path('analytics/api/kpi-qualite/', 
         views.api_kpi_qualite, 
         name='api_kpi_qualite'),
    
    
    # ==================== API ANALYSES AVANCÉES ====================
    
    # Comparaison de périodes
    path('analytics/api/comparaison-periodes/', 
         views.api_comparaison_periodes, 
         name='api_comparaison_periodes'),
    
    # Analyse de saisonnalité
    path('analytics/api/saisonnalite/', 
         views.api_saisonnalite, 
         name='api_saisonnalite'),
    
    # Rentabilité par destination
    path('analytics/api/rentabilite-destinations/', 
         views.api_rentabilite_destinations, 
         name='api_rentabilite_destinations'),
    
    # Performance des véhicules
    path('analytics/api/performance-vehicules/', 
         views.api_performance_vehicules, 
         name='api_performance_vehicules'),
    
    
    # ==================== EXPORT ====================
    
    # Export PDF
    path('analytics/export/pdf/', 
         views.export_rapport_pdf, 
         name='export_pdf'),
    
    # Export Excel
    path('analytics/export/excel/', 
         views.export_rapport_excel, 
         name='export_excel'),
]