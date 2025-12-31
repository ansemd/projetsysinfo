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
]

urlpatterns = [
    path('incidents/', views.liste_incidents, name='liste_incidents'),
    path('incidents/creer/', views.creer_incident, name='creer_incident'),
    path('incidents/<int:incident_id>/', views.detail_incident, name='detail_incident'),
    path('incidents/<int:incident_id>/resoudre/', views.resoudre_incident, name='resoudre_incident'),
    path('incidents/statistiques/', views.statistiques_incidents, name='statistiques_incidents'),
    
    path('reclamations/', views.liste_reclamations, name='liste_reclamations'),
    path('reclamations/creer/', views.creer_reclamation, name='creer_reclamation'),
    path('reclamations/<int:reclamation_id>/', views.detail_reclamation, name='detail_reclamation'),
    path('reclamations/<int:reclamation_id>/assigner/', views.assigner_reclamation, name='assigner_reclamation'),
    path('reclamations/<int:reclamation_id>/repondre/', views.repondre_reclamation, name='repondre_reclamation'),
    path('reclamations/<int:reclamation_id>/resoudre/', views.resoudre_reclamation, name='resoudre_reclamation'),
    path('reclamations/statistiques/', views.statistiques_reclamations, name='statistiques_reclamations'),
]