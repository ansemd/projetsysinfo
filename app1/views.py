from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Q, Count, Sum
from .models import Client


# ========== LISTE DES CLIENTS (PAGE PRINCIPALE) ==========
def liste_clients(request):
    """
    Page principale : Liste de tous les clients avec recherche et statistiques
    """
    search = request.GET.get('search', '')
    
    if search:
        # Recherche par nom, prénom, téléphone, email, ville ou wilaya
        clients = Client.objects.filter(
            Q(nom__icontains=search) | 
            Q(prenom__icontains=search) |
            Q(telephone__icontains=search) |
            Q(email__icontains=search) |
            Q(ville__icontains=search) |
            Q(wilaya__icontains=search)
        ).order_by('-date_inscription')
    else:
        clients = Client.objects.all().order_by('-date_inscription')
    
    # Statistiques globales
    stats = {
        'total_clients': Client.objects.count(),
        'clients_avec_solde': Client.objects.filter(solde__gt=0).count(),
        'solde_total': Client.objects.aggregate(Sum('solde'))['solde__sum'] or 0,
    }
    
    return render(request, 'clients/liste.html', {
        'clients': clients,
        'search': search,
        'stats': stats,
    })


# ========== DÉTAILS D'UN CLIENT ==========
def detail_client(request, client_id):
    """
    Affiche tous les détails d'un client + ses expéditions
    """
    client = get_object_or_404(Client, id=client_id)
    
    # Récupérer toutes les expéditions du client
    expeditions = client.expedition_set.all().order_by('-date_creation')
    
    # Statistiques du client
    stats_client = {
        'total_expeditions': expeditions.count(),
        'expeditions_livrees': expeditions.filter(statut='LIVRE').count(),
        'expeditions_en_cours': expeditions.filter(statut='EN_TRANSIT').count(),
        'expeditions_en_attente': expeditions.filter(statut='EN_ATTENTE').count(),
        'total_depense': expeditions.aggregate(Sum('montant_total'))['montant_total__sum'] or 0,
    }
    
    # Récupérer les factures du client
    factures = client.factures.all().order_by('-date_creation')[:5]  # Les 5 dernières
    
    return render(request, 'clients/detail.html', {
        'client': client,
        'expeditions': expeditions,
        'stats_client': stats_client,
        'factures': factures,
    })


# ========== CRÉER UN CLIENT ==========
def creer_client(request):
    """
    Formulaire de création d'un nouveau client
    """
    if request.method == 'POST':
        try:
            # Récupérer les données du formulaire
            client = Client(
                nom=request.POST['nom'],
                prenom=request.POST['prenom'],
                date_naissance=request.POST['date_naissance'],
                telephone=request.POST['telephone'],
                email=request.POST.get('email', ''),
                adresse=request.POST.get('adresse', ''),
                ville=request.POST.get('ville', ''),
                wilaya=request.POST.get('wilaya', ''),
                solde=request.POST.get('solde', 0.00),
                remarques=request.POST.get('remarques', ''),
            )
            client.save()
            
            messages.success(request, f'Client {client.prenom} {client.nom} créé avec succès!')
            return redirect('detail_client', client_id=client.id)
            
        except Exception as e:
            messages.error(request, f'Erreur lors de la création du client: {str(e)}')
    
    return render(request, 'clients/creer.html')


# ========== MODIFIER UN CLIENT ==========
def modifier_client(request, client_id):
    """
    Formulaire de modification d'un client existant
    """
    client = get_object_or_404(Client, id=client_id)
    
    if request.method == 'POST':
        try:
            # Mettre à jour les données du client
            client.nom = request.POST['nom']
            client.prenom = request.POST['prenom']
            client.date_naissance = request.POST['date_naissance']
            client.telephone = request.POST['telephone']
            client.email = request.POST.get('email', '')
            client.adresse = request.POST.get('adresse', '')
            client.ville = request.POST.get('ville', '')
            client.wilaya = request.POST.get('wilaya', '')
            client.solde = request.POST.get('solde', 0.00)
            client.remarques = request.POST.get('remarques', '')
            
            # La date_modification sera mise à jour automatiquement (auto_now=True)
            client.save()
            
            messages.success(request, f'Client {client.prenom} {client.nom} modifié avec succès!')
            return redirect('detail_client', client_id=client.id)
            
        except Exception as e:
            messages.error(request, f'Erreur lors de la modification: {str(e)}')
    
    return render(request, 'clients/modifier.html', {
        'client': client,
    })


# ========== SUPPRIMER UN CLIENT ==========
def supprimer_client(request, client_id):
    """
    Suppression d'un client (avec confirmation)
    """
    client = get_object_or_404(Client, id=client_id)
    
    if request.method == 'POST':
        try:
            nom_complet = f"{client.prenom} {client.nom}"
            client.delete()
            messages.success(request, f'Client {nom_complet} supprimé avec succès!')
            return redirect('liste_clients')
            
        except Exception as e:
            messages.error(request, f'Erreur lors de la suppression: {str(e)}')
            return redirect('detail_client', client_id=client_id)
    
    # Si GET, afficher page de confirmation
    return render(request, 'clients/supprimer.html', {
        'client': client,
    })