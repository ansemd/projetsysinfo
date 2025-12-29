from django.urls import path
from . import views

urlpatterns = [
    path('clients/', views.liste_clients, name='liste_clients'),
    path('clients/<int:client_id>/', views.detail_client, name='detail_client'),
    path('clients/creer/', views.creer_client, name='creer_client'),
    path('clients/<int:client_id>/modifier/', views.modifier_client, name='modifier_client'),
    path('clients/<int:client_id>/supprimer/', views.supprimer_client, name='supprimer_client'),
]