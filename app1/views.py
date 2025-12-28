from django.shortcuts import render, get_object_or_404
from .models import Client

def liste_clients(request):
    """Liste de tous les clients avec recherche"""
    search = request.GET.get('search', '')
    client_trouve = None
    expeditions = []
    
    if search:
        
        clients = Client.objects.filter(nom__icontains=search) | Client.objects.filter(prenom__icontains=search)
        
        
        if clients.count() == 1:
            client_trouve = clients.first()
            expeditions = client_trouve.expedition_set.all().order_by('-date_creation')
    else:
        clients = Client.objects.all()
    
    return render(request, 'clients/liste.html', {
        'clients': clients,
        'search': search,
        'client_trouve': client_trouve,
        'expeditions': expeditions
    })


def detail_client(request, client_id):
    """Détails d'un client + ses expéditions"""
    client = get_object_or_404(Client, id=client_id)
    expeditions = client.expedition_set.all().order_by('-date_creation')
    
    return render(request, 'clients/detail.html', {
        'client': client,
        'expeditions': expeditions
    })
