"""
constants.py - Constantes globales de l'application
Liste de TOUTES les fonctionnalités disponibles pour le système de favoris
"""

FONCTIONNALITES_DISPONIBLES = [
    # ========== CLIENTS ==========
    {
        'id': 'ajouter_client',
        'nom': 'Ajouter un client',
        'url': 'creer_client',
        'categorie': 'Clients'
    },
    {
        'id': 'consulter_clients',
        'nom': 'Consulter les clients',
        'url': 'liste_clients',
        'categorie': 'Clients'
    },
    {
        'id': 'modifier_client',
        'nom': 'Modifier un client',
        'url': 'liste_clients',
        'categorie': 'Clients'
    },
    {
        'id': 'supprimer_client',
        'nom': 'Supprimer un client',
        'url': 'liste_clients',
        'categorie': 'Clients'
    },
    {
        'id': 'exporter_clients',
        'nom': 'Exporter clients (PDF)',
        'url': 'exporter_clients_pdf',
        'categorie': 'Clients'
    },
    
    # ========== CHAUFFEURS ==========
    {
        'id': 'ajouter_chauffeur',
        'nom': 'Ajouter un chauffeur',
        'url': 'creer_chauffeur',
        'categorie': 'Chauffeurs'
    },
    {
        'id': 'consulter_chauffeurs',
        'nom': 'Consulter les chauffeurs',
        'url': 'liste_chauffeurs',
        'categorie': 'Chauffeurs'
    },
    {
        'id': 'modifier_chauffeur',
        'nom': 'Modifier un chauffeur',
        'url': 'liste_chauffeurs',
        'categorie': 'Chauffeurs'
    },
    {
        'id': 'supprimer_chauffeur',
        'nom': 'Supprimer un chauffeur',
        'url': 'liste_chauffeurs',
        'categorie': 'Chauffeurs'
    },
    {
        'id': 'exporter_chauffeurs',
        'nom': 'Exporter chauffeurs (PDF)',
        'url': 'exporter_chauffeurs_pdf',
        'categorie': 'Chauffeurs'
    },
    
    # ========== VÉHICULES ==========
    {
        'id': 'ajouter_vehicule',
        'nom': 'Ajouter un véhicule',
        'url': 'creer_vehicule',
        'categorie': 'Véhicules'
    },
    {
        'id': 'consulter_vehicules',
        'nom': 'Consulter les véhicules',
        'url': 'liste_vehicules',
        'categorie': 'Véhicules'
    },
    {
        'id': 'modifier_vehicule',
        'nom': 'Modifier un véhicule',
        'url': 'liste_vehicules',
        'categorie': 'Véhicules'
    },
    {
        'id': 'supprimer_vehicule',
        'nom': 'Supprimer un véhicule',
        'url': 'liste_vehicules',
        'categorie': 'Véhicules'
    },
    {
        'id': 'exporter_vehicules',
        'nom': 'Exporter véhicules (PDF)',
        'url': 'exporter_vehicules_pdf',
        'categorie': 'Véhicules'
    },
    
    # ========== DESTINATIONS ==========
    {
        'id': 'ajouter_destination',
        'nom': 'Ajouter une destination',
        'url': 'creer_destination',
        'categorie': 'Destinations'
    },
    {
        'id': 'consulter_destinations',
        'nom': 'Consulter les destinations',
        'url': 'liste_destinations',
        'categorie': 'Destinations'
    },
    {
        'id': 'modifier_destination',
        'nom': 'Modifier une destination',
        'url': 'liste_destinations',
        'categorie': 'Destinations'
    },
    {
        'id': 'supprimer_destination',
        'nom': 'Supprimer une destination',
        'url': 'liste_destinations',
        'categorie': 'Destinations'
    },
    {
        'id': 'exporter_destinations',
        'nom': 'Exporter destinations (PDF)',
        'url': 'exporter_destinations_pdf',
        'categorie': 'Destinations'
    },
    
    # ========== TYPES DE SERVICE ==========
    {
        'id': 'ajouter_typeservice',
        'nom': 'Ajouter un type de service',
        'url': 'creer_typeservice',
        'categorie': 'Types de Service'
    },
    {
        'id': 'consulter_typeservices',
        'nom': 'Consulter les types de service',
        'url': 'liste_typeservices',
        'categorie': 'Types de Service'
    },
    {
        'id': 'modifier_typeservice',
        'nom': 'Modifier un type de service',
        'url': 'liste_typeservices',
        'categorie': 'Types de Service'
    },
    {
        'id': 'supprimer_typeservice',
        'nom': 'Supprimer un type de service',
        'url': 'liste_typeservices',
        'categorie': 'Types de Service'
    },
    
    # ========== TARIFICATIONS ==========
    {
        'id': 'ajouter_tarification',
        'nom': 'Ajouter une tarification',
        'url': 'creer_tarification',
        'categorie': 'Tarifications'
    },
    {
        'id': 'consulter_tarifications',
        'nom': 'Consulter les tarifications',
        'url': 'liste_tarifications',
        'categorie': 'Tarifications'
    },
    {
        'id': 'modifier_tarification',
        'nom': 'Modifier une tarification',
        'url': 'liste_tarifications',
        'categorie': 'Tarifications'
    },
    {
        'id': 'supprimer_tarification',
        'nom': 'Supprimer une tarification',
        'url': 'liste_tarifications',
        'categorie': 'Tarifications'
    },
    
    # ========== EXPÉDITIONS ==========
    {
        'id': 'ajouter_expedition',
        'nom': 'Ajouter une expédition',
        'url': 'creer_expedition',
        'categorie': 'Expéditions'
    },
    {
        'id': 'consulter_expeditions',
        'nom': 'Consulter les expéditions',
        'url': 'liste_expeditions',
        'categorie': 'Expéditions'
    },
    {
        'id': 'modifier_expedition',
        'nom': 'Modifier une expédition',
        'url': 'liste_expeditions',
        'categorie': 'Expéditions'
    },
    {
        'id': 'supprimer_expedition',
        'nom': 'Supprimer une expédition',
        'url': 'liste_expeditions',
        'categorie': 'Expéditions'
    },
    {
        'id': 'exporter_expeditions',
        'nom': 'Exporter expéditions (PDF)',
        'url': 'exporter_expeditions_pdf',
        'categorie': 'Expéditions'
    },
    
    # ========== TOURNÉES ==========
    {
        'id': 'ajouter_tournee',
        'nom': 'Ajouter une tournée',
        'url': 'creer_tournee',
        'categorie': 'Tournées'
    },
    {
        'id': 'consulter_tournees',
        'nom': 'Consulter les tournées',
        'url': 'liste_tournees',
        'categorie': 'Tournées'
    },
    {
        'id': 'modifier_tournee',
        'nom': 'Modifier une tournée',
        'url': 'liste_tournees',
        'categorie': 'Tournées'
    },
    {
        'id': 'supprimer_tournee',
        'nom': 'Supprimer une tournée',
        'url': 'liste_tournees',
        'categorie': 'Tournées'
    },
    {
        'id': 'terminer_tournee',
        'nom': 'Terminer une tournée',
        'url': 'liste_tournees',
        'categorie': 'Tournées'
    },
    {
        'id': 'exporter_tournees',
        'nom': 'Exporter tournées (PDF)',
        'url': 'exporter_tournees_pdf',
        'categorie': 'Tournées'
    },
    
    # ========== SUIVI ==========
    {
        'id': 'suivi_colis',
        'nom': 'Suivi des colis',
        'url': 'liste_trackings',
        'categorie': 'Suivi'
    },
    
    # ========== FACTURES ==========
    {
        'id': 'consulter_factures',
        'nom': 'Consulter les factures',
        'url': 'liste_factures',
        'categorie': 'Factures'
    },
    {
        'id': 'modifier_facture',
        'nom': 'Modifier une facture',
        'url': 'liste_factures',
        'categorie': 'Factures'
    },
    {
        'id': 'supprimer_facture',
        'nom': 'Supprimer une facture',
        'url': 'liste_factures',
        'categorie': 'Factures'
    },
    {
        'id': 'exporter_factures',
        'nom': 'Exporter factures (PDF)',
        'url': 'exporter_factures_pdf',
        'categorie': 'Factures'
    },
    
    # ========== PAIEMENTS ==========
    {
        'id': 'ajouter_paiement',
        'nom': 'Enregistrer un paiement',
        'url': 'creer_paiement',
        'categorie': 'Paiements'
    },
    {
        'id': 'consulter_paiements',
        'nom': 'Consulter les paiements',
        'url': 'liste_paiements',
        'categorie': 'Paiements'
    },
    {
        'id': 'supprimer_paiement',
        'nom': 'Supprimer un paiement',
        'url': 'liste_paiements',
        'categorie': 'Paiements'
    },
    {
        'id': 'exporter_paiements',
        'nom': 'Exporter paiements (PDF)',
        'url': 'exporter_paiements_pdf',
        'categorie': 'Paiements'
    },
    
    # ========== INCIDENTS ==========
    {
        'id': 'ajouter_incident',
        'nom': 'Signaler un incident',
        'url': 'creer_incident',
        'categorie': 'Incidents'
    },
    {
        'id': 'consulter_incidents',
        'nom': 'Consulter les incidents',
        'url': 'liste_incidents',
        'categorie': 'Incidents'
    },
    {
        'id': 'modifier_incident',
        'nom': 'Modifier un incident',
        'url': 'liste_incidents',
        'categorie': 'Incidents'
    },
    {
        'id': 'supprimer_incident',
        'nom': 'Supprimer un incident',
        'url': 'liste_incidents',
        'categorie': 'Incidents'
    },
    {
        'id': 'resoudre_incident',
        'nom': 'Résoudre un incident',
        'url': 'liste_incidents',
        'categorie': 'Incidents'
    },
    {
        'id': 'exporter_incidents',
        'nom': 'Exporter incidents (PDF)',
        'url': 'exporter_incidents_pdf',
        'categorie': 'Incidents'
    },
    
    # ========== RÉCLAMATIONS ==========
    {
        'id': 'ajouter_reclamation',
        'nom': 'Ajouter une réclamation',
        'url': 'creer_reclamation',
        'categorie': 'Réclamations'
    },
    {
        'id': 'consulter_reclamations',
        'nom': 'Consulter les réclamations',
        'url': 'liste_reclamations',
        'categorie': 'Réclamations'
    },
    {
        'id': 'modifier_reclamation',
        'nom': 'Modifier une réclamation',
        'url': 'liste_reclamations',
        'categorie': 'Réclamations'
    },
    {
        'id': 'supprimer_reclamation',
        'nom': 'Supprimer une réclamation',
        'url': 'liste_reclamations',
        'categorie': 'Réclamations'
    },
    {
        'id': 'resoudre_reclamation',
        'nom': 'Résoudre une réclamation',
        'url': 'liste_reclamations',
        'categorie': 'Réclamations'
    },
    {
        'id': 'exporter_reclamations',
        'nom': 'Exporter réclamations (PDF)',
        'url': 'exporter_reclamations_pdf',
        'categorie': 'Réclamations'
    },
    
    # ========== NOTIFICATIONS ==========
    {
        'id': 'consulter_notifications',
        'nom': 'Consulter les notifications',
        'url': 'liste_notifications',
        'categorie': 'Notifications'
    },
]

# Favoris par défaut (si l'utilisateur n'a pas encore choisi)
FAVORIS_PAR_DEFAUT = [
    'ajouter_expedition',
    'consulter_tournees',
    'consulter_factures',
    'ajouter_incident'
]