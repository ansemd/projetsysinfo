from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import HttpResponse
from django.core.exceptions import ValidationError
from django.db.models import Q, Count, Sum, Prefetch
from django.urls import reverse
from .models import Client, Chauffeur, Vehicule, TypeService, Destination, Tarification, Tournee, Expedition, TrackingExpedition, Facture, Paiement, Incident, HistoriqueIncident, Reclamation, HistoriqueReclamation, Notification, AgentUtilisateur
from .forms import ClientForm, ChauffeurForm, VehiculeForm, TypeServiceForm, DestinationForm, TarificationForm, TourneeForm, ExpeditionForm, FactureForm, PaiementForm, IncidentForm, IncidentModificationForm, ReclamationForm, ReclamationModificationForm, ReclamationReponseForm, ReclamationResolutionForm, LoginForm, ChangerMotDePasseForm
from .utils import generer_pdf_fiche, generer_pdf_liste, IncidentService, ReclamationService, ExpeditionService
from django.utils import timezone
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from datetime import datetime, timedelta
from .services.analytics_service import AnalyticsService
from .services.stats_service import StatsService  

@login_required
def liste_clients(request):
    
    search = request.GET.get('search', '')
    
    if search:
        # Recherche 
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

@login_required
def exporter_clients_pdf(request):
    clients = Client.objects.all()
    headers = ['Id', 'Nom', 'Prénom', 'Téléphone', 'Solde']
    data = [[f"CL-{c.id:03d}", c.nom, c.prenom, c.telephone, c.solde] for c in clients]
    return generer_pdf_liste("Liste Clients", headers, data, "clients")

@login_required
def detail_client(request, client_id):
    
    client = get_object_or_404(Client, id=client_id)
    
    # Récupérer toutes les expéditions du client
    expeditions = client.expedition_set.all().order_by('-date_creation')
    
    stats_client = {
        'total_expeditions': expeditions.count(),
        'expeditions_livrees': expeditions.filter(statut='LIVRE').count(),
        'expeditions_en_cours': expeditions.filter(statut='EN_TRANSIT').count(),
        'expeditions_en_attente': expeditions.filter(statut='EN_ATTENTE').count(),
        'total_depense': expeditions.aggregate(Sum('montant_total'))['montant_total__sum'] or 0,
    }
    
    # Récupérer les factures du client
    factures = client.factures.all().order_by('-date_creation')[:5] 
    
    return render(request, 'clients/detail.html', {
        'client': client,
        'expeditions': expeditions,
        'stats_client': stats_client,
        'factures': factures,
    })

@login_required
def exporter_client_detail_pdf(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    
    # Récupérer expéditions et factures
    expeditions = client.expedition_set.all()
    factures = Facture.objects.filter(client=client).order_by('-date_creation')[:5]
    
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
    
    if expeditions.exists():
        exp_data = []
        for idx, exp in enumerate(expeditions, 1):
            exp_data.append([f"Expédition #{idx}", ""])
            exp_data.append(['N°', exp.get_numero_expedition()])
            exp_data.append(['Destination', f"{exp.destination.ville} - {exp.destination.wilaya}"])
            exp_data.append(['Type', exp.type_service.get_type_service_display()])
            exp_data.append(['Poids', f"{exp.poids} kg"])
            exp_data.append(['Montant', f"{exp.montant_total:,.2f} DA"])
            if idx < len(expeditions):
                exp_data.append(['', ''])
        
        sections.append({
            'titre': f'Expéditions facturées ({expeditions.count()})',
            'data': exp_data
        })
    
    if factures.exists():
        facture_data = []
        
        for idx, f in enumerate(factures, 1):
            facture_data.append([f"Facture #{idx}", ""])
            facture_data.append(['N°', f.numero_facture])
            facture_data.append(['Date de creation', f.date_creation.strftime('%d/%m/%Y')])
            facture_data.append(['Statut', f.get_statut_display()])
            facture_data.append(['Montant', f"{f.montant_ttc:,.2f} DA"])
        
        sections.append({
            'titre': 'Factures Récentes (5 dernières)',
            'data': facture_data
        })
    

    return generer_pdf_fiche(
        titre_document=f"Fiche Client - {client.prenom} {client.nom}",
        sections=sections,
        nom_fichier_base=f"client_{client.id:03d}",
        remarques=None  
    )

@login_required
def creer_client(request):
    
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save(commit=False)
            client.cree_par = request.user  
            client.save()
            messages.success(request, f"Client {client.prenom} {client.nom} créé par {request.user.username}")
            return redirect('liste_clients')
        else:
            messages.error(request, 'Erreur de validation. Veuillez vérifier les champs.')
    else:
        form = ClientForm()
    
    return render(request, 'clients/creer.html', {'form': form})

@login_required
def modifier_client(request, client_id):
    
    client = get_object_or_404(Client, id=client_id)
    
    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            client = form.save(commit=False)
            client.modifie_par = request.user
            client = form.save()
            messages.success(request, f'Client {client.prenom} {client.nom} modifié par {request.user.username}!')
            return redirect('detail_client', client_id=client.id)
        else:
            messages.error(request, 'Erreur de validation. Veuillez vérifier les champs.')
    else:
        form = ClientForm(instance=client)
    
    return render(request, 'clients/modifier.html', {
        'form': form,
        'client': client,
    })

@login_required
def supprimer_client(request, client_id):
    
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

    return render(request, 'clients/supprimer.html', {
        'client': client,
    })

@login_required
def liste_chauffeurs(request):
    
    search = request.GET.get('search', '')
    filtre_statut = request.GET.get('statut', '')  
    
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

@login_required
def exporter_chauffeurs_pdf(request):
    
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

@login_required
def modifier_statut_chauffeur(request, chauffeur_id):
    
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

@login_required
def detail_chauffeur(request, chauffeur_id):
    
    chauffeur = get_object_or_404(Chauffeur, id=chauffeur_id)

    tournee_actuelle = chauffeur.tournee_set.filter(
        statut__in=['EN_COURS', 'PREVUE']
    ).order_by('-date_creation').first()
    

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

@login_required
def exporter_chauffeur_detail_pdf(request, chauffeur_id):
    
    chauffeur = get_object_or_404(Chauffeur, id=chauffeur_id)
    

    tournees = chauffeur.tournee_set.all()

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
                ['Créé par', 
                f"{chauffeur.cree_par.first_name} {chauffeur.cree_par.last_name} (@{chauffeur.cree_par.username})" 
                if chauffeur.cree_par else 'Non renseigné'],
                ['Date de création', chauffeur.date_creation.strftime('%d/%m/%Y %H:%M')],
                ['Modifié par', 
                f"{chauffeur.modifie_par.first_name} {chauffeur.modifie_par.last_name} (@{chauffeur.modifie_par.username})" 
                if chauffeur.modifie_par else 'Jamais modifié'],
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

@login_required
def creer_chauffeur(request):
    
    if request.method == 'POST':
        form = ChauffeurForm(request.POST)
        if form.is_valid():
            chauffeur = form.save(commit=False)
            chauffeur.cree_par = request.user  
            chauffeur.save()
            messages.success(request, f"✅ Chauffeur {chauffeur.prenom} {chauffeur.nom} créé par {request.user.username}")
            return redirect('detail_chauffeur', chauffeur_id=chauffeur.id)
        else:

            messages.error(request, 'Erreur de validation. Veuillez vérifier les champs.')
    else:
        form = ChauffeurForm()
    
    return render(request, 'chauffeurs/creer.html', {'form': form})

@login_required
def modifier_chauffeur(request, chauffeur_id):
    
    chauffeur = get_object_or_404(Chauffeur, id=chauffeur_id)
    
    if request.method == 'POST':
        form = ChauffeurForm(request.POST, instance=chauffeur)
        if form.is_valid():
            chauffeur = form.save(commit=False)
            chauffeur.modifie_par = request.user
            chauffeur = form.save()
            messages.success(request, f'Chauffeur {chauffeur.prenom} {chauffeur.nom} modifié par {request.user.username}')
            return redirect('detail_chauffeur', chauffeur_id=chauffeur.id)
        else:
            messages.error(request, 'Erreur de validation. Veuillez vérifier les champs.')
    else:
        form = ChauffeurForm(instance=chauffeur)
    
    return render(request, 'chauffeurs/modifier.html', {
        'form': form,
        'chauffeur': chauffeur,
    })

@login_required
def supprimer_chauffeur(request, chauffeur_id):
    
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

@login_required
def liste_vehicules(request):
    
    search = request.GET.get('search', '')
    filtre_statut = request.GET.get('statut', '')
    
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

@login_required
def exporter_vehicules_pdf(request):
    
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

@login_required
def modifier_statut_vehicule(request, vehicule_id):
    
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

@login_required
def detail_vehicule(request, vehicule_id):
    
    vehicule = get_object_or_404(Vehicule, id=vehicule_id)

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

@login_required
def exporter_vehicule_detail_pdf(request, vehicule_id):
    
    vehicule = get_object_or_404(Vehicule, id=vehicule_id)

    tournees = vehicule.tournee_set.all()
    
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
                ['Créé par', 
                f"{vehicule.cree_par.first_name} {vehicule.cree_par.last_name} (@{vehicule.cree_par.username})" 
                if vehicule.cree_par else 'Non renseigné'],
                ['Date de création', vehicule.date_creation.strftime('%d/%m/%Y %H:%M')],
                ['Modifié par', 
                f"{vehicule.modifie_par.first_name} {vehicule.modifie_par.last_name} (@{vehicule.modifie_par.username})" 
                if vehicule.modifie_par else 'Jamais modifié'],
                ['Dernière modification', vehicule.date_modification.strftime('%d/%m/%Y %H:%M')],
                ['Remarques', vehicule.remarques or 'Aucune remarque'],
            ]
        }
    ]
    

    if tournees.exists():
        tournee_headers = ['Zone', 'Date Départ', 'Chauffeur', 'Statut']
        tournee_data = [tournee_headers]
        
        for t in tournees[:10]:  
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

    return generer_pdf_fiche(
        titre_document=f"Fiche Véhicule - {vehicule.numero_immatriculation}",
        sections=sections,
        nom_fichier_base=f"vehicule_{vehicule.numero_immatriculation}",
        remarques=None  
    )

@login_required
def creer_vehicule(request):
    if request.method == 'POST':
        form = VehiculeForm(request.POST)
        if form.is_valid():
            vehicule = form.save(commit=False)
            vehicule.cree_par = request.user  
            vehicule.save()
            messages.success(request, f'Véhicule {vehicule.numero_immatriculation} créé par {request.user.username}')
            return redirect('detail_vehicule', vehicule_id=vehicule.id)
        else:
            messages.error(request, 'Erreur de validation. Veuillez vérifier les champs.')
    else:
        form = VehiculeForm()
    
    return render(request, 'vehicules/creer.html', {'form': form})

@login_required
def modifier_vehicule(request, vehicule_id):
    vehicule = get_object_or_404(Vehicule, id=vehicule_id)
    
    if request.method == 'POST':
        form = VehiculeForm(request.POST, instance=vehicule)
        if form.is_valid():
            vehicule = form.save(commit=False)
            vehicule.modifie_par = request.user
            vehicule = form.save()
            
            messages.success(request, f'Véhicule {vehicule.numero_immatriculation} modifié par {request.user.username}!')
            return redirect('detail_vehicule', vehicule_id=vehicule.id)
        else:
            messages.error(request, 'Erreur de validation. Veuillez vérifier les champs.')
    else:
        form = VehiculeForm(instance=vehicule)
    
    return render(request, 'vehicules/modifier.html', {
        'form': form,
        'vehicule': vehicule,
    })

@login_required
def supprimer_vehicule(request, vehicule_id):
    
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

@login_required
def liste_typeservices(request):
    
    typeservices = TypeService.objects.all().order_by('type_service')
    
    return render(request, 'typeservices/liste.html', {
        'typeservices': typeservices,
    })

@login_required
def exporter_typeservices_pdf(request):
    
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

@login_required
def detail_typeservice(request, typeservice_id):
    
    typeservice = get_object_or_404(TypeService, id=typeservice_id)
    
    nb_expeditions = typeservice.expedition_set.count()
    
    return render(request, 'typeservices/detail.html', {
        'typeservice': typeservice,
        'nb_expeditions': nb_expeditions,
    })

@login_required
def exporter_typeservice_detail_pdf(request, typeservice_id):
    
    typeservice = get_object_or_404(TypeService, id=typeservice_id)
    
    expeditions = typeservice.expedition_set.all()
    tarifications = typeservice.tarification_set.all()
    
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
    

    return generer_pdf_fiche(
        titre_document=f"Fiche Type de Service - {typeservice.get_type_service_display()}",
        sections=sections,
        nom_fichier_base=f"typeservice_{typeservice.type_service}",
        remarques=None
    )

@login_required
def creer_typeservice(request):
    
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

@login_required
def modifier_typeservice(request, typeservice_id):
    
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

@login_required
def supprimer_typeservice(request, typeservice_id):
    
    typeservice = get_object_or_404(TypeService, id=typeservice_id)

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

@login_required
def liste_destinations(request):
    
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

@login_required
def exporter_destinations_pdf(request):
    
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

@login_required
def detail_destination(request, destination_id):
   
    destination = get_object_or_404(Destination, id=destination_id)
    
    nb_tarifications = destination.tarification_set.count()
    nb_expeditions = destination.expedition_set.count()
    
    return render(request, 'destinations/detail.html', {
        'destination': destination,
        'nb_tarifications': nb_tarifications,
        'nb_expeditions': nb_expeditions,
    })

@login_required
def exporter_destination_detail_pdf(request, destination_id):
    
    destination = get_object_or_404(Destination, id=destination_id)
    
    nb_tarifications = destination.tarification_set.count()
    nb_expeditions = destination.expedition_set.count()
    
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

@login_required
def creer_destination(request):
    if request.method == 'POST':
        form = DestinationForm(request.POST)
        if form.is_valid():
            destination = form.save()
            messages.success(request, f'Destination "{destination.ville} - {destination.wilaya}" créée avec succès!')
            return redirect('detail_destination', destination_id=destination.id)
        else:
            # Afficher les erreurs détaillées
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
            messages.error(request, 'Erreur de validation. Veuillez vérifier les champs.')
    else:
        form = DestinationForm()
    
    return render(request, 'destinations/creer.html', {'form': form})

@login_required
def modifier_destination(request, destination_id):
    
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

@login_required
def supprimer_destination(request, destination_id):
    
    destination = get_object_or_404(Destination, id=destination_id)
    
    nb_tarifications = destination.tarification_set.count()
    nb_expeditions = destination.expedition_set.count()
    
    if request.method == 'POST':
        try:
            if nb_expeditions > 0:
                messages.error(request, f"Impossible de supprimer : {nb_expeditions} expédition(s) utilisent cette destination.")
                return redirect('detail_destination', destination_id=destination_id)
            
            if nb_tarifications > 0:
                destination.tarification_set.all().delete()
                messages.warning(request, f"{nb_tarifications} tarification(s) associée(s) ont été supprimée(s).")
            
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

@login_required
def liste_tarifications(request):
    
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

@login_required
def exporter_tarifications_pdf(request):
    
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

@login_required
def detail_tarification(request, tarification_id):
    """
    Détails d'une tarification + statistiques
    """
    tarification = get_object_or_404(Tarification, id=tarification_id)
    
    nb_expeditions = tarification.destination.expedition_set.filter(
        type_service=tarification.type_service
    ).count()
    
    return render(request, 'tarifications/detail.html', {
        'tarification': tarification,
        'nb_expeditions': nb_expeditions,
    })

@login_required
def exporter_tarification_detail_pdf(request, tarification_id):
    """
    Export PDF de la fiche détaillée d'une tarification
    """
    tarification = get_object_or_404(Tarification, id=tarification_id)
    

    nb_expeditions = tarification.destination.expedition_set.filter(
        type_service=tarification.type_service
    ).count()
    

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

@login_required
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

@login_required
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

@login_required
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

@login_required
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
    
    statut_filter = request.GET.get('statut', '')
    if statut_filter:
        tournees = tournees.filter(statut=statut_filter)
    
    zone_filter = request.GET.get('zone', '')
    if zone_filter:
        tournees = tournees.filter(zone_cible=zone_filter)
    
    tournees = tournees.annotate(nb_expeditions=Count('expeditions'))
    tournees = tournees.order_by('-date_depart')
    
    stats = {
        'total_tournees': Tournee.objects.count(),
        'prevues': Tournee.objects.filter(statut='PREVUE').count(),
        'en_cours': Tournee.objects.filter(statut='EN_COURS').count(),
        'terminees': Tournee.objects.filter(statut='TERMINEE').count(),
    }
    
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

@login_required
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

@login_required
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
            messages.success(request, f'Statut de la tournée #{tournee.id} modifié avec succès !')
        else:
            messages.error(request, 'Statut invalide')
        
        if source == 'home':
            return redirect('home')
        else:
            return redirect('liste_tournees')
    
    return redirect('liste_tournees')

@login_required
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

@login_required
def exporter_tournee_detail_pdf(request, tournee_id):
    """
    Exporte les détails d'une tournée en PDF
    """
    tournee = get_object_or_404(
        Tournee.objects.select_related('chauffeur', 'vehicule'),
        id=tournee_id
    )

    expeditions = tournee.expeditions.all().select_related('client', 'destination', 'type_service')
    
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
                ['Créé par', 
                f"{tournee.cree_par.first_name} {tournee.cree_par.last_name} (@{tournee.cree_par.username})" 
                if tournee.cree_par else 'Non renseigné'],
                ['Date de création', tournee.date_creation.strftime('%d/%m/%Y %H:%M')],
                ['Modifié par', 
                f"{tournee.modifie_par.first_name} {tournee.modifie_par.last_name} (@{tournee.modifie_par.username})" 
                if tournee.modifie_par else 'Jamais modifié'],
                ['Date de modification', 
                tournee.date_modification.strftime('%d/%m/%Y à %H:%M') if tournee.modifie_par else '-'],
                ['Remarques', tournee.remarques or 'Aucune remarque'],
            ]
        }
    ]
    
    if expeditions.exists():
        exp_data = []
        for idx, exp in enumerate(expeditions, 1):
            exp_data.append([f"Expédition #{idx}", ""])
            exp_data.append(['N°', exp.get_numero_expedition()])
            exp_data.append(['Destination', f"{exp.destination.ville} - {exp.destination.wilaya}"])
            exp_data.append(['Type', exp.type_service.get_type_service_display()])
            exp_data.append(['Poids', f"{exp.poids} kg"])
            exp_data.append(['Montant', f"{exp.montant_total:,.2f} DA"])
            if idx < len(expeditions):
                exp_data.append(['', ''])
        
        sections.append({
            'titre': f'Expéditions facturées ({expeditions.count()})',
            'data': exp_data
        })
    
    return generer_pdf_fiche(
        titre_document=f"Fiche Tournée #{tournee.id}",
        sections=sections,
        nom_fichier_base=f"tournee_{tournee.id}",
        remarques=None  # Déjà dans la table
    )

@login_required
def creer_tournee(request):
    """
    Création d'une tournée manuelle
    """
    if request.method == 'POST':
        form = TourneeForm(request.POST)
        
        if form.is_valid():
            try:
                tournee = form.save(commit=False)
                tournee.cree_par = request.user  
                tournee.save()
                
                messages.success(request, f"Tournée #{tournee.id} créé par {request.user.username} !")
                return redirect('detail_tournee', tournee_id=tournee.id)
            
            except Exception as e:
                messages.error(request, f"Erreur lors de la création : {str(e)}")
    else:
        form = TourneeForm()
    
    return render(request, 'tournees/creer.html', {
        'form': form,
    })

@login_required
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

                tournee = form.save(commit=False)
                tournee.modifie_par = request.user
                tournee = form.save()
                
                messages.success(request, f"Tournée #{tournee.id} modifiée par {request.user.username} !")
                return redirect('detail_tournee', tournee_id=tournee.id)
            
            except Exception as e:
                messages.error(request, f"Erreur lors de la modification : {str(e)}")
    else:
        form = TourneeForm(instance=tournee)
    
    return render(request, 'tournees/modifier.html', {
        'form': form,
        'tournee': tournee,
    })

@login_required
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

@login_required
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
            
            if kilometrage_arrivee < tournee.kilometrage_depart:
                messages.error(
                    request, 
                    f"Le kilométrage d'arrivée ({kilometrage_arrivee} km) doit être supérieur "
                    f"au kilométrage de départ ({tournee.kilometrage_depart} km)"
                )
                return render(request, 'tournees/terminer.html', {'tournee': tournee})
            
            from django.utils import timezone
            from .utils import TourneeService
            
            tournee.kilometrage_arrivee = kilometrage_arrivee
            tournee.date_retour_reelle = timezone.now()
            
            TourneeService.calculer_kilometrage_et_consommation(tournee)
            
            tournee.vehicule.kilometrage = kilometrage_arrivee
            tournee.vehicule.statut = 'DISPONIBLE'
            tournee.vehicule.save()
            
            tournee.chauffeur.statut_disponibilite = 'DISPONIBLE'
            tournee.chauffeur.save()
            
            for exp in tournee.expeditions.all():
                if exp.statut == 'EN_TRANSIT':
                    exp.statut = 'LIVRE'
                    exp.date_livraison_reelle = timezone.now().date()
                    exp.save(update_fields=['statut', 'date_livraison_reelle'])
            
            tournee.save()
            
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
                f"Tournée {tournee.get_numero_tournee()} finalisée ! "
                f"Kilométrage parcouru : {tournee.kilometrage_parcouru} km, "
                f"Consommation : {tournee.consommation_carburant:.2f} L"
            )
            
            return redirect('detail_tournee', tournee_id=tournee_id)
        
        except Exception as e:
            messages.error(request, f"❌ Erreur : {str(e)}")
    
    return render(request, 'tournees/terminer.html', {
        'tournee': tournee,
    })

@login_required
def liste_expeditions(request):
    """
    Liste des expéditions avec recherche et filtres
    """
    expeditions = Expedition.objects.all().select_related(
        'client', 'destination', 'type_service', 'tournee'
    )
    
    search = request.GET.get('search', '')
    if search:
        expeditions = expeditions.filter(
            Q(client__nom__icontains=search) |
            Q(client__prenom__icontains=search) |
            Q(destination__ville__icontains=search) |
            Q(destination__wilaya__icontains=search) |
            Q(nom_destinataire__icontains=search)
        )
    

    statut_filter = request.GET.get('statut', '')
    if statut_filter:
        expeditions = expeditions.filter(statut=statut_filter)
    
    type_filter = request.GET.get('type', '')
    if type_filter:
        expeditions = expeditions.filter(type_service__type_service=type_filter)
    
    expeditions = expeditions.order_by('-date_creation')
    
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

@login_required
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

@login_required
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
    
    trackings = expedition.suivis.all().order_by('-date_heure')
    
    return render(request, 'expeditions/detail.html', {
        'expedition': expedition,
        'trackings': trackings,
    })

@login_required
def exporter_expedition_detail_pdf(request, expedition_id):
    """Export PDF détail expédition avec tracking"""
    expedition = get_object_or_404(
        Expedition.objects.select_related('client', 'destination', 'type_service', 'tournee'),
        id=expedition_id
    )
    trackings = expedition.suivis.all().order_by('-date_heure')
    
    sections = []
    sections.append({
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
                ['Créé par', 
                f"{expedition.cree_par.first_name} {expedition.cree_par.last_name} (@{expedition.cree_par.username})" 
                if expedition.cree_par else 'Non renseigné'],
                ['Date création', expedition.date_creation.strftime('%d/%m/%Y %H:%M')],
                ['Modifié par', 
                f"{expedition.modifie_par.first_name} {expedition.modifie_par.last_name} (@{expedition.modifie_par.username})" 
                if expedition.modifie_par else 'Jamais modifié'],
                ['Date de modification', 
                expedition.date_modification.strftime('%d/%m/%Y à %H:%M') if expedition.modifie_par else '-'],
                ['Description', expedition.description or 'Aucune description'],
                ['Remarques', expedition.remarques or 'Aucune remarque'],
            ]
        })
    
    if trackings.exists():
        tracking_data = []
        for idx, t in enumerate(trackings, 1):
            tracking_data.append([f"Historique de suivi #{idx}", ""])
            tracking_data.append(['date', t.date_heure.strftime('%d/%m/%Y %H:%M')])
            tracking_data.append(['statut', t.get_statut_etape_display()])
            tracking_data.append(['commentaire', t.commentaire or '-'])
            if idx < len(trackings):
                tracking_data.append(['', ''])
        
        sections.append({
            'titre': f'Historique de suivi ({trackings.count()} étapes)',
            'data': tracking_data
        })
    
    return generer_pdf_fiche(
        f"Fiche Expédition - {expedition.get_numero_expedition()}",
        sections,
        f"expedition_{expedition.id}",
        remarques=None  
    )

@login_required
def creer_expedition(request):
    if request.method == 'POST':
        form = ExpeditionForm(request.POST)
        
        if form.is_valid():
            try:
                expedition = form.save(commit=False)
                expedition.cree_par = request.user  
                expedition.save()

                ExpeditionService.calculer_montant(expedition)

                try:
                    ExpeditionService.affecter_tournee_intelligente(expedition)
                except ValidationError as e:
                    messages.warning(request, str(e))

                from .utils import FacturationService
                facture = FacturationService.gerer_facture_expedition(
                    expedition, 
                    created_by=request.user  
                )
                
                messages.success(request, f"Expédition {expedition.get_numero_expedition()} créée par {request.user.username} ! ")
                return redirect('detail_expedition', expedition_id=expedition.id)
            
            except Exception as e:
                messages.error(request, f"Erreur : {str(e)}")
    else:
        form = ExpeditionForm()
    
    return render(request, 'expeditions/creer.html', {
        'form': form,
    })

@login_required
def modifier_expedition(request, expedition_id):
    """
    Modification d'une expédition (EN_ATTENTE uniquement)
    """
    expedition = get_object_or_404(Expedition, id=expedition_id)
    
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
                expedition = form.save(commit=False)
                expedition.modifie_par = request.user
                expedition = form.save()
                messages.success(request, f"Expédition {expedition.get_numero_expedition()} modifiée par {request.user.username} !")
                return redirect('detail_expedition', expedition_id=expedition.id)
            
            except Exception as e:
                messages.error(request, f"Erreur : {str(e)}")
    else:
        form = ExpeditionForm(instance=expedition)
    
    return render(request, 'expeditions/modifier.html', {
        'form': form,
        'expedition': expedition,
    })

@login_required
def supprimer_expedition(request, expedition_id):
    """
    Suppression d'une expédition
    La logique de validation est dans le signal pre_delete
    """
    expedition = get_object_or_404(Expedition, id=expedition_id)

    if request.method == 'POST':
        try:
            numero_expedition = expedition.get_numero_expedition()

            expedition.delete()

            messages.success(
                request,
                f"Expédition {numero_expedition} supprimée avec succès"
            )
            return redirect('liste_expeditions')

        except ValidationError as e:
            messages.error(request, str(e))
            return redirect('detail_expedition', expedition_id=expedition_id)

        except Exception as e:
            messages.error(request, f"Erreur : {str(e)}")
            return redirect('liste_expeditions')

    return render(request, 'expeditions/supprimer.html', {
        'expedition': expedition,
    })

@login_required
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
    

    expeditions_data = []
    for exp in expeditions:
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

@login_required
def detail_tracking(request, expedition_id):
    """
    Redirige vers la page de détails de l'expédition
    (qui contient la table tracking détaillée en dessous)
    """
    return redirect('detail_expedition', expedition_id=expedition_id)

@login_required
def liste_factures(request):
    """
    Affiche la liste de toutes les factures
    
    FONCTIONNALITÉS :
    - Recherche par nom du client (nom ou prénom)
    - Filtre par statut (IMPAYEE, PAYEE, etc.)
    - Statistiques globales
    """
    factures = Facture.objects.all().select_related('client')
    

    search = request.GET.get('search', '')
    if search:
        factures = factures.filter(
            Q(client__nom__icontains=search) |       
            Q(client__prenom__icontains=search) |   
            Q(numero_facture__icontains=search)     
        )
    

    statut_filter = request.GET.get('statut', '')
    if statut_filter:
        factures = factures.filter(statut=statut_filter)
    

    factures = factures.order_by('-date_creation')
    
    stats = {
        'total': Facture.objects.count(),
        'impayees': Facture.objects.filter(statut='IMPAYEE').count(),
        'partiellement_payees': Facture.objects.filter(statut='PARTIELLEMENT_PAYEE').count(),
        'payees': Facture.objects.filter(statut='PAYEE').count(),
        'en_retard': Facture.objects.filter(statut='EN_RETARD').count(),
        'montant_total': Facture.objects.aggregate(Sum('montant_ttc'))['montant_ttc__sum'] or 0,
    }
    
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

@login_required
def exporter_factures_pdf(request):
    """
    Génère un PDF avec la liste de toutes les factures
    Format : Tableau avec colonnes [N° Facture, Client, Montant, Statut, Échéance]
    """
    factures = Facture.objects.all().select_related('client').order_by('-date_creation')
    

    headers = ['N° Facture', 'Client', 'Montant TTC', 'Statut', 'Échéance']
    
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

@login_required
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
    

    paiements = facture.paiements.all().order_by('-date_paiement')
    
    expeditions = facture.expeditions.all().select_related(
        'destination', 'type_service', 'tournee'
    )
    
    stats_paiements = {
        'total_paye': paiements.aggregate(Sum('montant_paye'))['montant_paye__sum'] or 0,
        'nb_paiements': paiements.count(),
    }
    
    peut_ajouter_paiement = facture.statut not in ['PAYEE', 'ANNULEE']

    montant_restant = FacturationService.calculer_montant_restant(facture)
    
    return render(request, 'factures/detail.html', {
        'facture': facture,
        'paiements': paiements,
        'expeditions': expeditions,
        'stats_paiements': stats_paiements,
        'peut_ajouter_paiement': peut_ajouter_paiement, 
    })

@login_required
def exporter_facture_detail_pdf(request, facture_id):
    facture = get_object_or_404(Facture.objects.select_related('client'), id=facture_id)
    paiements = facture.paiements.all().order_by('-date_paiement')
    expeditions = facture.expeditions.all().select_related('destination', 'type_service')
    
    sections = []
    sections.append({
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
    })
    
    if expeditions.exists():
        exp_data = []
        for idx, exp in enumerate(expeditions, 1):
            exp_data.append([f"Expédition #{idx}", ""])
            exp_data.append(['N°', exp.get_numero_expedition()])
            exp_data.append(['Destination', f"{exp.destination.ville} - {exp.destination.wilaya}"])
            exp_data.append(['Type', exp.type_service.get_type_service_display()])
            exp_data.append(['Poids', f"{exp.poids} kg"])
            exp_data.append(['Montant', f"{exp.montant_total:,.2f} DA"])
            if idx < len(expeditions):
                exp_data.append(['', ''])
        
        sections.append({
            'titre': f'Expéditions facturées ({expeditions.count()})',
            'data': exp_data
        })
    
    if paiements.exists():
        paie_data = []
        total_paye = 0
        
        for idx, p in enumerate(paiements, 1):
            total_paye += p.montant_paye
            paie_data.append([f"Paiement #{idx}", ""])
            paie_data.append(['Date', p.date_paiement.strftime('%d/%m/%Y')])
            paie_data.append(['Montant', f"{p.montant_paye:,.2f} DA"])
            paie_data.append(['Mode', p.get_mode_paiement_display()])
            paie_data.append(['Référence', p.reference_transaction or 'Non renseignée'])
            
            if idx < len(paiements):
                paie_data.append(['', ''])
        
        sections.append({
            'titre': f'Paiements ({paiements.count()})',
            'data': paie_data
        })
        
        reste = facture.montant_ttc - total_paye
        recap_data = [
            ['Total payé', f"{total_paye:,.2f} DA"],
        ]
        
        if reste > 0:
            recap_data.append(['Reste à payer', f"{reste:,.2f} DA (⚠️ IMPAYÉ)"])
        elif reste < 0:
            recap_data.append(['Trop-perçu', f"{-reste:,.2f} DA"])
        else:
            recap_data.append(['Reste à payer', "0,00 DA (✓ PAYÉE)"])
        
        sections.append({
            'titre': 'Récapitulatif financier',
            'data': recap_data
        })
    
    return generer_pdf_fiche(
        titre_document=f"Facture - {facture.numero_facture}",
        sections=sections,
        nom_fichier_base=f"facture_{facture.id}",
        remarques=""
    )

@login_required
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

@login_required
def supprimer_facture(request, facture_id):
    """
    Supprime une facture
    ATTENTION : Les paiements associés seront aussi supprimés (cascade)
    """
    facture = get_object_or_404(Facture, id=facture_id)
    
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

@login_required
def liste_paiements(request):
    """
    Affiche la liste de tous les paiements
    
    FONCTIONNALITÉS :
    - Recherche par nom client ou référence transaction
    - Filtre par mode de paiement
    - Statistiques globales
    """
    paiements = Paiement.objects.all().select_related('facture', 'facture__client')
    

    search = request.GET.get('search', '')
    if search:
        paiements = paiements.filter(
            Q(facture__client__nom__icontains=search) |
            Q(facture__client__prenom__icontains=search) |
            Q(reference_transaction__icontains=search)
        )
    
    mode_filter = request.GET.get('mode', '')
    if mode_filter:
        paiements = paiements.filter(mode_paiement=mode_filter)
    
    paiements = paiements.order_by('-date_paiement')

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

@login_required
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

@login_required
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

@login_required
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
                ['Enregistré par', 
                f"{paiement.cree_par.first_name} {paiement.cree_par.last_name} (@{paiement.cree_par.username})" 
                if paiement.cree_par else 'Non renseigné'],
                ['Date d\'enregistrement', paiement.date_paiement.strftime('%d/%m/%Y à %H:%M')],
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

@login_required
def creer_paiement(request, facture_id=None):
    """
    Enregistre un nouveau paiement
    """
    depuis_facture = facture_id is not None
    facture = None
    
    if depuis_facture:
        facture = get_object_or_404(Facture, id=facture_id)
        
        if facture.statut in ['PAYEE', 'ANNULEE']:
            messages.error(request, f"Impossible : facture {facture.get_statut_display()}")
            return redirect('detail_facture', facture_id=facture_id)
    
    if request.method == 'POST':
        form = PaiementForm(
            request.POST,
            depuis_facture=depuis_facture,
            facture_id=facture_id
        )
        
        if form.is_valid():
            try:
                paiement = form.save(commit=False)
                paiement.cree_par = request.user  
                paiement.save()
                
                messages.success(
                    request,
                    f"Paiement de {paiement.montant_paye:,.2f} DA enregistré par {request.user.username} !"
                )
                
                if depuis_facture:
                    return redirect('detail_facture', facture_id=facture_id)
                else:
                    return redirect('detail_paiement', paiement_id=paiement.id)
            except Exception as e:
                messages.error(request, f"❌ Erreur : {str(e)}")
    else:
        form = PaiementForm(
            depuis_facture=depuis_facture,
            facture_id=facture_id
        )
    
    return render(request, 'paiements/creer.html', {
        'form': form,
        'depuis_facture': depuis_facture,
        'facture': facture,
    })

@login_required
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
            facture = paiement.facture  
            paiement.delete()           
            
            messages.success(request, f"Paiement de {paiement.montant_paye:,.2f} DA supprimé")
            return redirect('detail_facture', facture_id=facture.id)
        except Exception as e:
            messages.error(request, f"Erreur : {str(e)}")
            return redirect('detail_paiement', paiement_id=paiement_id)
    
    return render(request, 'paiements/supprimer.html', {
        'paiement': paiement,
    })

@login_required
def liste_incidents(request):
    """
    Liste avec recherche et filtres
    """
    incidents = Incident.objects.all().select_related('expedition', 'tournee')
    
    search = request.GET.get('search', '')
    if search:
        incidents = incidents.filter(
            Q(numero_incident__icontains=search) |
            Q(titre__icontains=search) |
            Q(description__icontains=search) |
            Q(signale_par__icontains=search) |
            Q(lieu_incident__icontains=search)
        )
    
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
    
    stats = {
        'total': incidents.count(),
        'signales': Incident.objects.filter(statut='SIGNALE').count(),
        'en_cours': Incident.objects.filter(statut='EN_COURS').count(),
        'resolus': Incident.objects.filter(statut='RESOLU').count(),
        'clos': Incident.objects.filter(statut='CLOS').count(),
        'critiques': Incident.objects.filter(severite='CRITIQUE').count(),
        'eleves': Incident.objects.filter(severite='ELEVEE').count(),
    }
    
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

@login_required
def detail_incident(request, incident_id):
    """
    Affiche tous les détails + historique
    """
    incident = get_object_or_404(
        Incident.objects.select_related('expedition', 'tournee'),
        id=incident_id
    )
    
    historique = incident.historique.all().order_by('-date_action')
    
    return render(request, 'incidents/detail.html', {
        'incident': incident,
        'historique': historique,
    })

@login_required
def creer_incident(request):
    """
    Créer un incident avec notification automatique
    """
    if request.method == 'POST':
        form = IncidentForm(request.POST, request.FILES, user=request.user)
        
        if form.is_valid():
            try:
                incident = form.save(commit=False)

                if not incident.signale_par:
                    incident.signale_par = request.user

                if incident.expedition and incident.expedition.tournee:
                    incident.tournee = incident.expedition.tournee
                
                if incident.type_incident in ['PERTE', 'ACCIDENT']:
                    incident.severite = 'CRITIQUE'
                elif incident.type_incident in ['ENDOMMAGEMENT', 'PROBLEME_TECHNIQUE']:
                    incident.severite = 'ELEVEE'
                elif incident.type_incident == 'RETARD':
                    incident.severite = 'MOYENNE'
                else:
                    incident.severite = 'FAIBLE'
                
                incident.taux_remboursement = IncidentService.obtenir_taux_remboursement(
                    incident.type_incident
                )
                
                incident.save()
                

                if incident.agent_responsable:
                    Notification.objects.create(
                        type_notification='INCIDENT_AFFECTE',
                        titre=f"Incident affecté - {incident.numero_incident}",
                        message=f"Vous avez été affecté à l'incident {incident.numero_incident} par {request.user.first_name} {request.user.last_name}",
                        incident=incident,
                        statut='NON_LUE'
                    )
                    
                    HistoriqueIncident.objects.create(
                        incident=incident,
                        action="Création + Affectation",
                        auteur=f"{request.user.first_name} {request.user.last_name}",
                        details=f"Incident créé et affecté à {incident.agent_responsable.first_name} {incident.agent_responsable.last_name}",
                        ancien_statut=None,
                        nouveau_statut='EN_COURS'
                    )
                    
                    messages.success(
                        request,
                        f"Incident {incident.numero_incident} créé et affecté à "
                        f"{incident.agent_responsable.first_name} {incident.agent_responsable.last_name}"
                    )
                
                else:
                    from django.contrib.auth import get_user_model
                    AgentUtilisateur = get_user_model()
                    agent_responsable_principal = AgentUtilisateur.objects.filter(
                        is_responsable=True
                    ).first()
                    
                    if agent_responsable_principal:
                        Notification.objects.create(
                            type_notification='INCIDENT_CREE',
                            titre=f"Nouvel incident - {incident.numero_incident}",
                            message=f"Nouvel incident {incident.get_type_incident_display()} créé par {incident.signale_par.first_name} {incident.signale_par.last_name}",
                            incident=incident,
                            statut='NON_LUE'
                        )
                    

                    HistoriqueIncident.objects.create(
                        incident=incident,
                        action="Création",
                        auteur=f"{request.user.first_name} {request.user.last_name}",
                        details=f"Incident signalé - En attente d'affectation",
                        ancien_statut=None,
                        nouveau_statut='SIGNALE'
                    )
                    
                    messages.success(
                        request,
                        f"Incident {incident.numero_incident} créé par {request.user.username}. "
                        f"En attente d'affectation."
                    )
                
                return redirect('detail_incident', incident_id=incident.id)
                
            except Exception as e:
                messages.error(request, f"❌ Erreur : {str(e)}")
    else:
        form = IncidentForm(user=request.user)
    
    return render(request, 'incidents/creer.html', {
        'form': form,
    })

@login_required
def modifier_incident(request, incident_id):
    """
    Modification d'un incident existant
    """
    incident = get_object_or_404(Incident, id=incident_id)
    if incident.agent_responsable != request.user and not request.user.is_responsable:
        messages.error(
            request,
            "❌ Accès refusé : Seul l'agent affecté ou le responsable principal peut modifier cet incident"
        )
        return redirect('detail_incident', incident_id=incident.id)
    
    if request.method == 'POST':
        form = IncidentModificationForm(request.POST, request.FILES, instance=incident, user=request.user)
        
        if form.is_valid():
            try:
                incident = form.save()
                messages.success(request, f"Incident {incident.numero_incident} modifié !")
                return redirect('detail_incident', incident_id=incident.id)
            except Exception as e:
                messages.error(request, f"❌ Erreur : {str(e)}")
    else:
        form = IncidentModificationForm(instance=incident, user=request.user)
    
    return render(request, 'incidents/modifier.html', {
        'form': form,
        'incident': incident,
    })

@login_required
def resoudre_incident(request, incident_id):
    """
    Résoudre un incident avec traitement personnalisé selon le type
    """
    from decimal import Decimal
    
    incident = get_object_or_404(Incident, id=incident_id)

    if incident.agent_responsable != request.user and not request.user.is_responsable:
        messages.error(
            request,
            "❌ Accès refusé : Seul l'agent affecté ou le responsable principal peut résoudre cet incident"
        )
        return redirect('detail_incident', incident_id=incident.id)
    
    expedition = incident.expedition
    
    if not expedition:
        messages.error(request, "❌ Aucune expédition associée à cet incident")
        return redirect('detail_incident', incident_id=incident.id)
    
    cause_auto = None
    if incident.type_incident == 'RETARD':
        cause_auto = IncidentService.analyser_cause_retard(expedition)
    
    taux = IncidentService.obtenir_taux_remboursement(incident.type_incident)
    montant_ttc = expedition.montant_total * Decimal('1.19')
    montant_rembourse = montant_ttc * (taux / Decimal('100.00'))

    type_incident = incident.type_incident
    
    if type_incident in IncidentService.INCIDENTS_GRAVES_ANNULATION:
        options_statut = [('ANNULE', 'Expédition annulée automatiquement')]
        statut_auto = True
    
    elif type_incident in IncidentService.TYPES_REEXPEDITION:
        options_statut = [
            ('REENVOYE', 'Réexpédier le colis (nouvelle tournée + nouvelle facture)'),
            ('ANNULE', 'Annuler définitivement l\'expédition')
        ]
        statut_auto = False
    
    else:
        options_statut = [
            ('CONTINUE', 'Expédition continue sans changement'),
            ('ANNULE', 'Annuler l\'expédition')
        ]
        statut_auto = False

    
    if request.method == 'POST':
        try:
            solution = request.POST.get('solution', '').strip()
            if not solution:
                messages.error(request, "La solution est obligatoire")
                return render(request, 'incidents/resoudre.html', {
                    'incident': incident,
                    'expedition': expedition,
                    'cause_auto': cause_auto,
                    'taux': taux,
                    'montant_rembourse': montant_rembourse,
                    'montant_ttc': montant_ttc,
                    'options_statut': options_statut,
                    'statut_auto': statut_auto,
                })
            
            if incident.type_incident == 'RETARD':
                cause = cause_auto  
            else:
                cause = request.POST.get('cause', '').strip()
                if not cause:
                    messages.error(request, "❌ La cause est obligatoire")
                    return render(request, 'incidents/resoudre.html', {
                        'incident': incident,
                        'expedition': expedition,
                        'cause_auto': cause_auto,
                        'taux': taux,
                        'montant_rembourse': montant_rembourse,
                        'montant_ttc': montant_ttc,
                        'options_statut': options_statut,
                        'statut_auto': statut_auto,
                    })
            
            if statut_auto:
                nouveau_statut_exp = 'ANNULE'
            else:
                nouveau_statut_exp = request.POST.get('nouveau_statut_exp')
                if not nouveau_statut_exp:
                    messages.error(request, "❌ Veuillez choisir un statut pour l'expédition")
                    return render(request, 'incidents/resoudre.html', {
                        'incident': incident,
                        'expedition': expedition,
                        'cause_auto': cause_auto,
                        'taux': taux,
                        'montant_rembourse': montant_rembourse,
                        'montant_ttc': montant_ttc,
                        'options_statut': options_statut,
                        'statut_auto': statut_auto,
                    })
            
            donnees_resolution = {
                'cause': cause,
                'solution': solution,
                'nouveau_statut_exp': nouveau_statut_exp if nouveau_statut_exp != 'CONTINUE' else None,
            }
            
            success, message = IncidentService.resoudre_incident_complet(
                incident,
                donnees_resolution,
                request.user
            )
            
            if success:
                messages.success(request, f"✅ {message}")
                return redirect('detail_expedition', expedition_id=expedition.id)
            else:
                messages.error(request, f"❌ {message}")
        
        except Exception as e:
            messages.error(request, f"❌ Erreur : {str(e)}")
    
    
    return render(request, 'incidents/resoudre.html', {
        'incident': incident,
        'expedition': expedition,
        'cause_auto': cause_auto,
        'taux': taux,
        'montant_rembourse': montant_rembourse,
        'montant_ttc': montant_ttc,
        'options_statut': options_statut,
        'statut_auto': statut_auto,
    })

@login_required
def assigner_incident(request, incident_id):
    """
    Affecter un agent à un incident
    RÉSERVÉ À L'AGENT RESPONSABLE PRINCIPAL
    """
    if not request.user.is_responsable:
        messages.error(request, "Accès refusé : Seul l'agent responsable peut affecter des incidents")
        return redirect('detail_incident', incident_id=incident_id)
    
    incident = get_object_or_404(Incident, id=incident_id)
    
    if request.method == 'POST':
        agent_id = request.POST.get('agent_responsable')
        
        if agent_id:
            try:
                from django.contrib.auth import get_user_model
                AgentUtilisateur = get_user_model()
                agent = AgentUtilisateur.objects.get(id=agent_id)
                
                ancien_statut = incident.statut
                
                incident.agent_responsable = agent
                incident.statut = 'EN_COURS'
                incident.save()

                Notification.objects.create(
                    type_notification='INCIDENT_AFFECTE',
                    titre=f"Incident affecté - {incident.numero_incident}",
                    message=f"Vous avez été affecté à l'incident {incident.numero_incident} ({incident.get_type_incident_display()}) par {request.user.first_name} {request.user.last_name}",
                    incident=incident,
                    statut='NON_LUE'
                )
                
                HistoriqueIncident.objects.create(
                    incident=incident,
                    action="Affectation",
                    auteur=f"{request.user.first_name} {request.user.last_name}",
                    details=f"Incident affecté à {agent.first_name} {agent.last_name}",
                    ancien_statut=ancien_statut,
                    nouveau_statut='EN_COURS'
                )
                
                messages.success(
                    request,
                    f"Incident affecté à {agent.first_name} {agent.last_name}"
                )
                
                return redirect('detail_incident', incident_id=incident.id)
                
            except Exception as e:
                messages.error(request, f"❌ Erreur : {str(e)}")
        else:
            messages.error(request, "❌ Veuillez sélectionner un agent")
    
    from django.contrib.auth import get_user_model
    AgentUtilisateur = get_user_model()
    agents = AgentUtilisateur.objects.all()
    
    return render(request, 'incidents/assigner.html', {
        'incident': incident,
        'agents': agents,
    })

@login_required
def cloturer_incident(request, incident_id):
    """
    Clôture définitive d'un incident (doit être RESOLU avant)
    """
    incident = get_object_or_404(Incident, id=incident_id)
    if not request.user.is_responsable:
        messages.error(request, "Accès refusé : Seul l'agent responsable peut cloturer cet incident")
        return redirect('detail_incident', incident_id=incident_id)
    
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

@login_required
def supprimer_incident(request, incident_id):
    """
    Suppression d'un incident (avec confirmation)
    """
    incident = get_object_or_404(Incident, id=incident_id)
    if not request.user.is_responsable:
        messages.error(request, "Accès refusé : Seul l'agent responsable peut supprimer des incidents")
        return redirect('detail_incident', incident_id=incident_id)
    
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

@login_required
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

@login_required
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

@login_required
def liste_reclamations(request):
    """
    Liste avec recherche et filtres
    """
    reclamations = Reclamation.objects.all().select_related('client', 'facture')
    
    search = request.GET.get('search', '')
    if search:
        reclamations = reclamations.filter(
            Q(numero_reclamation__icontains=search) |
            Q(objet__icontains=search) |
            Q(description__icontains=search) |
            Q(client__nom__icontains=search) |
            Q(client__prenom__icontains=search)
        )
    
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
    
    stats = {
        'total': reclamations.count(),
        'ouvertes': Reclamation.objects.filter(statut='OUVERTE').count(),
        'en_cours': Reclamation.objects.filter(statut='EN_COURS').count(),
        'resolues': Reclamation.objects.filter(statut='RESOLUE').count(),
        'closes': Reclamation.objects.filter(statut='CLOSE').count(),
        'urgentes': Reclamation.objects.filter(priorite='URGENTE').count(),
        'avec_compensation': Reclamation.objects.filter(compensation_accordee=True).count(),
    }
    
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

@login_required
def detail_reclamation(request, reclamation_id):
    """
    Affiche tous les détails + historique
    """
    reclamation = get_object_or_404(
        Reclamation.objects.select_related('client', 'facture').prefetch_related('expeditions'),
        id=reclamation_id
    )
    
    historique = reclamation.historique.all().order_by('-date_action')
    
    return render(request, 'reclamations/detail.html', {
        'reclamation': reclamation,
        'historique': historique,
    })

@login_required
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

                if not reclamation.signale_par:
                    reclamation.signale_par = request.user

                reclamation.save()
            
                
                messages.success(
                    request,
                    f"Réclamation {reclamation.numero_reclamation} créée avec succès ! "
                    f"Email envoyé au support."
                )
                from django.contrib.auth import get_user_model
                AgentUtilisateur = get_user_model()
                agent_responsable_principal = AgentUtilisateur.objects.filter(
                    is_responsable=True
                ).first()
                    
                if agent_responsable_principal:
                    Notification.objects.create(
                        type_notification='RECLAMATION_CREEE',
                        titre=f"Nouvel reclamation - {reclamation.numero_reclamation}",
                        message=f"Nouvel reclamation {reclamation.get_type_reclamation_display()} créé par {reclamation.signale_par.first_name} {reclamation.signale_par.last_name}",
                        reclamation=reclamation,
                        statut='NON_LUE'
                    )

            
                    HistoriqueReclamation.objects.create(
                        reclamation=reclamation,
                        action="Création",
                        auteur=f"{request.user.first_name} {request.user.last_name}",
                        details=f"Reclamation signalé - En attente d'affectation",
                        ancien_statut=None,
                        nouveau_statut='SIGNALE'
                    )
                    
                    messages.success(
                        request,
                        f"Reclamation {reclamation.numero_reclamation} créé par {request.user.username}. "
                        f"En attente d'affectation."
                    )

                return redirect('detail_reclamation', reclamation_id=reclamation.id)
                
            except Exception as e:
                messages.error(request, f"❌ Erreur : {str(e)}")
    else:
        form = ReclamationForm()
    
    return render(request, 'reclamations/creer.html', {
        'form': form,
    })

@login_required
def modifier_reclamation(request, reclamation_id):
    """
    Modification d'une réclamation existante
    """
    reclamation = get_object_or_404(Reclamation, id=reclamation_id)
    if reclamation.agent_responsable != request.user and not request.user.is_responsable:
        messages.error(
            request,
            "❌ Accès refusé : Seul l'agent affecté ou le responsable principal peut modifier cette réclamation"
        )
        return redirect('detail_reclamation', reclamation_id=reclamation.id)
    
    
    if request.method == 'POST':
        form = ReclamationModificationForm(request.POST, instance=reclamation)
        
        if form.is_valid():
            try:
                reclamation = form.save()
                messages.success(request, f"Réclamation {reclamation.numero_reclamation} modifiée !")
                return redirect('detail_reclamation', reclamation_id=reclamation.id)
            except Exception as e:
                messages.error(request, f"❌ Erreur : {str(e)}")
    else:
        form = ReclamationModificationForm(instance=reclamation)
    
    return render(request, 'reclamations/modifier.html', {
        'form': form,
        'reclamation': reclamation,
    })

@login_required
def assigner_reclamation(request,reclamation_id):
    """
    Affecter un agent à une réclamation
    RÉSERVÉ À L'AGENT RESPONSABLE PRINCIPAL
    """
    if not request.user.is_responsable:
        messages.error(request, "Accès refusé : Seul l'agent responsable peut affecter des réclamations")
        return redirect('detail_reclamation', reclamation_id=reclamation_id)
    
    reclamation = get_object_or_404(Reclamation, id=reclamation_id)
    
    if request.method == 'POST':
        agent_id = request.POST.get('agent_responsable')
        
        if agent_id:
            try:
                from django.contrib.auth import get_user_model
                AgentUtilisateur = get_user_model()
                agent = AgentUtilisateur.objects.get(id=agent_id)
                
                ancien_statut = reclamation.statut
                
                # Affecter l'agent
                reclamation.agent_responsable = agent
                reclamation.statut = 'EN_COURS'
                reclamation.save()

                Notification.objects.create(
                    type_notification='RECLAMATION_AFFECTEE',
                    titre=f"Reclamation affecté - {reclamation.numero_reclamation}",
                    message=f"Vous avez été affecté à la reclamation {reclamation.numero_reclamation} ({reclamation.get_type_reclamation_display()}) par {request.user.first_name} {request.user.last_name}",
                    reclamation=reclamation,
                    statut='NON_LUE'
                )
                
                HistoriqueReclamation.objects.create(
                    reclamation=reclamation,
                    action="Affectation",
                    auteur=f"{request.user.first_name} {request.user.last_name}",
                    details=f"Reclamation affecté à {agent.first_name} {agent.last_name}",
                    ancien_statut=ancien_statut,
                    nouveau_statut='EN_COURS'
                )
                
                messages.success(
                    request,
                    f"Réclamation affectée à {agent.first_name} {agent.last_name}"
                )
                return redirect('detail_reclamation', reclamation_id=reclamation.id)
                
            except Exception as e:
                messages.error(request, f"❌ Erreur : {str(e)}")
        else:
            messages.error(request, "Veuillez sélectionner un agent")
    
    from django.contrib.auth import get_user_model
    AgentUtilisateur = get_user_model()
    agents = AgentUtilisateur.objects.all()
    
    return render(request, 'reclamations/assigner.html', {
        'reclamation': reclamation,
        'agents': agents,
    })

@login_required
def repondre_reclamation(request, reclamation_id):
    """
    Enregistrer une réponse à la réclamation
    """
    reclamation = get_object_or_404(Reclamation, id=reclamation_id)
    
    if request.method == 'POST':
        form = ReclamationReponseForm(request.POST)

        if reclamation.agent_responsable != request.user and not request.user.is_responsable:
            messages.error(
                request,
                "Accès refusé : Seul l'agent affecté ou le responsable principal peut répondre à cette réclamation"
            )
            return redirect('detail_reclamation', reclamation_id=reclamation.id)
    
        
        if form.is_valid():
            try:
                reponse = form.cleaned_data['reponse']
                solution = form.cleaned_data['solution']
                agent = form.cleaned_data['agent']
                
                ReclamationService.repondre_reclamation(reclamation, reponse, solution, agent)

                
                messages.success(
                    request,
                    f"Réponse enregistrée ! Email envoyé au client."
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

@login_required
def resoudre_reclamation(request, reclamation_id):
    """
    Marquer une réclamation comme résolue avec compensation éventuelle
    """
    reclamation = get_object_or_404(Reclamation, id=reclamation_id)
    if reclamation.agent_responsable != request.user and not request.user.is_responsable:
        messages.error(
            request,
            "Accès refusé : Seul l'agent affecté ou le responsable principal peut résoudre cette réclamation"
        )
        return redirect('detail_reclamation', reclamation_id=reclamation.id)
    
    if request.method == 'POST':
        form = ReclamationResolutionForm(request.POST)
        
        if form.is_valid():
            try:
                agent = form.cleaned_data['agent']
                accorder_compensation = form.cleaned_data['accorder_compensation']
                montant_compensation = form.cleaned_data['montant_compensation'] or 0
                
                ReclamationService.resoudre_reclamation(
                    reclamation,
                    agent,
                    accorder_compensation,
                    montant_compensation
                )
                
                msg = f"Réclamation {reclamation.numero_reclamation} résolue !"
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

@login_required
def cloturer_reclamation(request, reclamation_id):
    """
    Clôture définitive d'une réclamation (doit être RESOLUE avant)
    """
    reclamation = get_object_or_404(Reclamation, id=reclamation_id)
    if not request.user.is_responsable:
        messages.error(
            request,
            "Accès refusé : Seul le responsable principal peut clôturer une réclamation"
        )
        return redirect('detail_reclamation', reclamation_id=reclamation.id)
    
    if request.method == 'POST':
        try:
            agent = request.POST.get('agent', 'Agent')
            ReclamationService.cloturer_reclamation(reclamation, agent)
            
            messages.success(request, f"Réclamation {reclamation.numero_reclamation} clôturée !")
            return redirect('liste_reclamations')
            
        except ValidationError as e:
            messages.error(request, str(e))
            return redirect('detail_reclamation', reclamation_id=reclamation.id)
    
    return render(request, 'reclamations/cloturer.html', {
        'reclamation': reclamation,
    })

@login_required
def annuler_reclamation(request, reclamation_id):
    """
    Annuler une réclamation (demande infondée, doublon, etc.)
    """
    reclamation = get_object_or_404(Reclamation, id=reclamation_id)
    if not request.user.is_responsable:
        messages.error(
            request,
            "Accès refusé : Seul le responsable principal peut annuler une réclamation"
        )
        return redirect('detail_reclamation', reclamation_id=reclamation.id)
    
    
    if request.method == 'POST':
        try:
            motif = request.POST.get('motif', '')
            agent = request.POST.get('agent', 'Agent')
            
            if not motif:
                messages.error(request, "Le motif d'annulation est obligatoire")
                return redirect('detail_reclamation', reclamation_id=reclamation.id)
            
            ReclamationService.annuler_reclamation(reclamation, motif, agent)
            
            messages.success(request, f"Réclamation {reclamation.numero_reclamation} annulée !")
            return redirect('liste_reclamations')
            
        except Exception as e:
            messages.error(request, f"❌ Erreur : {str(e)}")
            return redirect('detail_reclamation', reclamation_id=reclamation.id)
    
    return render(request, 'reclamations/annuler.html', {
        'reclamation': reclamation,
    })

@login_required
def supprimer_reclamation(request, reclamation_id):
    """
    Suppression d'une réclamation (avec confirmation)
    """
    reclamation = get_object_or_404(Reclamation, id=reclamation_id)
    if not request.user.is_responsable:
        messages.error(
            request,
            "❌ Accès refusé : Seul le responsable principal peut supprimer une réclamation"
        )
        return redirect('detail_reclamation', reclamation_id=reclamation.id)
    
    if request.method == 'POST':
        try:
            numero = reclamation.numero_reclamation
            reclamation.delete()
            messages.success(request, f"Réclamation {numero} supprimée !")
            return redirect('liste_reclamations')
            
        except Exception as e:
            messages.error(request, f"❌ Erreur : {str(e)}")
            return redirect('detail_reclamation', reclamation_id=reclamation_id)
    
    return render(request, 'reclamations/supprimer.html', {
        'reclamation': reclamation,
    })

@login_required
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

@login_required
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

@login_required
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
    
    favoris_ids = request.session.get('favoris', FAVORIS_PAR_DEFAUT)
    favoris = [
        f for f in FONCTIONNALITES_DISPONIBLES 
        if f['id'] in favoris_ids
    ][:4]
    
    notifications = Notification.objects.filter(
        statut='NON_LUE'
    ).order_by('-date_creation')
    
    from django.db.models import Q

    if request.user.is_responsable:
        reclamations_non_terminees = Reclamation.objects.exclude(
            statut__in=['ANNULE', 'CLOTURE', 'RESOLUE']
        ).order_by('-date_creation')[:5]
        
        incidents_non_termines = Incident.objects.exclude(
            statut__in=['ANNULE', 'CLOTURE', 'RESOLUE']
        ).order_by('-date_creation')[:5]
    else:
        reclamations_non_terminees = Reclamation.objects.exclude(
            statut__in=['ANNULE', 'CLOSE', 'RESOLUE']
        ).order_by('-date_creation')[:5]
        
        incidents_non_termines = Incident.objects.exclude(
            statut__in=['ANNULE', 'CLOS', 'RESOLUE']
        ).order_by('-date_creation')[:5]
        
    tournees_en_cours = Tournee.objects.filter(
        statut='EN_COURS'
    ).select_related('chauffeur', 'vehicule').annotate(
        nb_expeditions=Count('expeditions')
    ).order_by('date_depart')
    
    demain = date.today() + timedelta(days=1)
    tournees_demain = Tournee.objects.filter(
        statut='PREVUE',
        date_depart__date=demain
    ).select_related('chauffeur', 'vehicule').annotate(
        nb_expeditions=Count('expeditions')
    ).order_by('date_depart')
    
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
        "reclamations_non_terminees": reclamations_non_terminees,
        "incidents_non_termines": incidents_non_termines,
    }
    
    return render(request, 'home.html', context)

@login_required
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
            messages.error(request, 'Vous ne pouvez sélectionner que 4 favoris maximum !')
            return redirect('selectionner_favoris')
        
        if len(favoris_selectionnes) == 0:
            messages.error(request, 'Veuillez sélectionner au moins 1 favori !')
            return redirect('selectionner_favoris')
        
        # Enregistrer en session
        request.session['favoris'] = favoris_selectionnes
        
        messages.success(request, f'Vos {len(favoris_selectionnes)} favoris ont été enregistrés !')
        return redirect('home')

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

@login_required
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

                if 'redirect' in resultat:
                    return redirect(resultat['redirect'])
                
                return redirect('home')
            else:
                messages.error(request, resultat['message'])
                
        except Exception as e:
            messages.error(request, f"❌ Erreur : {str(e)}")
        
        return redirect('home')
    
    return render(request, 'notifications/traiter.html', {
        'notification': notification,
    })

@login_required
def liste_notifications(request):
    """
    Liste de toutes les notifications
    """
    notifications = Notification.objects.all().order_by('-date_creation')
    
    return render(request, 'notifications/liste.html', {
        'notifications': notifications,
    })

def login_view(request):
    """Page de connexion"""
    if request.user.is_authenticated:
        return redirect('home')
    
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            
            if user is not None:
                login(request, user)
                messages.success(request, f"Bienvenue {user.first_name} {user.last_name} !")
                return redirect('home')
        else:
            messages.error(request, "❌ Nom d'utilisateur ou mot de passe incorrect")
    else:
        form = LoginForm()
    
    return render(request, 'auth/login.html', {'form': form})

@login_required
def logout_view(request):
    """Déconnexion"""
    logout(request)
    messages.success(request, "Vous avez été déconnecté avec succès")
    return redirect('login')

@login_required
def ajouter_agent(request):
    """Ajouter un nouvel agent (réservé au responsable)"""
    if not request.user.is_responsable:
        messages.error(request, "Accès refusé : réservé à l'agent responsable")
        return redirect('home')
    
    if request.method == 'POST':
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        email = request.POST.get('email')
        telephone = request.POST.get('telephone')
        
        if not all([first_name, last_name, email, telephone]):
            messages.error(request, "❌ Tous les champs sont requis")
            return render(request, 'auth/ajouter_agent.html')
        
        # Générer username et password
        from .models import AgentUtilisateur
        username = AgentUtilisateur.generer_username(first_name, last_name)
        mot_de_passe = AgentUtilisateur.generer_mot_de_passe_securise()
        
        agent = AgentUtilisateur(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            telephone=telephone,
            is_staff=False,
            is_responsable=False
        )
        agent.set_password(mot_de_passe)
        agent.save()
        
        return render(request, 'auth/agent_cree.html', {
            'agent': agent,
            'username': username,
            'mot_de_passe': mot_de_passe,
        })
    
    return render(request, 'auth/ajouter_agent.html')

@login_required
def liste_agents(request):
    """Liste de tous les agents (réservé au responsable)"""
    if not request.user.is_responsable:
        messages.error(request, "Accès refusé : réservé à l'agent responsable")
        return redirect('home')
    
    agents = AgentUtilisateur.objects.all().order_by('-date_creation')
    
    return render(request, 'auth/liste_agents.html', {'agents': agents})

@login_required
def changer_mot_de_passe(request):
    """Changer son mot de passe"""
    if request.method == 'POST':
        form = ChangerMotDePasseForm(request.POST)
        
        if form.is_valid():
            ancien = form.cleaned_data.get('ancien_mot_de_passe')
            nouveau = form.cleaned_data.get('nouveau_mot_de_passe')
            
            if not request.user.check_password(ancien):
                messages.error(request, "Mot de passe actuel incorrect")
            else:
                # Changer le mot de passe
                request.user.set_password(nouveau)
                request.user.save()
                
                login(request, request.user)
                
                messages.success(request, "Mot de passe modifié avec succès !")
                return redirect('home')
    else:
        form = ChangerMotDePasseForm()
    
    return render(request, 'auth/changer_mot_de_passe.html', {'form': form})

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from datetime import datetime, timedelta
from .services.analytics_service import AnalyticsService
from .services.stats_service import StatsService
from .models import Expedition, Tournee, Facture, Client, Chauffeur, Incident, Paiement

analytics = AnalyticsService(Expedition, Tournee, Facture, Client, Chauffeur, Incident)
stats = StatsService(Expedition, Tournee, Facture, Paiement)

@login_required
def dashboard_analytics(request):
    """Vue principale du tableau de bord d'analyse"""
    context = {
        'page_title': 'Analyse et Tableaux de Bord',
        'section': 'analytics'
    }
    return render(request, 'analytics/dashboard.html', context)

@login_required
def analyse_commerciale(request):
    """Page d'analyse commerciale"""
    period_type = request.GET.get('period', 'year') 
    year = request.GET.get('year', datetime.now().year)
    
    try:
        year = int(year)
    except ValueError:
        year = datetime.now().year
    
    if period_type == 'year':
        start_date = datetime(year, 1, 1)
        end_date = datetime(year, 12, 31, 23, 59, 59)
    else:
        start_date = datetime(year - 2, 1, 1)
        end_date = datetime(year, 12, 31, 23, 59, 59)
    
    context = {
        'page_title': 'Analyse Commerciale',
        'section': 'analytics',
        'subsection': 'commercial',
        'year': year,
        'period_type': period_type
    }
    
    return render(request, 'analytics/commercial.html', context)

@login_required
def analyse_operationnelle(request):
    """Page d'analyse opérationnelle"""
    period_type = request.GET.get('period', 'year')
    year = request.GET.get('year', datetime.now().year)
    
    try:
        year = int(year)
    except ValueError:
        year = datetime.now().year
    
    context = {
        'page_title': 'Analyse Opérationnelle',
        'section': 'analytics',
        'subsection': 'operational',
        'year': year,
        'period_type': period_type
    }
    
    return render(request, 'analytics/operational.html', context)

@login_required
def api_evolution_expeditions(request):
    """API: Évolution des expéditions"""
    period = request.GET.get('period', 'month') 
    year = int(request.GET.get('year', datetime.now().year))
    
    if period == 'month':
        start_date = datetime(year, 1, 1)
        end_date = datetime(year, 12, 31, 23, 59, 59)
    else:
        years = int(request.GET.get('years', 3))
        start_date = datetime(year - years + 1, 1, 1)
        end_date = datetime(year, 12, 31, 23, 59, 59)
    
    data = analytics.get_expeditions_evolution(start_date, end_date, period)
    
    return JsonResponse({
        'success': True,
        'data': data,
        'period': period
    })

@login_required
def api_chiffre_affaires(request):
    """API: Évolution du chiffre d'affaires"""
    period = request.GET.get('period', 'month')
    year = int(request.GET.get('year', datetime.now().year))
    
    if period == 'month':
        start_date = datetime(year, 1, 1)
        end_date = datetime(year, 12, 31, 23, 59, 59)
    else:
        years = int(request.GET.get('years', 3))
        start_date = datetime(year - years + 1, 1, 1)
        end_date = datetime(year, 12, 31, 23, 59, 59)
    
    data = analytics.get_chiffre_affaires_evolution(start_date, end_date, period)
    
    return JsonResponse({
        'success': True,
        'data': data
    })

@login_required
def api_top_clients(request):
    """API: Top clients"""
    year = int(request.GET.get('year', datetime.now().year))
    by = request.GET.get('by', 'volume') 
    limit = int(request.GET.get('limit', 10))
    
    start_date = datetime(year, 1, 1)
    end_date = datetime(year, 12, 31, 23, 59, 59)
    
    data = analytics.get_top_clients(start_date, end_date, limit, by)
    
    return JsonResponse({
        'success': True,
        'data': data,
        'criteria': by
    })

@login_required
def api_destinations_populaires(request):
    """API: Destinations les plus sollicitées"""
    year = int(request.GET.get('year', datetime.now().year))
    limit = int(request.GET.get('limit', 10))
    
    start_date = datetime(year, 1, 1)
    end_date = datetime(year, 12, 31, 23, 59, 59)
    
    data = analytics.get_destinations_populaires(start_date, end_date, limit)
    
    return JsonResponse({
        'success': True,
        'data': data
    })

@login_required
def api_services_performance(request):
    """API: Performance par type de service"""
    year = int(request.GET.get('year', datetime.now().year))
    
    start_date = datetime(year, 1, 1)
    end_date = datetime(year, 12, 31, 23, 59, 59)
    
    data = analytics.get_services_performance(start_date, end_date)
    
    return JsonResponse({
        'success': True,
        'data': data
    })

@login_required
def api_evolution_tournees(request):
    """API: Évolution des tournées"""
    period = request.GET.get('period', 'month')
    year = int(request.GET.get('year', datetime.now().year))
    
    if period == 'month':
        start_date = datetime(year, 1, 1)
        end_date = datetime(year, 12, 31, 23, 59, 59)
    else:
        years = int(request.GET.get('years', 3))
        start_date = datetime(year - years + 1, 1, 1)
        end_date = datetime(year, 12, 31, 23, 59, 59)
    
    data = analytics.get_tournees_evolution(start_date, end_date, period)
    
    return JsonResponse({
        'success': True,
        'data': data
    })

@login_required
def api_taux_reussite(request):
    """API: Taux de réussite des livraisons"""
    year = int(request.GET.get('year', datetime.now().year))
    
    start_date = datetime(year, 1, 1)
    end_date = datetime(year, 12, 31, 23, 59, 59)
    
    data = analytics.get_taux_reussite_livraisons(start_date, end_date)
    
    return JsonResponse({
        'success': True,
        'data': data
    })

@login_required
def api_top_chauffeurs(request):
    """API: Top chauffeurs"""
    year = int(request.GET.get('year', datetime.now().year))
    limit = int(request.GET.get('limit', 10))
    
    start_date = datetime(year, 1, 1)
    end_date = datetime(year, 12, 31, 23, 59, 59)
    
    data = analytics.get_top_chauffeurs(start_date, end_date, limit)
    
    return JsonResponse({
        'success': True,
        'data': data
    })

@login_required
def api_zones_incidents(request):
    """API: Zones avec le plus d'incidents"""
    year = int(request.GET.get('year', datetime.now().year))
    limit = int(request.GET.get('limit', 10))
    
    start_date = datetime(year, 1, 1)
    end_date = datetime(year, 12, 31, 23, 59, 59)
    
    data = analytics.get_zones_incidents(start_date, end_date, limit)
    
    return JsonResponse({
        'success': True,
        'data': data
    })

@login_required
def api_periodes_activite(request):
    """API: Périodes de forte activité"""
    year = int(request.GET.get('year', datetime.now().year))
    
    start_date = datetime(year, 1, 1)
    end_date = datetime(year, 12, 31, 23, 59, 59)
    
    data = analytics.get_periodes_forte_activite(start_date, end_date)
    
    return JsonResponse({
        'success': True,
        'data': data
    })

@login_required
def api_kpi_dashboard(request):
    """API: KPI pour le tableau de bord principal"""
    year = int(request.GET.get('year', datetime.now().year))
    
    start_date = datetime(year, 1, 1)
    end_date = datetime(year, 12, 31, 23, 59, 59)
    
    kpi_data = analytics.get_kpi_dashboard(start_date, end_date)
    kpis = stats.calculate_kpis(start_date, end_date)
    taux = analytics.get_taux_reussite_livraisons(start_date, end_date)
    
    return JsonResponse({
        'success': True,
        'data': {
            'global': kpi_data,
            'performance': kpis,
            'livraisons': taux
        }
    })

@login_required
def api_comparison_years(request):
    """API: Comparaison entre deux années"""
    year1 = int(request.GET.get('year1', datetime.now().year - 1))
    year2 = int(request.GET.get('year2', datetime.now().year))
    
    data = stats.compare_years(year1, year2)
    
    return JsonResponse({
        'success': True,
        'data': data
    })

@login_required
def api_rentabilite_service(request):
    """API: Rentabilité par type de service"""
    year = int(request.GET.get('year', datetime.now().year))
    
    start_date = datetime(year, 1, 1)
    end_date = datetime(year, 12, 31, 23, 59, 59)
    
    data = stats.get_rentabilite_par_service(start_date, end_date)
    
    return JsonResponse({
        'success': True,
        'data': data
    })

@login_required
def api_monthly_summary(request):
    """API: Résumé mensuel"""
    year = int(request.GET.get('year', datetime.now().year))
    month = int(request.GET.get('month', datetime.now().month))
    
    data = stats.get_monthly_summary(year, month)
    
    return JsonResponse({
        'success': True,
        'data': data
    })

@login_required
def export_report(request):
    """Exporter un rapport en PDF"""
    
    report_type = request.GET.get('type', 'commercial')
    year = int(request.GET.get('year', datetime.now().year))
    
    # TODO: Implémenter la génération de PDF
    
    return JsonResponse({
        'success': False,
        'message': 'Fonctionnalité en développement'
    })

@login_required
def supprimer_agent(request, pk):
    """Supprimer un agent"""
    if request.method == 'POST':
        try:
            agent = AgentUtilisateur.objects.get(pk=pk)
            
            # Empêcher la suppression de soi-même
            if agent == request.user:
                messages.error(request, "❌ Vous ne pouvez pas supprimer votre propre compte.")
                return redirect('liste_agents')
            
            nom_complet = f"{agent.first_name} {agent.last_name}"
            agent.delete()
            messages.success(request, f" L'agent {nom_complet} a été supprimé avec succès.")
            
        except AgentUtilisateur.DoesNotExist:
            messages.error(request, "❌ Agent introuvable.")
        except Exception as e:
            messages.error(request, f"❌ Erreur lors de la suppression : {str(e)}")
    
    return redirect('liste_agents')
