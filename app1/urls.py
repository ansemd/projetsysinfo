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