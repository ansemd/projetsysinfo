from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import HttpResponse
from django.core.exceptions import ValidationError
from django.db.models import Q, Count, Sum, Prefetch
from django.urls import reverse
from .models import Client, Chauffeur, Vehicule, TypeService, Facture, Destination, Tarification, Tournee, Expedition, TrackingExpedition, Facture, Paiement, Incident, HistoriqueIncident, Reclamation, HistoriqueReclamation, Notification
from .forms import ClientForm, ChauffeurForm, VehiculeForm, TypeServiceForm, DestinationForm, TarificationForm, TourneeForm, ExpeditionForm, FactureForm, PaiementForm, IncidentForm, IncidentModificationForm, IncidentResolutionForm, AssignationForm, ReclamationForm, ReclamationModificationForm, ReclamationReponseForm, ReclamationResolutionForm
from .utils import generer_pdf_fiche, generer_pdf_liste, IncidentService, ReclamationService
from django.utils import timezone


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

def exporter_clients_pdf(request):
    clients = Client.objects.all()
    headers = ['Id', 'Nom', 'Prénom', 'Téléphone', 'Solde']
    data = [[f"CL-{c.id:03d}", c.nom, c.prenom, c.telephone, c.solde] for c in clients]
    return generer_pdf_liste("Liste Clients", headers, data, "clients")

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

def exporter_client_detail_pdf(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    
    # Récupérer expéditions et factures
    expeditions = client.expedition_set.all()
    factures = Facture.objects.filter(client=client).order_by('-date_creation')[:5]
    
    # ========== UNE SEULE SECTION AVEC TOUS LES CHAMPS ==========
    sections = [
        {
            'titre': 'Informations du Client',
            'data': [
                ['ID Client', f"CL-{client.id:03d}"],
                ['Nom', client.nom],
                ['Prénom', client.prenom],
                ['Date de Naissance', client.date_naissance.strftime('%d/%m/%Y') if client.date_naissance else 'Non renseignée'],
                ['Téléphone', client.telephone],
                ['Email', client.email or 'Non renseigné'],
                ['Adresse', client.adresse or 'Non renseignée'],
                ['Ville', client.ville or 'Non renseignée'],
                ['Wilaya', client.wilaya or 'Non renseignée'],
                ['Solde', f"{client.solde:,.2f} DA"],
                ['Date d\'inscription', client.date_inscription.strftime('%d/%m/%Y %H:%M')],
                ['Dernière modification', client.date_modification.strftime('%d/%m/%Y %H:%M')],
                ['Remarques', client.remarques or 'Aucune remarque'],
            ]
        }
    ]
    
    # ========== Expéditions ==========
    if expeditions.exists():
        exp_headers = ['N° Expédition', 'Destination', 'Montant', 'Statut']
        exp_data = [exp_headers]
        
        for exp in expeditions[:10]:
            exp_data.append([
                exp.get_numero_expedition(),
                f"{exp.destination.ville}",
                f"{exp.montant_total:,.2f} DA",
                exp.get_statut_display()
            ])
        
        sections.append({
            'titre': f'Historique des Expéditions ({expeditions.count()})',
            'data': exp_data
        })
    
    # ========== Factures ==========
    if factures.exists():
        facture_headers = ['N° Facture', 'Date', 'Montant TTC', 'Statut']
        facture_data = [facture_headers]
        
        for f in factures:
            facture_data.append([
                f.numero_facture,
                f.date_creation.strftime('%d/%m/%Y'),
                f"{f.montant_ttc:,.2f} DA",
                f.get_statut_display()
            ])
        
        sections.append({
            'titre': 'Factures Récentes (5 dernières)',
            'data': facture_data
        })
    
    # Générer le PDF
    return generer_pdf_fiche(
        titre_document=f"Fiche Client - {client.prenom} {client.nom}",
        sections=sections,
        nom_fichier_base=f"client_{client.id:03d}",
        remarques=None  # Déjà dans la table
    )

def creer_client(request):
    """
    Formulaire de création d'un nouveau client
    """
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save()
            messages.success(request, f'Client {client.prenom} {client.nom} créé avec succès!')
            return redirect('detail_client', client_id=client.id)
        else:
            # Les erreurs sont automatiquement passées au template via form.errors
            messages.error(request, 'Erreur de validation. Veuillez vérifier les champs.')
    else:
        form = ClientForm()
    
    return render(request, 'clients/creer.html', {'form': form})

def modifier_client(request, client_id):
    """
    Formulaire de modification d'un client existant
    """
    client = get_object_or_404(Client, id=client_id)
    
    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            client = form.save()
            messages.success(request, f'Client {client.prenom} {client.nom} modifié avec succès!')
            return redirect('detail_client', client_id=client.id)
        else:
            messages.error(request, 'Erreur de validation. Veuillez vérifier les champs.')
    else:
        form = ClientForm(instance=client)
    
    return render(request, 'clients/modifier.html', {
        'form': form,
        'client': client,
    })

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

def liste_chauffeurs(request):
    """
    Page principale : Liste de tous les chauffeurs avec recherche et filtrage par statut
    """
    search = request.GET.get('search', '')
    filtre_statut = request.GET.get('statut', '')  
    
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

def exporter_chauffeurs_pdf(request):
    """
    Export PDF de la liste complète des chauffeurs
    """
    chauffeurs = Chauffeur.objects.all().order_by('nom', 'prenom')
    
    headers = ['ID', 'Nom', 'Prénom', 'Téléphone', 'Permis', 'Statut']
    
    data = []
    for chauffeur in chauffeurs:
        data.append([
            f"CH-{chauffeur.id:03d}",
            chauffeur.nom,
            chauffeur.prenom,
            chauffeur.telephone,
            chauffeur.numero_permis,
            chauffeur.get_statut_disponibilite_display()
        ])
    
    return generer_pdf_liste(
        titre_document="Liste des Chauffeurs",
        headers=headers,
        data_rows=data,
        nom_fichier_base="chauffeurs"
    )

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

def exporter_chauffeur_detail_pdf(request, chauffeur_id):
    """
    Export PDF de la fiche détaillée d'un chauffeur
    """
    chauffeur = get_object_or_404(Chauffeur, id=chauffeur_id)
    
    # Récupérer les tournées du chauffeur
    tournees = chauffeur.tournee_set.all()
    
    # ========== UNE SEULE SECTION AVEC TOUS LES CHAMPS ==========
    sections = [
        {
            'titre': 'Informations du Chauffeur',
            'data': [
                ['ID Chauffeur', f"CH-{chauffeur.id:03d}"],
                ['Nom', chauffeur.nom],
                ['Prénom', chauffeur.prenom],
                ['Date de Naissance', chauffeur.date_naissance.strftime('%d/%m/%Y') if chauffeur.date_naissance else 'Non renseignée'],
                ['Téléphone', chauffeur.telephone],
                ['Email', chauffeur.email or 'Non renseigné'],
                ['Adresse', chauffeur.adresse or 'Non renseignée'],
                ['Numéro de Permis', chauffeur.numero_permis],
                ['Date d\'obtention permis', chauffeur.date_obtention_permis.strftime('%d/%m/%Y') if chauffeur.date_obtention_permis else 'Non renseignée'],
                ['Date d\'expiration permis', chauffeur.date_expiration_permis.strftime('%d/%m/%Y') if chauffeur.date_expiration_permis else 'Non renseignée'],
                ['Date d\'embauche', chauffeur.date_embauche.strftime('%d/%m/%Y') if chauffeur.date_embauche else 'Non renseignée'],
                ['Salaire', f"{chauffeur.salaire:,.2f} DA" if chauffeur.salaire else 'Non renseigné'],
                ['Statut', chauffeur.get_statut_disponibilite_display()],
                ['Date de création', chauffeur.date_creation.strftime('%d/%m/%Y %H:%M')],
                ['Dernière modification', chauffeur.date_modification.strftime('%d/%m/%Y %H:%M')],
                ['Remarques', chauffeur.remarques or 'Aucune remarque'],
            ]
        }
    ]
    
    # ========== Tournées ==========
    if tournees.exists():
        tournee_headers = ['Zone', 'Date Départ', 'Véhicule', 'Statut']
        tournee_data = [tournee_headers]
        
        for t in tournees[:10]:  # Limiter à 10
            tournee_data.append([
                t.zone_cible,
                t.date_depart.strftime('%d/%m/%Y %H:%M'),
                t.vehicule.numero_immatriculation if t.vehicule else '-',
                t.get_statut_display()
            ])
        
        sections.append({
            'titre': f'Historique des Tournées ({tournees.count()})',
            'data': tournee_data
        })
    
    # Générer le PDF
    return generer_pdf_fiche(
        titre_document=f"Fiche Chauffeur - {chauffeur.prenom} {chauffeur.nom}",
        sections=sections,
        nom_fichier_base=f"chauffeur_{chauffeur.id:03d}",
        remarques=None  # Déjà dans la table
    )

def creer_chauffeur(request):
    """
    Formulaire de création d'un nouveau chauffeur
    """
    if request.method == 'POST':
        form = ChauffeurForm(request.POST)
        if form.is_valid():
            chauffeur = form.save()
            messages.success(request, f'Chauffeur {chauffeur.prenom} {chauffeur.nom} créé avec succès!')
            return redirect('detail_chauffeur', chauffeur_id=chauffeur.id)
        else:
            # Les erreurs sont automatiquement passées au template via form.errors
            messages.error(request, 'Erreur de validation. Veuillez vérifier les champs.')
    else:
        form = ChauffeurForm()
    
    return render(request, 'chauffeurs/creer.html', {'form': form})

def modifier_chauffeur(request, chauffeur_id):
    """
    Formulaire de modification d'un chauffeur existant
    """
    chauffeur = get_object_or_404(Chauffeur, id=chauffeur_id)
    
    if request.method == 'POST':
        form = ChauffeurForm(request.POST, instance=chauffeur)
        if form.is_valid():
            chauffeur = form.save()
            messages.success(request, f'Chauffeur {chauffeur.prenom} {chauffeur.nom} modifié avec succès!')
            return redirect('detail_chauffeur', chauffeur_id=chauffeur.id)
        else:
            messages.error(request, 'Erreur de validation. Veuillez vérifier les champs.')
    else:
        form = ChauffeurForm(instance=chauffeur)
    
    return render(request, 'chauffeurs/modifier.html', {
        'form': form,
        'chauffeur': chauffeur,
    })

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

def liste_vehicules(request):
    """
    Page principale : Liste de tous les véhicules avec recherche et filtrage par statut
    """
    search = request.GET.get('search', '')
    filtre_statut = request.GET.get('statut', '')
    
    # Base queryset
    vehicules = Vehicule.objects.all()
    
    # Recherche
    if search:
        vehicules = vehicules.filter(
            Q(numero_immatriculation__icontains=search) | 
            Q(marque__icontains=search) |
            Q(modele__icontains=search)
        )
    
    # Filtrage par statut
    if filtre_statut:
        vehicules = vehicules.filter(statut=filtre_statut)
    
    vehicules = vehicules.order_by('-date_creation')
    
    # Statistiques globales
    stats = {
        'total_vehicules': Vehicule.objects.count(),
        'disponibles': Vehicule.objects.filter(statut='DISPONIBLE').count(),
        'en_tournee': Vehicule.objects.filter(statut='EN_TOURNEE').count(),
        'en_maintenance': Vehicule.objects.filter(statut='EN_MAINTENANCE').count(),
        'hors_service': Vehicule.objects.filter(statut='HORS_SERVICE').count(),
    }
    
    # Liste des statuts pour le filtre
    statuts = [
        ('DISPONIBLE', 'Disponible'),
        ('EN_TOURNEE', 'En tournée'),
        ('EN_MAINTENANCE', 'En maintenance'),
        ('HORS_SERVICE', 'Hors service'),
    ]
    
    return render(request, 'vehicules/liste.html', {
        'vehicules': vehicules,
        'search': search,
        'filtre_statut': filtre_statut,
        'statuts': statuts,
        'stats': stats,
    })

def exporter_vehicules_pdf(request):
    """
    Export PDF de la liste complète des véhicules
    """
    vehicules = Vehicule.objects.all().order_by('numero_immatriculation')
    
    headers = ['Immatriculation', 'Marque', 'Modèle', 'Type', 'Capacité (kg)', 'Statut']
    
    data = []
    for vehicule in vehicules:
        data.append([
            vehicule.numero_immatriculation,
            vehicule.marque,
            vehicule.modele,
            vehicule.get_type_vehicule_display(),
            str(vehicule.capacite_poids),
            vehicule.get_statut_display()
        ])
    
    return generer_pdf_liste(
        titre_document="Liste des Véhicules",
        headers=headers,
        data_rows=data,
        nom_fichier_base="vehicules"
    )

def modifier_statut_vehicule(request, vehicule_id):
    """
    Modifie uniquement le statut d'un véhicule (appelé depuis la liste)
    """
    if request.method == 'POST':
        vehicule = get_object_or_404(Vehicule, id=vehicule_id)
        nouveau_statut = request.POST.get('statut')
        
        if nouveau_statut in ['DISPONIBLE', 'EN_TOURNEE', 'EN_MAINTENANCE', 'HORS_SERVICE']:
            vehicule.statut = nouveau_statut
            vehicule.save()
            messages.success(request, f'Statut du véhicule {vehicule.numero_immatriculation} modifié avec succès!')
        else:
            messages.error(request, 'Statut invalide')
    
    return redirect('liste_vehicules')

def detail_vehicule(request, vehicule_id):
    """
    Affiche tous les détails d'un véhicule + sa tournée actuelle (EN_COURS ou PREVUE)
    """
    vehicule = get_object_or_404(Vehicule, id=vehicule_id)
    
    # Récupérer SEULEMENT la tournée actuelle (EN_COURS ou PREVUE)
    tournee_actuelle = vehicule.tournee_set.filter(
        statut__in=['EN_COURS', 'PREVUE']
    ).order_by('-date_creation').first()
    
    # Statistiques du véhicule (toutes les tournées)
    all_tournees = vehicule.tournee_set.all()
    stats_vehicule = {
        'total_tournees': all_tournees.count(),
        'tournees_prevues': all_tournees.filter(statut='PREVUE').count(),
        'tournees_en_cours': all_tournees.filter(statut='EN_COURS').count(),
        'tournees_terminees': all_tournees.filter(statut='TERMINEE').count(),
    }
    
    return render(request, 'vehicules/detail.html', {
        'vehicule': vehicule,
        'tournee_actuelle': tournee_actuelle,
        'stats_vehicule': stats_vehicule,
    })

def exporter_vehicule_detail_pdf(request, vehicule_id):
    """
    Export PDF de la fiche détaillée d'un véhicule
    """
    vehicule = get_object_or_404(Vehicule, id=vehicule_id)
    
    # Récupérer les tournées du véhicule
    tournees = vehicule.tournee_set.all()
    
    # ========== UNE SEULE SECTION AVEC TOUS LES CHAMPS ==========
    sections = [
        {
            'titre': 'Informations du Véhicule',
            'data': [
                ['Immatriculation', vehicule.numero_immatriculation],
                ['Marque', vehicule.marque],
                ['Modèle', vehicule.modele],
                ['Année', str(vehicule.annee) if vehicule.annee else 'Non renseignée'],
                ['Type de véhicule', vehicule.get_type_vehicule_display()],
                ['État', vehicule.get_etat_display()],
                ['Statut', vehicule.get_statut_display()],
                ['Date d\'acquisition', vehicule.date_acquisition.strftime('%d/%m/%Y')],
                ['Capacité poids', f"{vehicule.capacite_poids} kg"],
                ['Capacité volume', f"{vehicule.capacite_volume} m³" if vehicule.capacite_volume else 'Non renseignée'],
                ['Consommation moyenne', f"{vehicule.consommation_moyenne} L/100km"],
                ['Kilométrage', f"{vehicule.kilometrage} km"],
                ['Dernière révision', vehicule.date_derniere_revision.strftime('%d/%m/%Y') if vehicule.date_derniere_revision else 'Aucune révision'],
                ['Prochaine révision', vehicule.date_prochaine_revision.strftime('%d/%m/%Y') if vehicule.date_prochaine_revision else 'Non calculée'],
                ['Date de création', vehicule.date_creation.strftime('%d/%m/%Y %H:%M')],
                ['Dernière modification', vehicule.date_modification.strftime('%d/%m/%Y %H:%M')],
                ['Remarques', vehicule.remarques or 'Aucune remarque'],
            ]
        }
    ]
    
    # ========== Tournées ==========
    if tournees.exists():
        tournee_headers = ['Zone', 'Date Départ', 'Chauffeur', 'Statut']
        tournee_data = [tournee_headers]
        
        for t in tournees[:10]:  # Limiter à 10
            tournee_data.append([
                t.zone_cible,
                t.date_depart.strftime('%d/%m/%Y %H:%M'),
                f"{t.chauffeur.prenom} {t.chauffeur.nom}" if t.chauffeur else '-',
                t.get_statut_display()
            ])
        
        sections.append({
            'titre': f'Historique des Tournées ({tournees.count()})',
            'data': tournee_data
        })
    
    # Générer le PDF
    return generer_pdf_fiche(
        titre_document=f"Fiche Véhicule - {vehicule.numero_immatriculation}",
        sections=sections,
        nom_fichier_base=f"vehicule_{vehicule.numero_immatriculation}",
        remarques=None  # Déjà dans la table
    )

def creer_vehicule(request):
    if request.method == 'POST':
        form = VehiculeForm(request.POST)
        if form.is_valid():
            vehicule = form.save()  
            
            messages.success(request, f'Véhicule {vehicule.numero_immatriculation} créé avec succès!')
            return redirect('detail_vehicule', vehicule_id=vehicule.id)
        else:
            messages.error(request, 'Erreur de validation. Veuillez vérifier les champs.')
    else:
        form = VehiculeForm()
    
    return render(request, 'vehicules/creer.html', {'form': form})

def modifier_vehicule(request, vehicule_id):
    vehicule = get_object_or_404(Vehicule, id=vehicule_id)
    
    if request.method == 'POST':
        form = VehiculeForm(request.POST, instance=vehicule)
        if form.is_valid():
            vehicule = form.save() 
            
            messages.success(request, f'Véhicule {vehicule.numero_immatriculation} modifié avec succès!')
            return redirect('detail_vehicule', vehicule_id=vehicule.id)
        else:
            messages.error(request, 'Erreur de validation. Veuillez vérifier les champs.')
    else:
        form = VehiculeForm(instance=vehicule)
    
    return render(request, 'vehicules/modifier.html', {
        'form': form,
        'vehicule': vehicule,
    })

def supprimer_vehicule(request, vehicule_id):
    """
    Suppression d'un véhicule (avec confirmation)
    """
    vehicule = get_object_or_404(Vehicule, id=vehicule_id)
    
    if request.method == 'POST':
        try:
            numero = vehicule.numero_immatriculation
            vehicule.delete()
            messages.success(request, f'Véhicule {numero} supprimé avec succès!')
            return redirect('liste_vehicules')
            
        except Exception as e:
            messages.error(request, f'Erreur lors de la suppression: {str(e)}')
            return redirect('detail_vehicule', vehicule_id=vehicule_id)
    
    return render(request, 'vehicules/supprimer.html', {
        'vehicule': vehicule,
    })

def liste_typeservices(request):
    """
    Page principale : Liste de tous les types de service
    """
    typeservices = TypeService.objects.all().order_by('type_service')
    
    return render(request, 'typeservices/liste.html', {
        'typeservices': typeservices,
    })

def exporter_typeservices_pdf(request):
    """
    Export PDF de la liste complète des types de service
    """
    typeservices = TypeService.objects.all().order_by('type_service')
    
    headers = ['Type de Service', 'Description', 'Expéditions', 'Tarifications']
    
    data = []
    for ts in typeservices:
        description = ts.description[:50] + '...' if ts.description and len(ts.description) > 50 else (ts.description or '-')
        data.append([
            ts.get_type_service_display(),
            description,
            str(ts.expedition_set.count()),
            str(ts.tarification_set.count())
        ])
    
    return generer_pdf_liste(
        titre_document="Liste des Types de Service",
        headers=headers,
        data_rows=data,
        nom_fichier_base="types_service"
    )

def detail_typeservice(request, typeservice_id):
    """
    Affiche tous les détails d'un type de service
    + Nombre d'expéditions utilisant ce type
    """
    typeservice = get_object_or_404(TypeService, id=typeservice_id)
    
    # Statistiques
    nb_expeditions = typeservice.expedition_set.count()
    
    return render(request, 'typeservices/detail.html', {
        'typeservice': typeservice,
        'nb_expeditions': nb_expeditions,
    })

def exporter_typeservice_detail_pdf(request, typeservice_id):
    """
    Export PDF de la fiche détaillée d'un type de service
    """
    typeservice = get_object_or_404(TypeService, id=typeservice_id)
    
    # Récupérer les expéditions et tarifications
    expeditions = typeservice.expedition_set.all()
    tarifications = typeservice.tarification_set.all()
    
    # ========== UNE SEULE SECTION AVEC TOUS LES CHAMPS ==========
    sections = [
        {
            'titre': 'Informations du Type de Service',
            'data': [
                ['Type de Service', typeservice.get_type_service_display()],
                ['Description', typeservice.description or 'Aucune description'],
            ]
        },
        {
            'titre': 'Statistiques d\'Utilisation',
            'data': [
                ['Nombre d\'expéditions', str(expeditions.count())],
                ['Nombre de tarifications', str(tarifications.count())],
            ]
        }
    ]
    
    # Générer le PDF
    return generer_pdf_fiche(
        titre_document=f"Fiche Type de Service - {typeservice.get_type_service_display()}",
        sections=sections,
        nom_fichier_base=f"typeservice_{typeservice.type_service}",
        remarques=None
    )

def creer_typeservice(request):
    """
    Formulaire de création d'un nouveau type de service
    """
    if request.method == 'POST':
        form = TypeServiceForm(request.POST)
        if form.is_valid():
            typeservice = form.save()
            messages.success(request, f'Type de service "{typeservice.type_service}" créé avec succès!')
            return redirect('detail_typeservice', typeservice_id=typeservice.id)
        else:
            messages.error(request, 'Erreur de validation. Veuillez vérifier les champs.')
    else:
        form = TypeServiceForm()
    
    return render(request, 'typeservices/creer.html', {'form': form})

def modifier_typeservice(request, typeservice_id):
    """
    Formulaire de modification d'un type de service existant
    """
    typeservice = get_object_or_404(TypeService, id=typeservice_id)
    
    if request.method == 'POST':
        form = TypeServiceForm(request.POST, instance=typeservice)
        if form.is_valid():
            typeservice = form.save()
            messages.success(request, f'Type de service "{typeservice.type_service}" modifié avec succès!')
            return redirect('detail_typeservice', typeservice_id=typeservice.id)
        else:
            messages.error(request, 'Erreur de validation. Veuillez vérifier les champs.')
    else:
        form = TypeServiceForm(instance=typeservice)
    
    return render(request, 'typeservices/modifier.html', {
        'form': form,
        'typeservice': typeservice,
    })

def supprimer_typeservice(request, typeservice_id):
    """
    Suppression d'un type de service (avec validation)
    ATTENTION : Ne pas supprimer si utilisé dans des expéditions ou tarifications
    """
    typeservice = get_object_or_404(TypeService, id=typeservice_id)
    
    # Vérifier si utilisé
    nb_expeditions = typeservice.expedition_set.count()
    nb_tarifications = typeservice.tarification_set.count()
    
    if request.method == 'POST':
        try:
            if nb_expeditions > 0:
                raise ValidationError(
                    f"Impossible de supprimer : {nb_expeditions} expédition(s) utilisent ce type de service."
                )
            
            if nb_tarifications > 0:
                raise ValidationError(
                    f"Impossible de supprimer : {nb_tarifications} tarification(s) utilisent ce type de service."
                )
            
            type_nom = typeservice.type_service
            typeservice.delete()
            messages.success(request, f'Type de service "{type_nom}" supprimé avec succès!')
            return redirect('liste_typeservices')
            
        except ValidationError as e:
            messages.error(request, str(e))
            return redirect('detail_typeservice', typeservice_id=typeservice_id)
        except Exception as e:
            messages.error(request, f'Erreur lors de la suppression: {str(e)}')
            return redirect('detail_typeservice', typeservice_id=typeservice_id)
    
    return render(request, 'typeservices/supprimer.html', {
        'typeservice': typeservice,
        'nb_expeditions': nb_expeditions,
        'nb_tarifications': nb_tarifications,
    })

def liste_destinations(request):
    """
    Liste de toutes les destinations avec recherche
    """
    search = request.GET.get('search', '')
    zone = request.GET.get('zone', '')
    
    destinations = Destination.objects.all()
    
    if search:
        destinations = destinations.filter(
            Q(ville__icontains=search) |
            Q(wilaya__icontains=search) |
            Q(pays__icontains=search)
        )
    
    if zone:
        destinations = destinations.filter(zone_logistique=zone)
    
    destinations = destinations.order_by('wilaya', 'ville')
    
    # Stats
    stats = {
        'total_destinations': Destination.objects.count(),
        'zone_centre': Destination.objects.filter(zone_logistique='CENTRE').count(),
        'zone_est': Destination.objects.filter(zone_logistique='EST').count(),
        'zone_ouest': Destination.objects.filter(zone_logistique='OUEST').count(),
        'zone_sud': Destination.objects.filter(zone_logistique='SUD').count(),
    }
    
    zones = [
        ('CENTRE', 'Centre'),
        ('EST', 'Est'),
        ('OUEST', 'Ouest'),
        ('SUD', 'Sud'),
    ]
    
    return render(request, 'destinations/liste.html', {
        'destinations': destinations,
        'search': search,
        'zone_filtre': zone,
        'zones': zones,
        'stats': stats,
    })

def exporter_destinations_pdf(request):
    """
    Export PDF de la liste complète des destinations
    """
    destinations = Destination.objects.all().order_by('wilaya', 'ville')
    
    headers = ['Ville', 'Wilaya', 'Zone', 'Distance (km)', 'Tarif Base (DA)', 'Délai (j)']
    
    data = []
    for dest in destinations:
        data.append([
            dest.ville or '-',
            dest.wilaya,
            dest.get_zone_logistique_display(),
            str(dest.distance_estimee),
            f"{dest.tarif_base:,.2f}",
            str(dest.delai_livraison_estime)
        ])
    
    return generer_pdf_liste(
        titre_document="Liste des Destinations",
        headers=headers,
        data_rows=data,
        nom_fichier_base="destinations"
    )

def detail_destination(request, destination_id):
    """
    Détails d'une destination + statistiques
    """
    destination = get_object_or_404(Destination, id=destination_id)
    
    # Stats
    nb_tarifications = destination.tarification_set.count()
    nb_expeditions = destination.expedition_set.count()
    
    return render(request, 'destinations/detail.html', {
        'destination': destination,
        'nb_tarifications': nb_tarifications,
        'nb_expeditions': nb_expeditions,
    })

def exporter_destination_detail_pdf(request, destination_id):
    """
    Export PDF de la fiche détaillée d'une destination
    """
    destination = get_object_or_404(Destination, id=destination_id)
    
    # Stats
    nb_tarifications = destination.tarification_set.count()
    nb_expeditions = destination.expedition_set.count()
    
    # Une seule section avec tous les champs
    sections = [
        {
            'titre': 'Informations de la Destination',
            'data': [
                ['Ville', destination.ville or 'Non renseignée'],
                ['Wilaya', destination.wilaya],
                ['Pays', destination.pays],
                ['Zone Géographique', destination.get_zone_geographique_display()],
                ['Zone Logistique', destination.get_zone_logistique_display()],
                ['Distance estimée', f"{destination.distance_estimee} km"],
                ['Tarif de base', f"{destination.tarif_base:,.2f} DA"],
                ['Délai de livraison estimé', f"{destination.delai_livraison_estime} jour(s)"],
                ['Code postal', destination.code_postal or 'Non renseigné'],
                ['Date de création', destination.date_creation.strftime('%d/%m/%Y %H:%M')],
                ['Dernière modification', destination.date_modification.strftime('%d/%m/%Y %H:%M')],
                ['Remarques', destination.remarques or 'Aucune remarque'],
            ]
        },
        {
            'titre': 'Statistiques d\'Utilisation',
            'data': [
                ['Nombre de tarifications', str(nb_tarifications)],
                ['Nombre d\'expéditions', str(nb_expeditions)],
            ]
        }
    ]
    
    return generer_pdf_fiche(
        titre_document=f"Fiche Destination - {destination.ville} - {destination.wilaya}",
        sections=sections,
        nom_fichier_base=f"destination_{destination.id:03d}",
        remarques=None
    )

def creer_destination(request):
    """
    Créer une nouvelle destination
    """
    if request.method == 'POST':
        form = DestinationForm(request.POST)
        if form.is_valid():
            destination = form.save()
            messages.success(request, f'Destination "{destination.ville} - {destination.wilaya}" créée avec succès!')
            return redirect('detail_destination', destination_id=destination.id)
        else:
            messages.error(request, 'Erreur de validation. Veuillez vérifier les champs.')
    else:
        form = DestinationForm()
    
    return render(request, 'destinations/creer.html', {'form': form})

def modifier_destination(request, destination_id):
    """
    Modifier une destination existante
    """
    destination = get_object_or_404(Destination, id=destination_id)
    
    if request.method == 'POST':
        form = DestinationForm(request.POST, instance=destination)
        if form.is_valid():
            destination = form.save()
            messages.success(request, f'Destination "{destination.ville} - {destination.wilaya}" modifiée avec succès!')
            return redirect('detail_destination', destination_id=destination.id)
        else:
            messages.error(request, 'Erreur de validation. Veuillez vérifier les champs.')
    else:
        form = DestinationForm(instance=destination)
    
    return render(request, 'destinations/modifier.html', {
        'form': form,
        'destination': destination,
    })

def supprimer_destination(request, destination_id):
    """
    Supprimer une destination (avec validation)
    """
    destination = get_object_or_404(Destination, id=destination_id)
    
    # Vérifier si utilisée
    nb_tarifications = destination.tarification_set.count()
    nb_expeditions = destination.expedition_set.count()
    
    if request.method == 'POST':
        try:
            if nb_expeditions > 0:
                messages.error(request, f"Impossible de supprimer : {nb_expeditions} expédition(s) utilisent cette destination.")
                return redirect('detail_destination', destination_id=destination_id)
            
            if nb_tarifications > 0:
                messages.error(request, f"Impossible de supprimer : {nb_tarifications} tarification(s) utilisent cette destination.")
                return redirect('detail_destination', destination_id=destination_id)
            
            ville = destination.ville
            wilaya = destination.wilaya
            destination.delete()
            messages.success(request, f'Destination "{ville} - {wilaya}" supprimée avec succès!')
            return redirect('liste_destinations')
            
        except Exception as e:
            messages.error(request, f'Erreur lors de la suppression: {str(e)}')
            return redirect('detail_destination', destination_id=destination_id)
    
    return render(request, 'destinations/supprimer.html', {
        'destination': destination,
        'nb_tarifications': nb_tarifications,
        'nb_expeditions': nb_expeditions,
    })

def liste_tarifications(request):
    """
    Liste de toutes les tarifications avec recherche et filtres
    """
    search = request.GET.get('search', '')
    type_service_filter = request.GET.get('type_service', '')
    zone_filter = request.GET.get('zone', '')
    
    tarifications = Tarification.objects.all().select_related('destination', 'type_service')
    
    if search:
        tarifications = tarifications.filter(
            Q(destination__ville__icontains=search) |
            Q(destination__wilaya__icontains=search)
        )
    
    if type_service_filter:
        tarifications = tarifications.filter(type_service__type_service=type_service_filter)
    
    if zone_filter:
        tarifications = tarifications.filter(destination__zone_logistique=zone_filter)
    
    tarifications = tarifications.order_by('destination__wilaya', 'destination__ville', 'type_service')
    
    # Stats
    stats = {
        'total_tarifications': Tarification.objects.count(),
        'standard': Tarification.objects.filter(type_service__type_service='STANDARD').count(),
        'express': Tarification.objects.filter(type_service__type_service='EXPRESS').count(),
        'international': Tarification.objects.filter(type_service__type_service='INTERNATIONAL').count(),
    }
    
    types_service = TypeService.objects.all()
    zones = [
        ('CENTRE', 'Centre'),
        ('EST', 'Est'),
        ('OUEST', 'Ouest'),
        ('SUD', 'Sud'),
    ]
    
    return render(request, 'tarifications/liste.html', {
        'tarifications': tarifications,
        'search': search,
        'type_service_filter': type_service_filter,
        'zone_filter': zone_filter,
        'types_service': types_service,
        'zones': zones,
        'stats': stats,
    })

def exporter_tarifications_pdf(request):
    """
    Export PDF de la liste complète des tarifications
    """
    tarifications = Tarification.objects.all().select_related('destination', 'type_service').order_by('destination__wilaya')
    
    headers = ['Destination', 'Type Service', 'Tarif Poids (DA/kg)', 'Tarif Volume (DA/m³)', 'Délai (j)']
    
    data = []
    for tarif in tarifications:
        data.append([
            f"{tarif.destination.ville} - {tarif.destination.wilaya}",
            tarif.type_service.get_type_service_display(),
            f"{tarif.tarif_poids:,.2f}",
            f"{tarif.tarif_volume:,.2f}",
            str(tarif.calculer_delai())
        ])
    
    return generer_pdf_liste(
        titre_document="Liste des Tarifications",
        headers=headers,
        data_rows=data,
        nom_fichier_base="tarifications"
    )

def detail_tarification(request, tarification_id):
    """
    Détails d'une tarification + statistiques
    """
    tarification = get_object_or_404(Tarification, id=tarification_id)
    
    # Stats
    nb_expeditions = tarification.destination.expedition_set.filter(
        type_service=tarification.type_service
    ).count()
    
    return render(request, 'tarifications/detail.html', {
        'tarification': tarification,
        'nb_expeditions': nb_expeditions,
    })

def exporter_tarification_detail_pdf(request, tarification_id):
    """
    Export PDF de la fiche détaillée d'une tarification
    """
    tarification = get_object_or_404(Tarification, id=tarification_id)
    
    # Stats
    nb_expeditions = tarification.destination.expedition_set.filter(
        type_service=tarification.type_service
    ).count()
    
    # Une seule section avec tous les champs
    sections = [
        {
            'titre': 'Informations de la Tarification',
            'data': [
                ['Destination', f"{tarification.destination.ville} - {tarification.destination.wilaya}"],
                ['Pays', tarification.destination.pays],
                ['Zone Logistique', tarification.destination.get_zone_logistique_display()],
                ['Type de Service', tarification.type_service.get_type_service_display()],
                ['Tarif Poids', f"{tarification.tarif_poids:,.2f} DA/kg"],
                ['Tarif Volume', f"{tarification.tarif_volume:,.2f} DA/m³"],
                ['Délai de livraison', f"{tarification.calculer_delai()} jour(s)"],
            ]
        },
        {
            'titre': 'Statistiques d\'Utilisation',
            'data': [
                ['Nombre d\'expéditions', str(nb_expeditions)],
            ]
        }
    ]
    
    return generer_pdf_fiche(
        titre_document=f"Fiche Tarification - {tarification.destination.ville} - {tarification.type_service.get_type_service_display()}",
        sections=sections,
        nom_fichier_base=f"tarification_{tarification.id:03d}",
        remarques=None
    )

def creer_tarification(request):
    """
    Créer une nouvelle tarification
    """
    if request.method == 'POST':
        form = TarificationForm(request.POST)
        if form.is_valid():
            tarification = form.save()
            messages.success(request, f'Tarification créée avec succès!')
            return redirect('detail_tarification', tarification_id=tarification.id)
        else:
            messages.error(request, 'Erreur de validation. Veuillez vérifier les champs.')
    else:
        form = TarificationForm()
    
    return render(request, 'tarifications/creer.html', {'form': form})

def modifier_tarification(request, tarification_id):
    """
    Modifier une tarification existante
    """
    tarification = get_object_or_404(Tarification, id=tarification_id)
    
    if request.method == 'POST':
        form = TarificationForm(request.POST, instance=tarification)
        if form.is_valid():
            tarification = form.save()
            messages.success(request, f'Tarification modifiée avec succès!')
            return redirect('detail_tarification', tarification_id=tarification.id)
        else:
            messages.error(request, 'Erreur de validation. Veuillez vérifier les champs.')
    else:
        form = TarificationForm(instance=tarification)
    
    return render(request, 'tarifications/modifier.html', {
        'form': form,
        'tarification': tarification,
    })

def supprimer_tarification(request, tarification_id):
    """
    Supprimer une tarification (avec validation)
    """
    tarification = get_object_or_404(Tarification, id=tarification_id)
    
    # Vérifier si utilisée
    nb_expeditions = tarification.destination.expedition_set.filter(
        type_service=tarification.type_service
    ).count()
    
    if request.method == 'POST':
        try:
            if nb_expeditions > 0:
                messages.error(request, f"Impossible de supprimer : {nb_expeditions} expédition(s) utilisent cette tarification.")
                return redirect('detail_tarification', tarification_id=tarification_id)
            
            tarification.delete()
            messages.success(request, f'Tarification supprimée avec succès!')
            return redirect('liste_tarifications')
            
        except Exception as e:
            messages.error(request, f'Erreur lors de la suppression: {str(e)}')
            return redirect('detail_tarification', tarification_id=tarification_id)
    
    return render(request, 'tarifications/supprimer.html', {
        'tarification': tarification,
        'nb_expeditions': nb_expeditions,
    })

def liste_tournees(request):
    """
    Liste des tournées avec recherche, filtres et statistiques
    """
    tournees = Tournee.objects.all().select_related('chauffeur', 'vehicule')
    
    search = request.GET.get('search', '')
    if search:
        tournees = tournees.filter(
            Q(chauffeur__nom__icontains=search) |
            Q(chauffeur__prenom__icontains=search) |
            Q(vehicule__numero_immatriculation__icontains=search)
        )
    
    # ========== FILTRES ==========
    statut_filter = request.GET.get('statut', '')
    if statut_filter:
        tournees = tournees.filter(statut=statut_filter)
    
    zone_filter = request.GET.get('zone', '')
    if zone_filter:
        tournees = tournees.filter(zone_cible=zone_filter)
    
    # ========== ANNOTATION ==========
    tournees = tournees.annotate(nb_expeditions=Count('expeditions'))
    tournees = tournees.order_by('-date_depart')
    
    # ========== STATISTIQUES ==========
    stats = {
        'total_tournees': Tournee.objects.count(),
        'prevues': Tournee.objects.filter(statut='PREVUE').count(),
        'en_cours': Tournee.objects.filter(statut='EN_COURS').count(),
        'terminees': Tournee.objects.filter(statut='TERMINEE').count(),
    }
    
    # ========== STATUTS ==========
    statuts = [
        ('PREVUE', 'Prévue'),
        ('EN_COURS', 'En cours'),
        ('TERMINEE', 'Terminée'),
    ]
    
    zones = [
        ('CENTRE', 'Centre'),
        ('EST', 'Est'),
        ('OUEST', 'Ouest'),
        ('SUD', 'Sud'),
    ]
    
    return render(request, 'tournees/liste.html', {
        'tournees': tournees,
        'search': search,
        'statut_filter': statut_filter,
        'zone_filter': zone_filter,
        'stats': stats,
        'statuts': statuts,
        'zones': zones,
    })

def exporter_tournees_pdf(request):
    """
    Exporte la liste de toutes les tournées en PDF
    """
    tournees = Tournee.objects.all().select_related('chauffeur', 'vehicule').order_by('-date_depart')
    
    headers = ['ID', 'Chauffeur', 'Véhicule', 'Date départ', 'Zone', 'Statut']
    
    data = [
        [
            f"#{t.id}",
            f"{t.chauffeur.prenom} {t.chauffeur.nom}",
            t.vehicule.numero_immatriculation,
            t.date_depart.strftime('%d/%m/%Y %H:%M'),
            t.get_zone_cible_display(),
            t.get_statut_display()
        ]
        for t in tournees
    ]
    
    return generer_pdf_liste("Liste des Tournées", headers, data, "tournees")

def modifier_statut_tournee(request, tournee_id):
    """
    Modifie le statut d'une tournée
    Cette fonction marche depuis :
    - Le dashboard (home)
    - La liste des tournées
    
    Redirige vers la page d'origine grâce au paramètre 'source'
    """
    if request.method == 'POST':
        tournee = get_object_or_404(Tournee, id=tournee_id)
        nouveau_statut = request.POST.get('statut')
        source = request.POST.get('source', 'liste_tournees')  
        
        if nouveau_statut in ['PREVUE', 'EN_COURS', 'TERMINEE']:
            tournee.statut = nouveau_statut
            tournee.save()
            messages.success(request, f'✅ Statut de la tournée #{tournee.id} modifié avec succès !')
        else:
            messages.error(request, '❌ Statut invalide')
        
        # Rediriger vers la page d'origine
        if source == 'home':
            return redirect('home')
        else:
            return redirect('liste_tournees')
    
    return redirect('liste_tournees')

def detail_tournee(request, tournee_id):
    """
    Détails d'une tournée + liste des expéditions affectées
    """
    tournee = get_object_or_404(
        Tournee.objects.select_related('chauffeur', 'vehicule'),
        id=tournee_id
    )
    
    expeditions = tournee.expeditions.all().select_related(
        'client', 'destination', 'type_service'
    ).order_by('date_creation')
    
    stats_expeditions = {
        'total': expeditions.count(),
        'en_attente': expeditions.filter(statut='EN_ATTENTE').count(),
        'en_transit': expeditions.filter(statut='EN_TRANSIT').count(),
        'livrees': expeditions.filter(statut='LIVRE').count(),
    }
    
    return render(request, 'tournees/detail.html', {
        'tournee': tournee,
        'expeditions': expeditions,
        'stats_expeditions': stats_expeditions,
    })

def exporter_tournee_detail_pdf(request, tournee_id):
    """
    Exporte les détails d'une tournée en PDF
    """
    tournee = get_object_or_404(
        Tournee.objects.select_related('chauffeur', 'vehicule'),
        id=tournee_id
    )
    
    # Récupérer les expéditions
    expeditions = tournee.expeditions.all().select_related('client', 'destination', 'type_service')
    
    # ========== UNE SEULE SECTION AVEC TOUS LES CHAMPS ==========
    sections = [
        {
            'titre': 'Informations de la Tournée',
            'data': [
                ['ID Tournée', f"#{tournee.id}"],
                ['Chauffeur', f"{tournee.chauffeur.prenom} {tournee.chauffeur.nom} ({tournee.chauffeur.get_id_chauffeur()})"],
                ['Téléphone chauffeur', str(tournee.chauffeur.telephone)],
                ['Véhicule', f"{tournee.vehicule.marque} {tournee.vehicule.modele}"],
                ['Immatriculation', tournee.vehicule.numero_immatriculation],
                ['Date de départ', tournee.date_depart.strftime('%d/%m/%Y à %H:%M')],
                ['Date retour prévue', tournee.date_retour_prevue.strftime('%d/%m/%Y à %H:%M') if tournee.date_retour_prevue else 'Non définie'],
                ['Date retour réelle', tournee.date_retour_reelle.strftime('%d/%m/%Y à %H:%M') if tournee.date_retour_reelle else 'En cours'],
                ['Zone cible', tournee.get_zone_cible_display()],
                ['Statut', tournee.get_statut_display()],
                ['Tournée privée (EXPRESS)', 'Oui' if tournee.est_privee else 'Non'],
                ['Kilométrage départ', f"{tournee.kilometrage_depart} km" if tournee.kilometrage_depart else 'Non enregistré'],
                ['Kilométrage arrivée', f"{tournee.kilometrage_arrivee} km" if tournee.kilometrage_arrivee else 'Non enregistré'],
                ['Kilométrage parcouru', f"{tournee.kilometrage_parcouru} km" if tournee.kilometrage_parcouru else 'Non calculé'],
                ['Consommation carburant', f"{tournee.consommation_carburant:.2f} L" if tournee.consommation_carburant else 'Non calculée'],
                ['Date de création', tournee.date_creation.strftime('%d/%m/%Y %H:%M')],
                ['Remarques', tournee.remarques or 'Aucune remarque'],
            ]
        }
    ]
    
    # ========== Expéditions affectées ==========
    if expeditions.exists():
        exp_headers = ['N° Expédition', 'Client', 'Destination', 'Type', 'Poids', 'Statut']
        exp_data = [exp_headers]
        
        for exp in expeditions:
            exp_data.append([
                exp.get_numero_expedition(),
                f"{exp.client.prenom} {exp.client.nom}",
                f"{exp.destination.ville} - {exp.destination.wilaya}",
                exp.type_service.get_type_service_display(),
                f"{exp.poids} kg",
                exp.get_statut_display()
            ])
        
        sections.append({
            'titre': f'Expéditions affectées ({expeditions.count()})',
            'data': exp_data
        })
    
    # Générer le PDF
    return generer_pdf_fiche(
        titre_document=f"Fiche Tournée #{tournee.id}",
        sections=sections,
        nom_fichier_base=f"tournee_{tournee.id}",
        remarques=None  # Déjà dans la table
    )

def creer_tournee(request):
    """
    Création d'une tournée manuelle
    """
    if request.method == 'POST':
        form = TourneeForm(request.POST)
        
        if form.is_valid():
            try:
                # ✅ Pas de calcul de date_retour_prevue ici !
                # C'est déjà géré dans utils.py TourneeService.traiter_tournee()
                tournee = form.save()
                
                messages.success(request, f"Tournée #{tournee.id} créée avec succès !")
                return redirect('detail_tournee', tournee_id=tournee.id)
            
            except Exception as e:
                messages.error(request, f"Erreur lors de la création : {str(e)}")
    else:
        form = TourneeForm()
    
    return render(request, 'tournees/creer.html', {
        'form': form,
    })

def modifier_tournee(request, tournee_id):
    """
    Modification d'une tournée (PREVUE uniquement)
    """
    tournee = get_object_or_404(Tournee, id=tournee_id)
    
    if tournee.statut != 'PREVUE':
        messages.error(
            request, 
            f"Impossible de modifier : la tournée est {tournee.get_statut_display()}. "
            "Seules les tournées PRÉVUES peuvent être modifiées."
        )
        return redirect('detail_tournee', tournee_id=tournee_id)
    
    if request.method == 'POST':
        form = TourneeForm(request.POST, instance=tournee)
        
        if form.is_valid():
            try:
                # ✅ Pas de calcul ici non plus !
                tournee = form.save()
                
                messages.success(request, f"Tournée #{tournee.id} modifiée avec succès !")
                return redirect('detail_tournee', tournee_id=tournee.id)
            
            except Exception as e:
                messages.error(request, f"Erreur lors de la modification : {str(e)}")
    else:
        form = TourneeForm(instance=tournee)
    
    return render(request, 'tournees/modifier.html', {
        'form': form,
        'tournee': tournee,
    })

def supprimer_tournee(request, tournee_id):
    """
    Suppression d'une tournée (PREVUE uniquement)
    """
    tournee = get_object_or_404(Tournee, id=tournee_id)
    
    nb_expeditions = tournee.expeditions.count()
    
    if request.method == 'POST':
        try:
            tournee.delete()
            messages.success(request, f"Tournée #{tournee_id} supprimée avec succès")
            return redirect('liste_tournees')
        
        except Exception as e:
            messages.error(request, f"Erreur : {str(e)}")
            return redirect('detail_tournee', tournee_id=tournee_id)
    
    return render(request, 'tournees/supprimer.html', {
        'tournee': tournee,
        'nb_expeditions': nb_expeditions,
    })

def terminer_tournee(request, tournee_id):
    """
    Formulaire pour renseigner le kilométrage d'arrivée
    et finaliser une tournée terminée
    """
    tournee = get_object_or_404(Tournee, id=tournee_id)
    
    if tournee.statut != 'TERMINEE':
        messages.error(request, "⚠️ Cette tournée n'est pas terminée")
        return redirect('detail_tournee', tournee_id=tournee_id)
    
    if request.method == 'POST':
        try:
            kilometrage_arrivee = request.POST.get('kilometrage_arrivee')
            
            if not kilometrage_arrivee:
                messages.error(request, "⚠️ Le kilométrage d'arrivée est requis")
                return render(request, 'tournees/terminer.html', {'tournee': tournee})
            
            kilometrage_arrivee = int(kilometrage_arrivee)
            
            # Validation
            if kilometrage_arrivee < tournee.kilometrage_depart:
                messages.error(
                    request, 
                    f"❌ Le kilométrage d'arrivée ({kilometrage_arrivee} km) doit être supérieur "
                    f"au kilométrage de départ ({tournee.kilometrage_depart} km)"
                )
                return render(request, 'tournees/terminer.html', {'tournee': tournee})
            
            # ✅ METTRE À JOUR LA TOURNÉE
            from django.utils import timezone
            from .utils import TourneeService
            
            tournee.kilometrage_arrivee = kilometrage_arrivee
            tournee.date_retour_reelle = timezone.now()
            
            # Calculer kilométrage et consommation
            TourneeService.calculer_kilometrage_et_consommation(tournee)
            
            # Mettre à jour le kilométrage du véhicule
            tournee.vehicule.kilometrage = kilometrage_arrivee
            tournee.vehicule.statut = 'DISPONIBLE'
            tournee.vehicule.save()
            
            # Libérer le chauffeur
            tournee.chauffeur.statut_disponibilite = 'DISPONIBLE'
            tournee.chauffeur.save()
            
            # Marquer expéditions comme livrées
            for exp in tournee.expeditions.all():
                if exp.statut == 'EN_TRANSIT':
                    exp.statut = 'LIVRE'
                    exp.date_livraison_reelle = timezone.now().date()
                    exp.save(update_fields=['statut', 'date_livraison_reelle'])
            
            tournee.save()
            
            # Marquer toutes les notifications de cette tournée comme traitées
            from .models import Notification
            Notification.objects.filter(
                vehicule=tournee.vehicule,
                type_notification='TOURNEE_TERMINEE',
                statut__in=['NON_LUE', 'LUE']
            ).update(
                statut='TRAITEE',
                action_effectuee='KILOMETRAGE_RENSEIGNE',
                date_traitement=timezone.now()
            )
            
            messages.success(
                request, 
                f"✅ Tournée {tournee.get_numero_tournee()} finalisée ! "
                f"Kilométrage parcouru : {tournee.kilometrage_parcouru} km, "
                f"Consommation : {tournee.consommation_carburant:.2f} L"
            )
            
            return redirect('detail_tournee', tournee_id=tournee_id)
        
        except Exception as e:
            messages.error(request, f"❌ Erreur : {str(e)}")
    
    return render(request, 'tournees/terminer.html', {
        'tournee': tournee,
    })

def liste_expeditions(request):
    """
    Liste des expéditions avec recherche et filtres
    """
    expeditions = Expedition.objects.all().select_related(
        'client', 'destination', 'type_service', 'tournee'
    )
    
    # Recherche
    search = request.GET.get('search', '')
    if search:
        expeditions = expeditions.filter(
            Q(client__nom__icontains=search) |
            Q(client__prenom__icontains=search) |
            Q(destination__ville__icontains=search) |
            Q(destination__wilaya__icontains=search) |
            Q(nom_destinataire__icontains=search)
        )
    
    # Filtres
    statut_filter = request.GET.get('statut', '')
    if statut_filter:
        expeditions = expeditions.filter(statut=statut_filter)
    
    type_filter = request.GET.get('type', '')
    if type_filter:
        expeditions = expeditions.filter(type_service__type_service=type_filter)
    
    expeditions = expeditions.order_by('-date_creation')
    
    # Stats
    stats = {
        'total': Expedition.objects.count(),
        'en_attente': Expedition.objects.filter(statut='EN_ATTENTE').count(),
        'en_transit': Expedition.objects.filter(statut='EN_TRANSIT').count(),
        'livrees': Expedition.objects.filter(statut='LIVRE').count(),
    }
    
    statuts = [
        ('EN_ATTENTE', 'En attente'),
        ('EN_TRANSIT', 'En transit'),
        ('LIVRE', 'Livré'),
        ('ECHEC', 'Échec'),
    ]
    
    types = [
        ('STANDARD', 'Standard'),
        ('EXPRESS', 'Express'),
        ('INTERNATIONAL', 'International'),
    ]
    
    return render(request, 'expeditions/liste.html', {
        'expeditions': expeditions,
        'search': search,
        'statut_filter': statut_filter,
        'type_filter': type_filter,
        'stats': stats,
        'statuts': statuts,
        'types': types,
    })

def exporter_expeditions_pdf(request):
    """Export PDF liste expéditions"""
    expeditions = Expedition.objects.all().select_related(
        'client', 'destination', 'type_service'
    ).order_by('-date_creation')
    
    headers = ['N° Exp', 'Client', 'Destination', 'Type', 'Poids', 'Statut']
    data = [
        [
            e.get_numero_expedition(),
            f"{e.client.prenom} {e.client.nom}",
            f"{e.destination.ville} - {e.destination.wilaya}",
            e.type_service.get_type_service_display(),
            f"{e.poids} kg",
            e.get_statut_display()
        ]
        for e in expeditions
    ]
    
    return generer_pdf_liste("Liste des Expéditions", headers, data, "expeditions")

def detail_expedition(request, expedition_id):
    """
    Détails d'une expédition + table tracking détaillée dessous
    """
    expedition = get_object_or_404(
        Expedition.objects.select_related(
            'client', 'destination', 'type_service', 'tournee'
        ),
        id=expedition_id
    )
    
    # ✅ Récupérer TOUT l'historique de tracking pour affichage en table
    trackings = expedition.suivis.all().order_by('-date_heure')
    
    return render(request, 'expeditions/detail.html', {
        'expedition': expedition,
        'trackings': trackings,
    })

def exporter_expedition_detail_pdf(request, expedition_id):
    """Export PDF détail expédition avec tracking"""
    expedition = get_object_or_404(
        Expedition.objects.select_related('client', 'destination', 'type_service', 'tournee'),
        id=expedition_id
    )
    trackings = expedition.suivis.all().order_by('-date_heure')
    
    # Section principale
    sections = [
        {
            'titre': 'Informations de l\'Expédition',
            'data': [
                ['N° Expédition', expedition.get_numero_expedition()],
                ['Client', f"{expedition.client.prenom} {expedition.client.nom}"],
                ['Téléphone client', str(expedition.client.telephone)],
                ['Destination', f"{expedition.destination.ville} - {expedition.destination.wilaya}"],
                ['Pays', expedition.destination.pays],
                ['Type de service', expedition.type_service.get_type_service_display()],
                ['Destinataire', expedition.nom_destinataire],
                ['Téléphone destinataire', str(expedition.telephone_destinataire)],
                ['Email destinataire', expedition.email_destinataire],
                ['Adresse destinataire', expedition.adresse_destinataire],
                ['Poids', f"{expedition.poids} kg"],
                ['Volume', f"{expedition.volume} m³" if expedition.volume else 'Non spécifié'],
                ['Montant total', f"{expedition.montant_total:,.2f} DA"],
                ['Statut', expedition.get_statut_display()],
                ['Tournée', expedition.tournee.get_numero_tournee() if expedition.tournee else 'Aucune tournée affectée'],
                ['Date livraison prévue', expedition.date_livraison_prevue.strftime('%d/%m/%Y') if expedition.date_livraison_prevue else 'Non calculée'],
                ['Date livraison réelle', expedition.date_livraison_reelle.strftime('%d/%m/%Y') if expedition.date_livraison_reelle else '-'],
                ['Date création', expedition.date_creation.strftime('%d/%m/%Y %H:%M')],
                ['Description', expedition.description or 'Aucune description'],
                ['Remarques', expedition.remarques or 'Aucune remarque'],
            ]
        }
    ]
    
    # Historique tracking
    if trackings.exists():
        tracking_data = [['Date/Heure', 'Statut', 'Commentaire']]
        for t in trackings:
            tracking_data.append([
                t.date_heure.strftime('%d/%m/%Y %H:%M'),
                t.get_statut_etape_display(),
                t.commentaire or '-'
            ])
        
        sections.append({
            'titre': f'Historique de suivi ({trackings.count()} étapes)',
            'data': tracking_data
        })
    
    return generer_pdf_fiche(
        f"Fiche Expédition - {expedition.get_numero_expedition()}",
        sections,
        f"expedition_{expedition.id}",
        remarques=None  # Déjà dans la table
    )

def creer_expedition(request):
    if request.method == 'POST':
        form = ExpeditionForm(request.POST)
        
        if form.is_valid():
            try:
                # Sauvegarder l'expédition
                expedition = form.save()
                
                messages.success(
                    request, 
                    f"✅ Expédition {expedition.get_numero_expedition()} créée avec succès ! "
                )
                return redirect('detail_expedition', expedition_id=expedition.id)
            
            except Exception as e:
                messages.error(request, f"❌ Erreur : {str(e)}")
    else:
        form = ExpeditionForm()
    
    return render(request, 'expeditions/creer.html', {
        'form': form,
    })

def modifier_expedition(request, expedition_id):
    """
    Modification d'une expédition (EN_ATTENTE uniquement)
    """
    expedition = get_object_or_404(Expedition, id=expedition_id)
    
    # Validation : Seules les expéditions EN_ATTENTE peuvent être modifiées
    if expedition.statut not in ['EN_ATTENTE']:
        messages.error(
            request,
            f"Impossible de modifier : l'expédition est {expedition.get_statut_display()}. "
            "Seules les expéditions EN_ATTENTE peuvent être modifiées."
        )
        return redirect('detail_expedition', expedition_id=expedition_id)
    
    if request.method == 'POST':
        form = ExpeditionForm(request.POST, instance=expedition)
        
        if form.is_valid():
            try:
                expedition = form.save()
                messages.success(request, f"Expédition {expedition.get_numero_expedition()} modifiée avec succès !")
                return redirect('detail_expedition', expedition_id=expedition.id)
            
            except Exception as e:
                messages.error(request, f"Erreur : {str(e)}")
    else:
        form = ExpeditionForm(instance=expedition)
    
    return render(request, 'expeditions/modifier.html', {
        'form': form,
        'expedition': expedition,
    })

def supprimer_expedition(request, expedition_id):
    """
    Suppression d'une expédition
    La logique de validation est dans le signal pre_delete
    """
    expedition = get_object_or_404(Expedition, id=expedition_id)

    if request.method == 'POST':
        try:
            # ✅ Sauvegarder les infos AVANT suppression
            numero_expedition = expedition.get_numero_expedition()

            expedition.delete()

            messages.success(
                request,
                f"Expédition {numero_expedition} supprimée avec succès"
            )
            return redirect('liste_expeditions')

        except ValidationError as e:
            # ❌ Suppression refusée par le signal
            messages.error(request, str(e))
            return redirect('detail_expedition', expedition_id=expedition_id)

        except Exception as e:
            messages.error(request, f"Erreur : {str(e)}")
            return redirect('liste_expeditions')

    return render(request, 'expeditions/supprimer.html', {
        'expedition': expedition,
    })

def liste_trackings(request):
    """
    Vue globale : Liste de TOUTES les expéditions avec :
    - Expédition
    - Tournée affectée
    - Statut de la tournée
    - Dernier statut de l'expédition
    - Date/heure du dernier statut
    
    Clic sur une ligne → Redirige vers detail_expedition (qui a table tracking dessous)
    """
    # Récupérer toutes les expéditions avec leurs relations
    expeditions = Expedition.objects.all().select_related(
        'client',
        'destination',
        'tournee',
        'tournee__chauffeur',
        'tournee__vehicule'
    ).prefetch_related(
        # Précharger seulement le dernier tracking de chaque expédition
        Prefetch(
            'suivis',
            queryset=TrackingExpedition.objects.order_by('-date_heure')[:1],
            to_attr='dernier_tracking_list'
        )
    ).order_by('-date_creation')
    
    # Construire les données pour le template
    expeditions_data = []
    for exp in expeditions:
        # Récupérer le dernier tracking (premier élément de la liste préchargée)
        dernier_tracking = exp.dernier_tracking_list[0] if exp.dernier_tracking_list else None
        
        expeditions_data.append({
            'expedition': exp,
            'tournee': exp.tournee,
            'statut_tournee': exp.tournee.get_statut_display() if exp.tournee else '-',
            'dernier_tracking': dernier_tracking,
        })
    
    return render(request, 'trackings/liste.html', {
        'expeditions_data': expeditions_data,
    })

def detail_tracking(request, expedition_id):
    """
    Redirige vers la page de détails de l'expédition
    (qui contient la table tracking détaillée en dessous)
    """
    return redirect('detail_expedition', expedition_id=expedition_id)

def liste_factures(request):
    """
    Affiche la liste de toutes les factures
    
    FONCTIONNALITÉS :
    - Recherche par nom du client (nom ou prénom)
    - Filtre par statut (IMPAYEE, PAYEE, etc.)
    - Statistiques globales
    """
    factures = Facture.objects.all().select_related('client')
    
    # ========== RECHERCHE PAR NOM CLIENT ==========
    search = request.GET.get('search', '')
    if search:
        factures = factures.filter(
            Q(client__nom__icontains=search) |       # Recherche dans le nom
            Q(client__prenom__icontains=search) |    # Recherche dans le prénom
            Q(numero_facture__icontains=search)      # Recherche dans le numéro
        )
    
    # ========== FILTRE PAR STATUT ==========
    statut_filter = request.GET.get('statut', '')
    if statut_filter:
        factures = factures.filter(statut=statut_filter)
    
    # Trier par date de création (plus récentes en premier)
    factures = factures.order_by('-date_creation')
    
    # ========== STATISTIQUES GLOBALES ==========
    stats = {
        'total': Facture.objects.count(),
        'impayees': Facture.objects.filter(statut='IMPAYEE').count(),
        'partiellement_payees': Facture.objects.filter(statut='PARTIELLEMENT_PAYEE').count(),
        'payees': Facture.objects.filter(statut='PAYEE').count(),
        'en_retard': Facture.objects.filter(statut='EN_RETARD').count(),
        'montant_total': Facture.objects.aggregate(Sum('montant_ttc'))['montant_ttc__sum'] or 0,
    }
    
    # Choix pour le filtre statut
    statuts = [
        ('IMPAYEE', 'Impayée'),
        ('PARTIELLEMENT_PAYEE', 'Partiellement payée'),
        ('PAYEE', 'Payée'),
        ('EN_RETARD', 'En retard'),
    ]
    
    return render(request, 'factures/liste.html', {
        'factures': factures,
        'search': search,
        'statut_filter': statut_filter,
        'stats': stats,
        'statuts': statuts,
    })

def exporter_factures_pdf(request):
    """
    Génère un PDF avec la liste de toutes les factures
    Format : Tableau avec colonnes [N° Facture, Client, Montant, Statut, Échéance]
    """
    factures = Facture.objects.all().select_related('client').order_by('-date_creation')
    
    # En-têtes du tableau
    headers = ['N° Facture', 'Client', 'Montant TTC', 'Statut', 'Échéance']
    
    # Données (chaque ligne = une facture)
    data = [
        [
            f.numero_facture,
            f"{f.client.prenom} {f.client.nom}",
            f"{f.montant_ttc:,.2f} DA",
            f.get_statut_display(),
            f.date_echeance.strftime('%d/%m/%Y')
        ]
        for f in factures
    ]
    
    return generer_pdf_liste("Liste des Factures", headers, data, "factures")

def detail_facture(request, facture_id):
    """
    Affiche les détails d'une facture
    
    AFFICHE :
    - Informations de la facture
    - Liste des paiements effectués pour cette facture
    - Liste des expéditions facturées
    - Bouton "Ajouter paiement" (si facture pas PAYEE/ANNULEE)
    """
    from .utils import FacturationService
    facture = get_object_or_404(
        Facture.objects.select_related('client'),
        id=facture_id
    )
    
    # ========== RÉCUPÉRER LES PAIEMENTS ==========
    paiements = facture.paiements.all().order_by('-date_paiement')
    
    # ========== RÉCUPÉRER LES EXPÉDITIONS ==========
    # Les expéditions de cette facture (relation ManyToMany)
    expeditions = facture.expeditions.all().select_related(
        'destination', 'type_service', 'tournee'
    )
    
    # ========== STATISTIQUES PAIEMENTS ==========
    stats_paiements = {
        'total_paye': paiements.aggregate(Sum('montant_paye'))['montant_paye__sum'] or 0,
        'nb_paiements': paiements.count(),
    }
    
    # ========== PEUT-ON AJOUTER UN PAIEMENT ? ==========
    # On ne peut pas payer une facture PAYEE ou ANNULEE
    peut_ajouter_paiement = facture.statut not in ['PAYEE', 'ANNULEE']

    montant_restant = FacturationService.calculer_montant_restant(facture)
    
    return render(request, 'factures/detail.html', {
        'facture': facture,
        'paiements': paiements,
        'expeditions': expeditions,
        'stats_paiements': stats_paiements,
        'peut_ajouter_paiement': peut_ajouter_paiement,  # Pour afficher ou cacher le bouton
    })

def exporter_facture_detail_pdf(request, facture_id):
    """
    Génère un PDF détaillé d'une facture
    
    CONTENU :
    - Section 1 : Informations facture
    - Section 2 : Expéditions facturées (si existent)
    - Section 3 : Paiements effectués (si existent)
    """
    facture = get_object_or_404(Facture.objects.select_related('client'), id=facture_id)
    paiements = facture.paiements.all().order_by('-date_paiement')
    expeditions = facture.expeditions.all().select_related('destination', 'type_service')
    
    # ========== SECTION 1 : INFORMATIONS FACTURE ==========
    sections = [
        {
            'titre': 'Informations de la Facture',
            'data': [
                ['N° Facture', facture.numero_facture],
                ['Client', f"{facture.client.prenom} {facture.client.nom}"],
                ['Téléphone', str(facture.client.telephone)],
                ['Montant HT', f"{facture.montant_ht:,.2f} DA"],
                ['TVA', f"{facture.montant_tva:,.2f} DA"],
                ['Montant TTC', f"{facture.montant_ttc:,.2f} DA"],
                ['Statut', facture.get_statut_display()],
                ['Date création', facture.date_creation.strftime('%d/%m/%Y')],
                ['Date échéance', facture.date_echeance.strftime('%d/%m/%Y')],
                ['Remarques', facture.remarques or 'Aucune'],
            ]
        }
    ]
    
    # ========== SECTION 2 : EXPÉDITIONS FACTURÉES ==========
    if expeditions.exists():
        exp_data = [['N° Exp', 'Destination', 'Type', 'Poids', 'Montant']]
        for e in expeditions:
            exp_data.append([
                e.get_numero_expedition(),
                f"{e.destination.ville} - {e.destination.wilaya}",
                e.type_service.get_type_service_display(),
                f"{e.poids} kg",
                f"{e.montant_total:,.2f} DA"
            ])
        
        sections.append({
            'titre': f'Expéditions facturées ({expeditions.count()})',
            'data': exp_data
        })
    
    # ========== SECTION 3 : PAIEMENTS ==========
    if paiements.exists():
        paie_data = [['Date', 'Montant', 'Mode', 'Référence']]
        for p in paiements:
            paie_data.append([
                p.date_paiement.strftime('%d/%m/%Y'),
                f"{p.montant_paye:,.2f} DA",
                p.get_mode_paiement_display(),
                p.reference_transaction or '-'
            ])
        
        sections.append({
            'titre': f'Paiements ({paiements.count()})',
            'data': paie_data
        })
    
    # Générer le PDF
    return generer_pdf_fiche(
        f"Facture - {facture.numero_facture}",
        sections,
        f"facture_{facture.id}",
        remarques=None
    )

def modifier_facture(request, facture_id):
    """
    Permet de modifier une facture
    Modifiable : client, date échéance, statut, remarques
    """
    facture = get_object_or_404(Facture, id=facture_id)
    
    if request.method == 'POST':
        form = FactureForm(request.POST, instance=facture)
        
        if form.is_valid():
            try:
                facture = form.save()
                messages.success(request, f"Facture {facture.numero_facture} modifiée !")
                return redirect('detail_facture', facture_id=facture.id)
            except Exception as e:
                messages.error(request, f"Erreur : {str(e)}")
    else:
        form = FactureForm(instance=facture)
    
    return render(request, 'factures/modifier.html', {
        'form': form,
        'facture': facture,
    })

def supprimer_facture(request, facture_id):
    """
    Supprime une facture
    ATTENTION : Les paiements associés seront aussi supprimés (cascade)
    """
    facture = get_object_or_404(Facture, id=facture_id)
    
    # Compter combien de paiements vont être supprimés
    nb_paiements = facture.paiements.count()
    
    if request.method == 'POST':
        try:
            facture.delete()
            messages.success(request, f"Facture {facture.numero_facture} supprimée")
            return redirect('liste_factures')
        except Exception as e:
            messages.error(request, f"Erreur : {str(e)}")
            return redirect('detail_facture', facture_id=facture_id)
    
    return render(request, 'factures/supprimer.html', {
        'facture': facture,
        'nb_paiements': nb_paiements,
    })

def liste_paiements(request):
    """
    Affiche la liste de tous les paiements
    
    FONCTIONNALITÉS :
    - Recherche par nom client ou référence transaction
    - Filtre par mode de paiement
    - Statistiques globales
    """
    paiements = Paiement.objects.all().select_related('facture', 'facture__client')
    
    # ========== RECHERCHE ==========
    search = request.GET.get('search', '')
    if search:
        paiements = paiements.filter(
            Q(facture__client__nom__icontains=search) |
            Q(facture__client__prenom__icontains=search) |
            Q(reference_transaction__icontains=search)
        )
    
    # ========== FILTRE PAR MODE ==========
    mode_filter = request.GET.get('mode', '')
    if mode_filter:
        paiements = paiements.filter(mode_paiement=mode_filter)
    
    paiements = paiements.order_by('-date_paiement')
    
    # ========== STATISTIQUES ==========
    stats = {
        'total': paiements.count(),
        'montant_total': paiements.aggregate(Sum('montant_paye'))['montant_paye__sum'] or 0,
        'especes': paiements.filter(mode_paiement='ESPECES').count(),
        'cheque': paiements.filter(mode_paiement='CHEQUE').count(),
        'virement': paiements.filter(mode_paiement='VIREMENT').count(),
        'carte': paiements.filter(mode_paiement='CARTE').count(),
    }
    
    modes = [
        ('ESPECES', 'Espèces'),
        ('CHEQUE', 'Chèque'),
        ('VIREMENT', 'Virement'),
        ('CARTE', 'Carte bancaire'),
    ]
    
    return render(request, 'paiements/liste.html', {
        'paiements': paiements,
        'search': search,
        'mode_filter': mode_filter,
        'stats': stats,
        'modes': modes,
    })

def exporter_paiements_pdf(request):
    """
    Génère un PDF avec la liste de tous les paiements
    Format : Tableau avec colonnes [Date, Facture, Client, Montant, Mode]
    """
    paiements = Paiement.objects.all().select_related(
        'facture', 'facture__client'
    ).order_by('-date_paiement')
    
    headers = ['Date', 'Facture', 'Client', 'Montant', 'Mode']
    data = [
        [
            p.date_paiement.strftime('%d/%m/%Y'),
            p.facture.numero_facture,
            f"{p.facture.client.prenom} {p.facture.client.nom}",
            f"{p.montant_paye:,.2f} DA",
            p.get_mode_paiement_display()
        ]
        for p in paiements
    ]
    
    return generer_pdf_liste("Liste des Paiements", headers, data, "paiements")

def detail_paiement(request, paiement_id):
    """
    Affiche les détails d'un paiement
    Inclut les informations de la facture associée
    """
    paiement = get_object_or_404(
        Paiement.objects.select_related('facture', 'facture__client'),
        id=paiement_id
    )
    
    return render(request, 'paiements/detail.html', {
        'paiement': paiement,
    })

def exporter_paiement_detail_pdf(request, paiement_id):
    """
    Génère un PDF détaillé d'un paiement
    
    CONTENU :
    - Section 1 : Informations du paiement
    - Section 2 : Informations de la facture associée
    """
    paiement = get_object_or_404(
        Paiement.objects.select_related('facture', 'facture__client'),
        id=paiement_id
    )
    
    sections = [
        {
            'titre': 'Informations du Paiement',
            'data': [
                ['Facture', paiement.facture.numero_facture],
                ['Client', f"{paiement.facture.client.prenom} {paiement.facture.client.nom}"],
                ['Montant payé', f"{paiement.montant_paye:,.2f} DA"],
                ['Mode', paiement.get_mode_paiement_display()],
                ['Date', paiement.date_paiement.strftime('%d/%m/%Y')],
                ['Référence', paiement.reference_transaction or 'Non renseignée'],
                ['Remarques', paiement.remarques or 'Aucune'],
            ]
        },
        {
            'titre': 'Facture Associée',
            'data': [
                ['N° Facture', paiement.facture.numero_facture],
                ['Montant TTC', f"{paiement.facture.montant_ttc:,.2f} DA"],
                ['Statut', paiement.facture.get_statut_display()],
                ['Échéance', paiement.facture.date_echeance.strftime('%d/%m/%Y')],
            ]
        }
    ]
    
    return generer_pdf_fiche(
        f"Paiement - {paiement.facture.numero_facture}",
        sections,
        f"paiement_{paiement.id}",
        remarques=None
    )

def creer_paiement(request, facture_id=None):
    """
    Enregistre un nouveau paiement
    
    2 MODES D'UTILISATION :
    
    1. DEPUIS UNE FACTURE (facture_id fourni) :
       - L'agent clique "Ajouter paiement" depuis le détail d'une facture
       - Le formulaire est SIMPLIFIÉ : facture et client cachés (pré-remplis)
       - Après validation, retour vers le détail de la facture
    
    2. MODE NORMAL (facture_id = None) :
       - L'agent accède directement à "Créer un paiement"
       - Le formulaire est COMPLET : il choisit la facture dans une liste
       - Seules les factures IMPAYEE/PARTIELLEMENT_PAYEE sont proposées
       - Après validation, retour vers le détail du paiement
    """
    # Déterminer si on vient d'une facture
    depuis_facture = facture_id is not None
    facture = None
    
    # ========== SI DEPUIS UNE FACTURE ==========
    if depuis_facture:
        facture = get_object_or_404(Facture, id=facture_id)
        
        # Vérifier qu'on peut encore payer cette facture
        if facture.statut in ['PAYEE', 'ANNULEE']:
            messages.error(request, f"Impossible : facture {facture.get_statut_display()}")
            return redirect('detail_facture', facture_id=facture_id)
    
    # ========== TRAITEMENT DU FORMULAIRE ==========
    if request.method == 'POST':
        # Passer les options spéciales au formulaire
        form = PaiementForm(
            request.POST,
            depuis_facture=depuis_facture,  # Pour cacher les champs
            facture_id=facture_id           # Pour pré-remplir
        )
        
        if form.is_valid():
            try:
                paiement = form.save()
                messages.success(request, f"Paiement de {paiement.montant_paye:,.2f} DA enregistré !")
                
                # ========== REDIRECTION SELON ORIGINE ==========
                if depuis_facture:
                    # Retour vers la facture
                    return redirect('detail_facture', facture_id=facture_id)
                else:
                    # Retour vers le détail du paiement
                    return redirect('detail_paiement', paiement_id=paiement.id)
            except Exception as e:
                messages.error(request, f"Erreur : {str(e)}")
    else:
        # Affichage du formulaire vide
        form = PaiementForm(
            depuis_facture=depuis_facture,
            facture_id=facture_id
        )
    
    return render(request, 'paiements/creer.html', {
        'form': form,
        'depuis_facture': depuis_facture,  # Pour adapter l'affichage du template
        'facture': facture,                # Pour afficher les infos de la facture si depuis facture
    })

def supprimer_paiement(request, paiement_id):
    """
    Supprime un paiement
    
    ACTIONS AUTOMATIQUES (via signal pre_delete) :
    - Restauration du solde client
    - Mise à jour du statut de la facture
    """
    paiement = get_object_or_404(Paiement, id=paiement_id)
    
    if request.method == 'POST':
        try:
            facture = paiement.facture  # Garder référence avant suppression
            paiement.delete()           # Le signal va gérer la logique métier
            
            messages.success(request, f"Paiement de {paiement.montant_paye:,.2f} DA supprimé")
            return redirect('detail_facture', facture_id=facture.id)
        except Exception as e:
            messages.error(request, f"Erreur : {str(e)}")
            return redirect('detail_paiement', paiement_id=paiement_id)
    
    return render(request, 'paiements/supprimer.html', {
        'paiement': paiement,
    })

def liste_incidents(request):
    """
    Liste avec recherche et filtres
    """
    incidents = Incident.objects.all().select_related('expedition', 'tournee')
    
    # ========== RECHERCHE ==========
    search = request.GET.get('search', '')
    if search:
        incidents = incidents.filter(
            Q(numero_incident__icontains=search) |
            Q(titre__icontains=search) |
            Q(description__icontains=search) |
            Q(signale_par__icontains=search) |
            Q(lieu_incident__icontains=search)
        )
    
    # ========== FILTRES ==========
    type_incident = request.GET.get('type_incident', '')
    if type_incident:
        incidents = incidents.filter(type_incident=type_incident)
    
    severite = request.GET.get('severite', '')
    if severite:
        incidents = incidents.filter(severite=severite)
    
    statut = request.GET.get('statut', '')
    if statut:
        incidents = incidents.filter(statut=statut)
    
    incidents = incidents.order_by('-date_heure_incident')
    
    # ========== STATISTIQUES ==========
    stats = {
        'total': incidents.count(),
        'signales': Incident.objects.filter(statut='SIGNALE').count(),
        'en_cours': Incident.objects.filter(statut='EN_COURS').count(),
        'resolus': Incident.objects.filter(statut='RESOLU').count(),
        'clos': Incident.objects.filter(statut='CLOS').count(),
        'critiques': Incident.objects.filter(severite='CRITIQUE').count(),
        'eleves': Incident.objects.filter(severite='ELEVEE').count(),
    }
    
    # ========== CHOIX POUR FILTRES ==========
    types = Incident._meta.get_field('type_incident').choices
    severites = Incident._meta.get_field('severite').choices
    statuts = Incident._meta.get_field('statut').choices
    
    return render(request, 'incidents/liste.html', {
        'incidents': incidents,
        'search': search,
        'type_incident': type_incident,
        'severite': severite,
        'statut': statut,
        'types': types,
        'severites': severites,
        'statuts': statuts,
        'stats': stats,
    })

def detail_incident(request, incident_id):
    """
    Affiche tous les détails + historique
    """
    incident = get_object_or_404(
        Incident.objects.select_related('expedition', 'tournee'),
        id=incident_id
    )
    
    # Historique
    historique = incident.historique.all().order_by('-date_action')
    
    return render(request, 'incidents/detail.html', {
        'incident': incident,
        'historique': historique,
    })

def creer_incident(request):
    """
    Formulaire de création avec gestion emails automatiques
    """
    if request.method == 'POST':
        form = IncidentForm(request.POST, request.FILES)
        
        if form.is_valid():
            try:
                # Sauvegarder l'incident
                incident = form.save()
                
                # ✅ Le traitement automatique se fait dans le save() du modèle
                # qui appelle IncidentService.traiter_nouvel_incident()
                # → Emails envoyés automatiquement !
                
                messages.success(
                    request,
                    f"✅ Incident {incident.numero_incident} créé avec succès ! "
                    f"Alertes envoyées par email."
                )
                return redirect('detail_incident', incident_id=incident.id)
                
            except Exception as e:
                messages.error(request, f"❌ Erreur : {str(e)}")
    else:
        form = IncidentForm()
    
    return render(request, 'incidents/creer.html', {
        'form': form,
    })

def modifier_incident(request, incident_id):
    """
    Modification d'un incident existant
    """
    incident = get_object_or_404(Incident, id=incident_id)
    
    if request.method == 'POST':
        form = IncidentModificationForm(request.POST, request.FILES, instance=incident)
        
        if form.is_valid():
            try:
                incident = form.save()
                messages.success(request, f"✅ Incident {incident.numero_incident} modifié !")
                return redirect('detail_incident', incident_id=incident.id)
            except Exception as e:
                messages.error(request, f"❌ Erreur : {str(e)}")
    else:
        form = IncidentModificationForm(instance=incident)
    
    return render(request, 'incidents/modifier.html', {
        'form': form,
        'incident': incident,
    })

def assigner_incident(request, incident_id):
    """
    Assigner un agent à un incident
    """
    incident = get_object_or_404(Incident, id=incident_id)
    
    if request.method == 'POST':
        form = AssignationForm(request.POST)
        
        if form.is_valid():
            try:
                agent_nom = form.cleaned_data['agent_nom']
                
                # Utiliser le service
                IncidentService.assigner_agent_incident(incident, agent_nom)
                
                messages.success(request, f"✅ Incident assigné à {agent_nom}")
                return redirect('detail_incident', incident_id=incident.id)
                
            except Exception as e:
                messages.error(request, f"❌ Erreur : {str(e)}")
    else:
        form = AssignationForm()
    
    return render(request, 'incidents/assigner.html', {
        'form': form,
        'incident': incident,
    })

def resoudre_incident(request, incident_id):
    """
    Marquer un incident comme résolu
    """
    incident = get_object_or_404(Incident, id=incident_id)
    
    if request.method == 'POST':
        form = IncidentResolutionForm(request.POST)
        
        if form.is_valid():
            try:
                solution = form.cleaned_data['solution']
                agent = form.cleaned_data['agent']
                
                # Utiliser le service
                IncidentService.resoudre_incident(incident, solution, agent)
                
                messages.success(request, f"✅ Incident {incident.numero_incident} résolu !")
                return redirect('detail_incident', incident_id=incident.id)
                
            except Exception as e:
                messages.error(request, f"❌ Erreur : {str(e)}")
    else:
        form = IncidentResolutionForm()
    
    return render(request, 'incidents/resoudre.html', {
        'form': form,
        'incident': incident,
    })

def cloturer_incident(request, incident_id):
    """
    Clôture définitive d'un incident (doit être RESOLU avant)
    """
    incident = get_object_or_404(Incident, id=incident_id)
    
    if request.method == 'POST':
        try:
            IncidentService.cloturer_incident(incident)
            messages.success(request, f"✅ Incident {incident.numero_incident} clôturé !")
            return redirect('liste_incidents')
            
        except ValidationError as e:
            messages.error(request, str(e))
            return redirect('detail_incident', incident_id=incident.id)
    
    return render(request, 'incidents/cloturer.html', {
        'incident': incident,
    })

def supprimer_incident(request, incident_id):
    """
    Suppression d'un incident (avec confirmation)
    """
    incident = get_object_or_404(Incident, id=incident_id)
    
    if request.method == 'POST':
        try:
            numero = incident.numero_incident
            incident.delete()
            messages.success(request, f"✅ Incident {numero} supprimé !")
            return redirect('liste_incidents')
            
        except Exception as e:
            messages.error(request, f"❌ Erreur : {str(e)}")
            return redirect('detail_incident', incident_id=incident_id)
    
    return render(request, 'incidents/supprimer.html', {
        'incident': incident,
    })

def exporter_incidents_pdf(request):
    """
    Génère un PDF avec la liste de tous les incidents
    """
    incidents = Incident.objects.all().select_related(
        'expedition', 'tournee'
    ).order_by('-date_heure_incident')
    
    headers = ['N° Incident', 'Type', 'Sévérité', 'Statut', 'Date', 'Signalé par']
    
    data = [
        [
            i.numero_incident,
            i.get_type_incident_display(),
            i.get_severite_display(),
            i.get_statut_display(),
            i.date_heure_incident.strftime('%d/%m/%Y'),
            i.signale_par
        ]
        for i in incidents
    ]
    
    return generer_pdf_liste("Liste des Incidents", headers, data, "incidents")

def exporter_incident_detail_pdf(request, incident_id):
    """
    Génère un PDF détaillé d'un incident
    """
    incident = Incident.objects.select_related(
        'expedition', 'tournee'
    ).get(id=incident_id)
    
    sections = [
        {
            'titre': 'Informations de l\'Incident',
            'data': [
                ['N° Incident', incident.numero_incident],
                ['Type', incident.get_type_incident_display()],
                ['Titre', incident.titre],
                ['Description', incident.description],
                ['Sévérité', incident.get_severite_display()],
                ['Statut', incident.get_statut_display()],
                ['Date/Heure', incident.date_heure_incident.strftime('%d/%m/%Y %H:%M')],
                ['Lieu', incident.lieu_incident or 'Non spécifié'],
                ['Signalé par', incident.signale_par],
                ['Coût estimé', f"{incident.cout_estime:,.2f} DA" if incident.cout_estime else '0 DA'],
            ]
        }
    ]
    
    # ========== EXPÉDITION CONCERNÉE ==========
    if incident.expedition:
        exp_data = [
            ['N° Expédition', incident.expedition.get_numero_expedition()],
            ['Client', f"{incident.expedition.client.prenom} {incident.expedition.client.nom}"],
            ['Destination', f"{incident.expedition.destination.ville}, {incident.expedition.destination.wilaya}"],
            ['Statut', incident.expedition.get_statut_display()],
        ]
        sections.append({
            'titre': 'Expédition concernée',
            'data': exp_data
        })
    
    # ========== TOURNÉE CONCERNÉE ==========
    if incident.tournee:
        tournee_data = [
            ['N° Tournée', incident.tournee.get_numero_tournee()],
            ['Chauffeur', f"{incident.tournee.chauffeur.prenom} {incident.tournee.chauffeur.nom}"],
            ['Véhicule', incident.tournee.vehicule.numero_immatriculation],
            ['Zone', incident.tournee.get_zone_cible_display()],
            ['Statut', incident.tournee.get_statut_display()],
        ]
        sections.append({
            'titre': 'Tournée concernée',
            'data': tournee_data
        })
    
    # ========== REMBOURSEMENT ==========
    if incident.remboursement_effectue:
        rbt_data = [
            ['Remboursement effectué', 'OUI'],
            ['Montant remboursé', f"{incident.montant_rembourse:,.2f} DA"],
            ['Taux appliqué', f"{incident.taux_remboursement}%"],
        ]
        sections.append({
            'titre': 'Remboursement',
            'data': rbt_data
        })
    
    # ========== TRAITEMENT ==========
    if incident.agent_responsable:
        traitement_data = [
            ['Agent responsable', incident.agent_responsable],
            ['Actions entreprises', incident.actions_entreprises or 'Aucune'],
            ['Date résolution', incident.date_resolution.strftime('%d/%m/%Y') if incident.date_resolution else 'Non résolu'],
        ]
        sections.append({
            'titre': 'Traitement',
            'data': traitement_data
        })
    
    return generer_pdf_fiche(
        f"Incident - {incident.numero_incident}",
        sections,
        f"incident_{incident.id}",
        remarques=incident.remarques
    )

def liste_reclamations(request):
    """
    Liste avec recherche et filtres
    """
    reclamations = Reclamation.objects.all().select_related('client', 'facture')
    
    # ========== RECHERCHE ==========
    search = request.GET.get('search', '')
    if search:
        reclamations = reclamations.filter(
            Q(numero_reclamation__icontains=search) |
            Q(objet__icontains=search) |
            Q(description__icontains=search) |
            Q(client__nom__icontains=search) |
            Q(client__prenom__icontains=search)
        )
    
    # ========== FILTRES ==========
    type_reclamation = request.GET.get('type_reclamation', '')
    if type_reclamation:
        reclamations = reclamations.filter(type_reclamation=type_reclamation)
    
    nature = request.GET.get('nature', '')
    if nature:
        reclamations = reclamations.filter(nature=nature)
    
    priorite = request.GET.get('priorite', '')
    if priorite:
        reclamations = reclamations.filter(priorite=priorite)
    
    statut = request.GET.get('statut', '')
    if statut:
        reclamations = reclamations.filter(statut=statut)
    
    client_id = request.GET.get('client_id', '')
    if client_id:
        reclamations = reclamations.filter(client_id=client_id)
    
    reclamations = reclamations.order_by('-date_creation')
    
    # ========== STATISTIQUES ==========
    stats = {
        'total': reclamations.count(),
        'ouvertes': Reclamation.objects.filter(statut='OUVERTE').count(),
        'en_cours': Reclamation.objects.filter(statut='EN_COURS').count(),
        'resolues': Reclamation.objects.filter(statut='RESOLUE').count(),
        'closes': Reclamation.objects.filter(statut='CLOSE').count(),
        'urgentes': Reclamation.objects.filter(priorite='URGENTE').count(),
        'avec_compensation': Reclamation.objects.filter(compensation_accordee=True).count(),
    }
    
    # ========== CHOIX POUR FILTRES ==========
    types = Reclamation._meta.get_field('type_reclamation').choices
    natures = Reclamation._meta.get_field('nature').choices
    priorites = Reclamation._meta.get_field('priorite').choices
    statuts = Reclamation._meta.get_field('statut').choices
    clients = Client.objects.all().order_by('nom', 'prenom')
    
    return render(request, 'reclamations/liste.html', {
        'reclamations': reclamations,
        'search': search,
        'type_reclamation': type_reclamation,
        'nature': nature,
        'priorite': priorite,
        'statut': statut,
        'client_id': client_id,
        'types': types,
        'natures': natures,
        'priorites': priorites,
        'statuts': statuts,
        'clients': clients,
        'stats': stats,
    })

def detail_reclamation(request, reclamation_id):
    """
    Affiche tous les détails + historique
    """
    reclamation = get_object_or_404(
        Reclamation.objects.select_related('client', 'facture').prefetch_related('expeditions'),
        id=reclamation_id
    )
    
    # Historique
    historique = reclamation.historique.all().order_by('-date_action')
    
    return render(request, 'reclamations/detail.html', {
        'reclamation': reclamation,
        'historique': historique,
    })

def creer_reclamation(request):
    """
    Formulaire de création avec email automatique
    """
    if request.method == 'POST':
        form = ReclamationForm(request.POST, request.FILES)
        
        if form.is_valid():
            try:
                # Sauvegarder la réclamation
                reclamation = form.save()
                
                # ✅ Le traitement automatique se fait dans le save() du modèle
                # qui appelle ReclamationService.traiter_nouvelle_reclamation()
                # → Email envoyé au support automatiquement !
                
                messages.success(
                    request,
                    f"✅ Réclamation {reclamation.numero_reclamation} créée avec succès ! "
                    f"Email envoyé au support."
                )
                return redirect('detail_reclamation', reclamation_id=reclamation.id)
                
            except Exception as e:
                messages.error(request, f"❌ Erreur : {str(e)}")
    else:
        form = ReclamationForm()
    
    return render(request, 'reclamations/creer.html', {
        'form': form,
    })

def modifier_reclamation(request, reclamation_id):
    """
    Modification d'une réclamation existante
    """
    reclamation = get_object_or_404(Reclamation, id=reclamation_id)
    
    if request.method == 'POST':
        form = ReclamationModificationForm(request.POST, instance=reclamation)
        
        if form.is_valid():
            try:
                reclamation = form.save()
                messages.success(request, f"✅ Réclamation {reclamation.numero_reclamation} modifiée !")
                return redirect('detail_reclamation', reclamation_id=reclamation.id)
            except Exception as e:
                messages.error(request, f"❌ Erreur : {str(e)}")
    else:
        form = ReclamationModificationForm(instance=reclamation)
    
    return render(request, 'reclamations/modifier.html', {
        'form': form,
        'reclamation': reclamation,
    })

def assigner_reclamation(request, reclamation_id):
    """
    Assigner un agent à une réclamation
    """
    reclamation = get_object_or_404(Reclamation, id=reclamation_id)
    
    if request.method == 'POST':
        form = AssignationForm(request.POST)
        
        if form.is_valid():
            try:
                agent_nom = form.cleaned_data['agent_nom']
                
                # Utiliser le service
                ReclamationService.assigner_agent(reclamation, agent_nom)
                
                messages.success(request, f"✅ Réclamation assignée à {agent_nom}")
                return redirect('detail_reclamation', reclamation_id=reclamation.id)
                
            except Exception as e:
                messages.error(request, f"❌ Erreur : {str(e)}")
    else:
        form = AssignationForm()
    
    return render(request, 'reclamations/assigner.html', {
        'form': form,
        'reclamation': reclamation,
    })

def repondre_reclamation(request, reclamation_id):
    """
    Enregistrer une réponse à la réclamation
    """
    reclamation = get_object_or_404(Reclamation, id=reclamation_id)
    
    if request.method == 'POST':
        form = ReclamationReponseForm(request.POST)
        
        if form.is_valid():
            try:
                reponse = form.cleaned_data['reponse']
                solution = form.cleaned_data['solution']
                agent = form.cleaned_data['agent']
                
                # Utiliser le service
                ReclamationService.repondre_reclamation(reclamation, reponse, solution, agent)
                
                # ✅ Email envoyé automatiquement au client !
                
                messages.success(
                    request,
                    f"✅ Réponse enregistrée ! Email envoyé au client."
                )
                return redirect('detail_reclamation', reclamation_id=reclamation.id)
                
            except Exception as e:
                messages.error(request, f"❌ Erreur : {str(e)}")
    else:
        form = ReclamationReponseForm()
    
    return render(request, 'reclamations/repondre.html', {
        'form': form,
        'reclamation': reclamation,
    })

def resoudre_reclamation(request, reclamation_id):
    """
    Marquer une réclamation comme résolue avec compensation éventuelle
    """
    reclamation = get_object_or_404(Reclamation, id=reclamation_id)
    
    if request.method == 'POST':
        form = ReclamationResolutionForm(request.POST)
        
        if form.is_valid():
            try:
                agent = form.cleaned_data['agent']
                accorder_compensation = form.cleaned_data['accorder_compensation']
                montant_compensation = form.cleaned_data['montant_compensation'] or 0
                
                # Utiliser le service
                ReclamationService.resoudre_reclamation(
                    reclamation,
                    agent,
                    accorder_compensation,
                    montant_compensation
                )
                
                msg = f"✅ Réclamation {reclamation.numero_reclamation} résolue !"
                if accorder_compensation:
                    msg += f" Compensation de {montant_compensation:,.2f} DA accordée."
                
                messages.success(request, msg)
                return redirect('detail_reclamation', reclamation_id=reclamation.id)
                
            except Exception as e:
                messages.error(request, f"❌ Erreur : {str(e)}")
    else:
        form = ReclamationResolutionForm()
    
    return render(request, 'reclamations/resoudre.html', {
        'form': form,
        'reclamation': reclamation,
    })

def cloturer_reclamation(request, reclamation_id):
    """
    Clôture définitive d'une réclamation (doit être RESOLUE avant)
    """
    reclamation = get_object_or_404(Reclamation, id=reclamation_id)
    
    if request.method == 'POST':
        try:
            agent = request.POST.get('agent', 'Agent')
            ReclamationService.cloturer_reclamation(reclamation, agent)
            
            messages.success(request, f"✅ Réclamation {reclamation.numero_reclamation} clôturée !")
            return redirect('liste_reclamations')
            
        except ValidationError as e:
            messages.error(request, str(e))
            return redirect('detail_reclamation', reclamation_id=reclamation.id)
    
    return render(request, 'reclamations/cloturer.html', {
        'reclamation': reclamation,
    })

def annuler_reclamation(request, reclamation_id):
    """
    Annuler une réclamation (demande infondée, doublon, etc.)
    """
    reclamation = get_object_or_404(Reclamation, id=reclamation_id)
    
    if request.method == 'POST':
        try:
            motif = request.POST.get('motif', '')
            agent = request.POST.get('agent', 'Agent')
            
            if not motif:
                messages.error(request, "Le motif d'annulation est obligatoire")
                return redirect('detail_reclamation', reclamation_id=reclamation.id)
            
            ReclamationService.annuler_reclamation(reclamation, motif, agent)
            
            messages.success(request, f"✅ Réclamation {reclamation.numero_reclamation} annulée !")
            return redirect('liste_reclamations')
            
        except Exception as e:
            messages.error(request, f"❌ Erreur : {str(e)}")
            return redirect('detail_reclamation', reclamation_id=reclamation.id)
    
    return render(request, 'reclamations/annuler.html', {
        'reclamation': reclamation,
    })

def supprimer_reclamation(request, reclamation_id):
    """
    Suppression d'une réclamation (avec confirmation)
    """
    reclamation = get_object_or_404(Reclamation, id=reclamation_id)
    
    if request.method == 'POST':
        try:
            numero = reclamation.numero_reclamation
            reclamation.delete()
            messages.success(request, f"✅ Réclamation {numero} supprimée !")
            return redirect('liste_reclamations')
            
        except Exception as e:
            messages.error(request, f"❌ Erreur : {str(e)}")
            return redirect('detail_reclamation', reclamation_id=reclamation_id)
    
    return render(request, 'reclamations/supprimer.html', {
        'reclamation': reclamation,
    })

def exporter_reclamations_pdf(request):
    """
    Génère un PDF avec la liste de toutes les réclamations
    """
    reclamations = Reclamation.objects.all().select_related(
        'client'
    ).order_by('-date_creation')
    
    headers = ['N° Réclamation', 'Client', 'Nature', 'Priorité', 'Statut', 'Date']
    
    data = [
        [
            r.numero_reclamation,
            f"{r.client.prenom} {r.client.nom}",
            r.get_nature_display(),
            r.get_priorite_display(),
            r.get_statut_display(),
            r.date_creation.strftime('%d/%m/%Y')
        ]
        for r in reclamations
    ]
    
    return generer_pdf_liste("Liste des Réclamations", headers, data, "reclamations")

def exporter_reclamation_detail_pdf(request, reclamation_id):
    """
    Génère un PDF détaillé d'une réclamation
    """
    reclamation = Reclamation.objects.select_related(
        'client', 'facture'
    ).prefetch_related('expeditions').get(id=reclamation_id)
    
    sections = [
        {
            'titre': 'Informations de la Réclamation',
            'data': [
                ['N° Réclamation', reclamation.numero_reclamation],
                ['Client', f"{reclamation.client.prenom} {reclamation.client.nom}"],
                ['Téléphone', str(reclamation.client.telephone)],
                ['Type', reclamation.get_type_reclamation_display()],
                ['Nature', reclamation.get_nature_display()],
                ['Priorité', reclamation.get_priorite_display()],
                ['Statut', reclamation.get_statut_display()],
                ['Date création', reclamation.date_creation.strftime('%d/%m/%Y')],
                ['Objet', reclamation.objet],
                ['Description', reclamation.description],
            ]
        }
    ]
    
    # ========== EXPÉDITIONS CONCERNÉES ==========
    if reclamation.expeditions.exists():
        exp_data = [['N° Expédition', 'Destination', 'Statut']]
        for exp in reclamation.expeditions.all():
            exp_data.append([
                exp.get_numero_expedition(),
                f"{exp.destination.ville}, {exp.destination.wilaya}",
                exp.get_statut_display()
            ])
        
        sections.append({
            'titre': f'Expéditions concernées ({reclamation.expeditions.count()})',
            'data': exp_data
        })
    
    # ========== FACTURE CONCERNÉE ==========
    if reclamation.facture:
        facture_data = [
            ['N° Facture', reclamation.facture.numero_facture],
            ['Montant TTC', f"{reclamation.facture.montant_ttc:,.2f} DA"],
            ['Statut', reclamation.facture.get_statut_display()],
        ]
        sections.append({
            'titre': 'Facture concernée',
            'data': facture_data
        })
    
    # ========== TRAITEMENT ==========
    if reclamation.agent_responsable:
        traitement_data = [
            ['Agent responsable', reclamation.agent_responsable],
            ['Date assignation', reclamation.date_assignation.strftime('%d/%m/%Y') if reclamation.date_assignation else '-'],
            ['Réponse agent', reclamation.reponse_agent or 'Aucune'],
            ['Solution proposée', reclamation.solution_proposee or 'Aucune'],
            ['Date résolution', reclamation.date_resolution.strftime('%d/%m/%Y') if reclamation.date_resolution else 'Non résolue'],
            ['Délai traitement', f"{reclamation.delai_traitement_jours} jours" if reclamation.delai_traitement_jours else '-'],
        ]
        sections.append({
            'titre': 'Traitement',
            'data': traitement_data
        })
    
    # ========== COMPENSATION ==========
    if reclamation.compensation_accordee:
        comp_data = [
            ['Compensation accordée', 'OUI'],
            ['Montant', f"{reclamation.montant_compensation:,.2f} DA"],
        ]
        sections.append({
            'titre': 'Compensation',
            'data': comp_data
        })
    
    return generer_pdf_fiche(
        f"Réclamation - {reclamation.numero_reclamation}",
        sections,
        f"reclamation_{reclamation.id}",
        remarques=reclamation.remarques
    )

def home(request):
    """
    Page d'accueil (Dashboard)
    Affiche :
    - Favoris (4 raccourcis personnalisables)
    - Notifications non lues
    - Tournées en cours
    - Tournées prévues demain
    """
    from datetime import date, timedelta
    from django.db.models import Count
    from .constants import FONCTIONNALITES_DISPONIBLES, FAVORIS_PAR_DEFAUT
    
    # ========== FAVORIS ==========
    favoris_ids = request.session.get('favoris', FAVORIS_PAR_DEFAUT)
    favoris = [
        f for f in FONCTIONNALITES_DISPONIBLES 
        if f['id'] in favoris_ids
    ][:4]
    
    # ========== NOTIFICATIONS NON LUES ==========
    notifications = Notification.objects.filter(
        statut='NON_LUE'
    ).order_by('-date_creation')
    
    # ========== TOURNÉES EN COURS ==========
    # On récupère EXACTEMENT les mêmes champs que dans liste_tournees
    tournees_en_cours = Tournee.objects.filter(
        statut='EN_COURS'
    ).select_related('chauffeur', 'vehicule').annotate(
        nb_expeditions=Count('expeditions')
    ).order_by('date_depart')
    
    # ========== TOURNÉES PRÉVUES DEMAIN ==========
    demain = date.today() + timedelta(days=1)
    tournees_demain = Tournee.objects.filter(
        statut='PREVUE',
        date_depart__date=demain
    ).select_related('chauffeur', 'vehicule').annotate(
        nb_expeditions=Count('expeditions')
    ).order_by('date_depart')
    
    # ========== STATUTS DISPONIBLES (pour le select) ==========
    statuts_tournee = [
        ('PREVUE', 'Prévue'),
        ('EN_COURS', 'En cours'),
        ('TERMINEE', 'Terminée'),
    ]
    
    context = {
        'favoris': favoris,
        'notifications': notifications,
        'tournees_en_cours': tournees_en_cours,
        'tournees_demain': tournees_demain,
        'statuts_tournee': statuts_tournee,
    }
    
    return render(request, 'home.html', context)

def selectionner_favoris(request):
    """
    Page de sélection des favoris
    Affiche TOUTES les fonctionnalités disponibles
    L'utilisateur peut sélectionner max 4 favoris
    """
    from .constants import FONCTIONNALITES_DISPONIBLES, FAVORIS_PAR_DEFAUT
    
    if request.method == 'POST':
        favoris_selectionnes = request.POST.getlist('favoris')
        
        if len(favoris_selectionnes) > 4:
            messages.error(request, '❌ Vous ne pouvez sélectionner que 4 favoris maximum !')
            return redirect('selectionner_favoris')
        
        if len(favoris_selectionnes) == 0:
            messages.error(request, '❌ Veuillez sélectionner au moins 1 favori !')
            return redirect('selectionner_favoris')
        
        # Enregistrer en session
        request.session['favoris'] = favoris_selectionnes
        
        messages.success(request, f'✅ Vos {len(favoris_selectionnes)} favoris ont été enregistrés !')
        return redirect('home')
    
    # GET : Afficher le formulaire
    categories = {}
    for fonc in FONCTIONNALITES_DISPONIBLES:
        cat = fonc['categorie']
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(fonc)
    
    favoris_actuels = request.session.get('favoris', FAVORIS_PAR_DEFAUT)
    
    context = {
        'categories': categories,
        'favoris_actuels': favoris_actuels,
    }
    
    return render(request, 'favoris/selectionner.html', context)

def traiter_notification(request, notification_id):
    """
    Affiche les détails d'une notification et permet de la traiter
    """
    from .utils import NotificationService

    notification = get_object_or_404(Notification, id=notification_id)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        try:
            resultat = NotificationService.traiter_action_notification(
                notification_id,
                action
            )
            
            if resultat['success']:
                messages.success(request, resultat['message'])
                
                # Si redirection demandée (cas REPORTER)
                if 'redirect' in resultat:
                    return redirect(resultat['redirect'])
                
                # Sinon, retour au home
                return redirect('home')
            else:
                messages.error(request, resultat['message'])
                
        except Exception as e:
            messages.error(request, f"❌ Erreur : {str(e)}")
        
        return redirect('home')
    
    # GET : Afficher la notification
    return render(request, 'notifications/traiter.html', {
        'notification': notification,
    })

def liste_notifications(request):
    """
    Liste de toutes les notifications
    """
    notifications = Notification.objects.all().order_by('-date_creation')
    
    return render(request, 'notifications/liste.html', {
        'notifications': notifications,
    })



