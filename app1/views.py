from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Q, Count, Sum
from .models import Client, Chauffeur


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



# ========== LISTE DES CHAUFFEURS (PAGE PRINCIPALE) ==========
def liste_chauffeurs(request):
    """
    Page principale : Liste de tous les chauffeurs avec recherche et filtrage par statut
    """
    search = request.GET.get('search', '')
    filtre_statut = request.GET.get('statut', '')  # Filtre par statut
    
    # Base queryset
    chauffeurs = Chauffeur.objects.all()
    
    # Recherche
    if search:
        chauffeurs = chauffeurs.filter(
            Q(nom__icontains=search) | 
            Q(prenom__icontains=search) |
            Q(numero_permis__icontains=search) |
            Q(telephone__icontains=search) |
            Q(ville__icontains=search) |
            Q(wilaya__icontains=search)
        )
    
    # Filtrage par statut
    if filtre_statut:
        chauffeurs = chauffeurs.filter(statut_disponibilite=filtre_statut)
    
    chauffeurs = chauffeurs.order_by('-date_embauche')
    
    # Statistiques globales
    stats = {
        'total_chauffeurs': Chauffeur.objects.count(),
        'disponibles': Chauffeur.objects.filter(statut_disponibilite='DISPONIBLE').count(),
        'en_tournee': Chauffeur.objects.filter(statut_disponibilite='EN_TOURNEE').count(),
        'en_conge': Chauffeur.objects.filter(statut_disponibilite='CONGE').count(),
    }
    
    # Liste des statuts pour le filtre
    statuts = [
        ('DISPONIBLE', 'Disponible'),
        ('EN_TOURNEE', 'En tournée'),
        ('CONGE', 'En congé'),
        ('MALADIE', 'Maladie'),
        ('AUTRE', 'Autre raison'),
    ]
    
    return render(request, 'chauffeurs/liste.html', {
        'chauffeurs': chauffeurs,
        'search': search,
        'filtre_statut': filtre_statut,
        'statuts': statuts,
        'stats': stats,
    })

# ========== MODIFIER STATUT CHAUFFEUR (AJAX) ==========
def modifier_statut_chauffeur(request, chauffeur_id):
    """
    Modifie uniquement le statut d'un chauffeur (appelé depuis la liste)
    """
    if request.method == 'POST':
        chauffeur = get_object_or_404(Chauffeur, id=chauffeur_id)
        nouveau_statut = request.POST.get('statut')
        
        if nouveau_statut in ['DISPONIBLE', 'EN_TOURNEE', 'CONGE', 'MALADIE', 'AUTRE']:
            chauffeur.statut_disponibilite = nouveau_statut
            chauffeur.save()
            messages.success(request, f'Statut de {chauffeur.prenom} {chauffeur.nom} modifié avec succès!')
        else:
            messages.error(request, 'Statut invalide')
    
    return redirect('liste_chauffeurs')

# ========== DÉTAILS D'UN CHAUFFEUR ==========
def detail_chauffeur(request, chauffeur_id):
    """
    Affiche tous les détails d'un chauffeur + sa tournée actuelle (EN_COURS ou PREVUE)
    """
    chauffeur = get_object_or_404(Chauffeur, id=chauffeur_id)
    
    # Récupérer SEULEMENT la tournée actuelle (EN_COURS ou PREVUE)
    tournee_actuelle = chauffeur.tournee_set.filter(
        statut__in=['EN_COURS', 'PREVUE']
    ).order_by('-date_creation').first()
    
    # Statistiques du chauffeur (toutes les tournées)
    all_tournees = chauffeur.tournee_set.all()
    stats_chauffeur = {
        'total_tournees': all_tournees.count(),
        'tournees_prevues': all_tournees.filter(statut='PREVUE').count(),
        'tournees_en_cours': all_tournees.filter(statut='EN_COURS').count(),
        'tournees_terminees': all_tournees.filter(statut='TERMINEE').count(),
    }
    
    return render(request, 'chauffeurs/detail.html', {
        'chauffeur': chauffeur,
        'tournee_actuelle': tournee_actuelle,
        'stats_chauffeur': stats_chauffeur,
    })

# ========== CRÉER UN CHAUFFEUR ==========
def creer_chauffeur(request):
    """
    Formulaire de création d'un nouveau chauffeur
    """
    if request.method == 'POST':
        try:
            from datetime import datetime
            
            # Récupérer et valider les dates
            date_obtention = datetime.strptime(request.POST['date_obtention_permis'], '%Y-%m-%d').date()
            date_expiration = datetime.strptime(request.POST['date_expiration_permis'], '%Y-%m-%d').date()
            
            # VALIDATION : date obtention doit être AVANT date expiration
            if date_obtention >= date_expiration:
                messages.error(
                    request, 
                    'Erreur : La date d\'obtention du permis doit être antérieure à la date d\'expiration !'
                )
                return render(request, 'chauffeurs/creer.html')
            
            chauffeur = Chauffeur(
                nom=request.POST['nom'],
                prenom=request.POST['prenom'],
                date_naissance=request.POST['date_naissance'],
                telephone=request.POST['telephone'],
                email=request.POST.get('email', ''),
                adresse=request.POST.get('adresse', ''),
                ville=request.POST.get('ville', ''),
                wilaya=request.POST.get('wilaya', ''),
                numero_permis=request.POST['numero_permis'],
                date_obtention_permis=date_obtention,
                date_expiration_permis=date_expiration,
                date_embauche=request.POST['date_embauche'],
                salaire=request.POST.get('salaire', None),
                statut_disponibilite=request.POST.get('statut_disponibilite', 'DISPONIBLE'),
                remarques=request.POST.get('remarques', ''),
            )
            chauffeur.save()
            
            messages.success(request, f'Chauffeur {chauffeur.prenom} {chauffeur.nom} créé avec succès!')
            return redirect('detail_chauffeur', chauffeur_id=chauffeur.id)
            
        except Exception as e:
            messages.error(request, f'Erreur lors de la création du chauffeur: {str(e)}')
    
    return render(request, 'chauffeurs/creer.html')

# ========== MODIFIER UN CHAUFFEUR ==========
def modifier_chauffeur(request, chauffeur_id):
    """
    Formulaire de modification d'un chauffeur existant
    """
    chauffeur = get_object_or_404(Chauffeur, id=chauffeur_id)
    
    if request.method == 'POST':
        try:
            from datetime import datetime
            
            # Récupérer et valider les dates
            date_obtention = datetime.strptime(request.POST['date_obtention_permis'], '%Y-%m-%d').date()
            date_expiration = datetime.strptime(request.POST['date_expiration_permis'], '%Y-%m-%d').date()
            
            # VALIDATION : date obtention doit être AVANT date expiration
            if date_obtention >= date_expiration:
                messages.error(
                    request, 
                    'Erreur : La date d\'obtention du permis doit être antérieure à la date d\'expiration !'
                )
                return render(request, 'chauffeurs/modifier.html', {'chauffeur': chauffeur})
            
            chauffeur.nom = request.POST['nom']
            chauffeur.prenom = request.POST['prenom']
            chauffeur.date_naissance = request.POST['date_naissance']
            chauffeur.telephone = request.POST['telephone']
            chauffeur.email = request.POST.get('email', '')
            chauffeur.adresse = request.POST.get('adresse', '')
            chauffeur.ville = request.POST.get('ville', '')
            chauffeur.wilaya = request.POST.get('wilaya', '')
            chauffeur.numero_permis = request.POST['numero_permis']
            chauffeur.date_obtention_permis = date_obtention
            chauffeur.date_expiration_permis = date_expiration
            chauffeur.date_embauche = request.POST['date_embauche']
            chauffeur.salaire = request.POST.get('salaire', None)
            chauffeur.statut_disponibilite = request.POST.get('statut_disponibilite', 'DISPONIBLE')
            chauffeur.remarques = request.POST.get('remarques', '')
            
            chauffeur.save()
            
            messages.success(request, f'Chauffeur {chauffeur.prenom} {chauffeur.nom} modifié avec succès!')
            return redirect('detail_chauffeur', chauffeur_id=chauffeur.id)
            
        except Exception as e:
            messages.error(request, f'Erreur lors de la modification: {str(e)}')
    
    return render(request, 'chauffeurs/modifier.html', {
        'chauffeur': chauffeur,
    })

# ========== SUPPRIMER UN CHAUFFEUR ==========
def supprimer_chauffeur(request, chauffeur_id):
    """
    Suppression d'un chauffeur (avec confirmation)
    """
    chauffeur = get_object_or_404(Chauffeur, id=chauffeur_id)
    
    if request.method == 'POST':
        try:
            nom_complet = f"{chauffeur.prenom} {chauffeur.nom}"
            chauffeur.delete()
            messages.success(request, f'Chauffeur {nom_complet} supprimé avec succès!')
            return redirect('liste_chauffeurs')
            
        except Exception as e:
            messages.error(request, f'Erreur lors de la suppression: {str(e)}')
            return redirect('detail_chauffeur', chauffeur_id=chauffeur_id)
    
    return render(request, 'chauffeurs/supprimer.html', {
        'chauffeur': chauffeur,
    })