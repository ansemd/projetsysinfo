from django import forms
from .models import Client, Chauffeur, Vehicule, TypeService, Destination, Tarification, Tournee, Expedition, TrackingExpedition, Facture, Paiement, Incident, Reclamation, AgentUtilisateur
from datetime import date
from django import forms
from django.contrib.auth.forms import AuthenticationForm

class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = '__all__'  
        widgets = {
            'date_naissance': forms.DateInput(attrs={'type': 'date'}),
            'remarques': forms.Textarea(attrs={'rows': 3}),
        }    

class ChauffeurForm(forms.ModelForm):
    class Meta:
        model = Chauffeur
        fields = '__all__'
        widgets = {
            'date_naissance': forms.DateInput(attrs={'type': 'date'}),
            'date_obtention_permis': forms.DateInput(attrs={'type': 'date'}),
            'date_expiration_permis': forms.DateInput(attrs={'type': 'date'}),
            'date_embauche': forms.DateInput(attrs={'type': 'date'}),
            'remarques': forms.Textarea(attrs={'rows': 3}),
        }
    
    def clean(self):
        # Garder SEULEMENT la validation des dates de permis
        cleaned_data = super().clean()
        date_obtention = cleaned_data.get('date_obtention_permis')
        date_expiration = cleaned_data.get('date_expiration_permis')
        
        if date_obtention and date_expiration:
            if date_obtention >= date_expiration:
                raise forms.ValidationError(
                    "La date d'obtention du permis doit être antérieure à la date d'expiration."
                )
        
        return cleaned_data
    
class VehiculeForm(forms.ModelForm):
    """
    Formulaire pour créer/modifier un véhicule
    
    IMPORTANT : 
    - À la CRÉATION : date_prochaine_revision est exclue (calculée auto)
    - À la MODIFICATION : date_prochaine_revision est en readonly
    """
    class Meta:
        model = Vehicule
        fields = [
            'numero_immatriculation', 'marque', 'modele', 'annee',
            'type_vehicule', 'capacite_poids', 'capacite_volume',
            'consommation_moyenne', 'etat', 'statut', 'kilometrage',
            'date_derniere_revision', 'date_acquisition', 'remarques'
        ]
        widgets = {
            'date_derniere_revision': forms.DateInput(attrs={'type': 'date'}),
            'date_acquisition': forms.DateInput(attrs={'type': 'date'}),
            'remarques': forms.Textarea(attrs={'rows': 3}),
        }
    
    def clean_capacite_poids(self):
        """Validation capacité poids"""
        capacite = self.cleaned_data.get('capacite_poids')
        if capacite and capacite <= 0:
            raise forms.ValidationError("La capacité doit être supérieure à 0")
        return capacite
    
    def clean_kilometrage(self):
        """Validation kilométrage"""
        km = self.cleaned_data.get('kilometrage')
        if km and km < 0:
            raise forms.ValidationError("Le kilométrage ne peut pas être négatif")
        return km

class TypeServiceForm(forms.ModelForm):
    """
    Formulaire pour créer/modifier un type de service
    """
    class Meta:
        model = TypeService
        fields = ['type_service', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }
    
    def clean_type_service(self):
        """Validation du type de service"""
        type_service = self.cleaned_data.get('type_service')
        
        # Vérifier que le type n'existe pas déjà (seulement à la création)
        if not self.instance.pk:
            if TypeService.objects.filter(type_service=type_service).exists():
                raise forms.ValidationError("Ce type de service existe déjà")
        
        return type_service
    
class DestinationForm(forms.ModelForm):
    """
    Formulaire pour créer/modifier une destination
    """
    class Meta:
        model = Destination
        fields = [
            'ville', 'wilaya', 'pays', 'zone_geographique', 'zone_logistique',
            'distance_estimee', 'tarif_base', 'delai_livraison_estime',
            'code_postal', 'remarques'
        ]
        widgets = {
            'remarques': forms.Textarea(attrs={'rows': 3}),
        }
    
    def clean_distance_estimee(self):
        """Validation distance"""
        distance = self.cleaned_data.get('distance_estimee')
        if distance and distance < 0:
            raise forms.ValidationError("La distance ne peut pas être négative")
        return distance
    
    def clean_tarif_base(self):
        """Validation tarif base"""
        tarif = self.cleaned_data.get('tarif_base')
        if tarif and tarif < 0:
            raise forms.ValidationError("Le tarif ne peut pas être négatif")
        return tarif

class TarificationForm(forms.ModelForm):
    """
    Formulaire pour créer/modifier une tarification
    """
    class Meta:
        model = Tarification
        fields = ['destination', 'type_service', 'tarif_poids', 'tarif_volume']
    
    def clean_tarif_poids(self):
        """Validation tarif poids"""
        tarif = self.cleaned_data.get('tarif_poids')
        if tarif and tarif < 0:
            raise forms.ValidationError("Le tarif ne peut pas être négatif")
        return tarif
    
    def clean_tarif_volume(self):
        """Validation tarif volume"""
        tarif = self.cleaned_data.get('tarif_volume')
        if tarif and tarif < 0:
            raise forms.ValidationError("Le tarif ne peut pas être négatif")
        return tarif

class TourneeForm(forms.ModelForm):
    """
    Formulaire de création/modification de tournée
    
    FILTRES INTELLIGENTS :
    - Chauffeurs DISPONIBLES uniquement
    - Véhicules DISPONIBLES uniquement
    - Date départ >= aujourd'hui
    """
    
    class Meta:
        model = Tournee
        fields = [
            'chauffeur',
            'vehicule', 
            'date_depart',
            'date_retour_prevue',
            'zone_cible',
            'est_privee',
            'remarques'
        ]
        widgets = {
            'date_depart': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'date_retour_prevue': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'remarques': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filtrer chauffeurs DISPONIBLES uniquement
        self.fields['chauffeur'].queryset = Chauffeur.objects.filter(
            statut_disponibilite='DISPONIBLE'
        )
        
        # Filtrer véhicules DISPONIBLES uniquement
        self.fields['vehicule'].queryset = Vehicule.objects.filter(
            statut='DISPONIBLE'
        )
        
        # Labels personnalisés
        self.fields['chauffeur'].label = "Chauffeur *"
        self.fields['vehicule'].label = "Véhicule *"
        self.fields['date_depart'].label = "Date et heure de départ *"
        self.fields['date_retour_prevue'].label = "Date et heure de retour prévue"
        self.fields['zone_cible'].label = "Zone cible *"
        self.fields['est_privee'].label = "Tournée privée (EXPRESS)"
        
        # Aide
        self.fields['date_retour_prevue'].help_text = "Laissez vide pour calcul automatique"
    
    def clean_date_depart(self):
        """
        Validation : Date départ >= aujourd'hui
        """
        date_depart = self.cleaned_data.get('date_depart')
        
        if date_depart:
            from django.utils import timezone
            
            if date_depart < timezone.now():
                raise forms.ValidationError(
                    "La date de départ doit être supérieure ou égale à aujourd'hui"
                )
        
        return date_depart
    
    def clean(self):
        """
        Validations globales
        """
        cleaned_data = super().clean()
        date_depart = cleaned_data.get('date_depart')
        date_retour_prevue = cleaned_data.get('date_retour_prevue')
        
        # Si date retour fournie, vérifier qu'elle est après date départ
        if date_depart and date_retour_prevue:
            if date_retour_prevue <= date_depart:
                raise forms.ValidationError({
                    'date_retour_prevue': "La date de retour doit être après la date de départ"
                })
        
        return cleaned_data

class ExpeditionForm(forms.ModelForm):
    """
    Formulaire de création d'expédition
    """
    
    class Meta:
        model = Expedition
        fields = [
            'client',
            'destination',
            'type_service',
            'tournee',
            'nom_destinataire',
            'telephone_destinataire',
            'email_destinataire',
            'adresse_destinataire',
            'poids',
            'volume',
            'description',
            'remarques',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'remarques': forms.Textarea(attrs={'rows': 2}),
            'adresse_destinataire': forms.Textarea(attrs={'rows': 2}),
        }
    
    def __init__(self, *args, **kwargs):
        
        super().__init__(*args, **kwargs)
        
        # Afficher SEULEMENT les tournées PREVUES
        tournees = Tournee.objects.filter(statut='PREVUE').select_related(
            'chauffeur', 'vehicule'
        ).order_by('date_depart')
        
        self.fields['tournee'].queryset = tournees
        self.fields['tournee'].required = False
        
        # Personnaliser l'affichage des tournées dans le select
        self.fields['tournee'].label_from_instance = lambda obj: (
            f"{obj.get_numero_tournee()} - {obj.chauffeur.prenom} {obj.chauffeur.nom} - "
            f"{obj.vehicule.numero_immatriculation} - {obj.date_depart.strftime('%d/%m/%Y %H:%M')}"
        )
        
        # Labels
        self.fields['client'].label = "Client *"
        self.fields['destination'].label = "Destination *"
        self.fields['type_service'].label = "Type de service *"
        self.fields['tournee'].label = "Tournée (optionnel - sera affectée automatiquement si non choisie)"
        self.fields['poids'].label = "Poids (kg) *"
        self.fields['volume'].label = "Volume (m³)"
        
        # Aides
        self.fields['tournee'].help_text = (
            "Laissez vide pour affectation automatique selon le type de service et la destination"
        )
    
    def clean_poids(self):
        poids = self.cleaned_data.get('poids')
        if poids and poids <= 0:
            raise forms.ValidationError("Le poids doit être supérieur à 0")
        return poids
    
    def clean_volume(self):
        volume = self.cleaned_data.get('volume')
        if volume and volume < 0:
            raise forms.ValidationError("Le volume ne peut pas être négatif")
        return volume

class FactureForm(forms.ModelForm):
    """
    Formulaire de modification de facture
    Permet de modifier : client, date échéance, statut, remarques
    """
    
    class Meta:
        model = Facture
        fields = ['client', 'date_echeance', 'statut', 'remarques']
        widgets = {
            'date_echeance': forms.DateInput(attrs={'type': 'date'}),
            'remarques': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Personnalisation des labels
        self.fields['client'].label = "Client *"
        self.fields['date_echeance'].label = "Date d'échéance *"
        self.fields['statut'].label = "Statut *"
        self.fields['date_echeance'].help_text = "Date limite de paiement"
    
    def clean_date_echeance(self):
        """
        Validation : Date échéance >= aujourd'hui
        Exception : Si facture déjà EN_RETARD, on garde la date passée
        """
        date_echeance = self.cleaned_data.get('date_echeance')
        
        # Si modification d'une facture existante EN_RETARD
        if self.instance and self.instance.pk:
            if self.instance.statut == 'EN_RETARD':
                return date_echeance  # On autorise la date passée
        
        # Sinon, date doit être >= aujourd'hui
        if date_echeance and date_echeance < date.today():
            raise forms.ValidationError(
                "La date d'échéance doit être supérieure ou égale à aujourd'hui"
            )
        
        return date_echeance

class PaiementForm(forms.ModelForm):
    """
    Formulaire d'enregistrement d'un paiement
    
    2 MODES D'UTILISATION :
    1. Depuis une facture (depuis_facture=True) :
       - Champs facture et client cachés (pré-remplis automatiquement)
       - Utilisé quand l'agent clique "Ajouter paiement" depuis une facture
    
    2. Mode normal (depuis_facture=False) :
       - Formulaire complet avec sélection de la facture
       - Affiche seulement les factures IMPAYEE ou PARTIELLEMENT_PAYEE
    """
    
    class Meta:
        model = Paiement
        fields = ['facture', 'client', 'montant_paye', 'mode_paiement', 
                  'reference_transaction', 'remarques']
        widgets = {
            'remarques': forms.Textarea(attrs={'rows': 2}),
        }
    
    def __init__(self, *args, **kwargs):
        # Récupérer les options spéciales
        depuis_facture = kwargs.pop('depuis_facture', False)  # Vient-on d'une facture ?
        facture_id = kwargs.pop('facture_id', None)           # ID de la facture si oui
        
        super().__init__(*args, **kwargs)
        
        # ========== MODE 1 : DEPUIS UNE FACTURE ==========
        if depuis_facture and facture_id:
            from .models import Facture
            facture = Facture.objects.get(id=facture_id)
            
            # Pré-remplir et CACHER le champ facture
            self.fields['facture'].initial = facture
            self.fields['facture'].widget = forms.HiddenInput()
            
            # Pré-remplir et CACHER le champ client
            self.fields['client'].initial = facture.client
            self.fields['client'].widget = forms.HiddenInput()
            
            # Montant par défaut = montant restant à payer
            self.fields['montant_paye'].initial = facture.montant_ttc
            self.fields['montant_paye'].help_text = f"Montant restant : {facture.montant_ttc:,.2f} DA"
        
        # ========== MODE 2 : FORMULAIRE NORMAL ==========
        else:
            # Filtrer : Afficher SEULEMENT les factures impayées ou partiellement payées
            factures = Facture.objects.filter(
                statut__in=['IMPAYEE', 'PARTIELLEMENT_PAYEE']
            ).select_related('client').order_by('-date_creation')
            
            self.fields['facture'].queryset = factures
            
            # Personnaliser l'affichage dans le select
            # Format : "F-20260104-CL-003-001 - Jean Dupont - 5,000.00 DA - Impayée"
            self.fields['facture'].label_from_instance = lambda obj: (
                f"{obj.numero_facture} - {obj.client.prenom} {obj.client.nom} - "
                f"{obj.montant_ttc:,.2f} DA - {obj.get_statut_display()}"
            )
        
        # Labels communs aux 2 modes
        self.fields['facture'].label = "Facture *"
        self.fields['client'].label = "Client *"
        self.fields['montant_paye'].label = "Montant du paiement (DA) *"
        self.fields['mode_paiement'].label = "Mode de paiement *"
        self.fields['reference_transaction'].label = "Référence de transaction"
    
    def clean_montant_paye(self):
        """Validation : Montant doit être > 0"""
        montant = self.cleaned_data.get('montant_paye')
        
        if montant and montant <= 0:
            raise forms.ValidationError("Le montant doit être supérieur à 0")
        
        return montant
    
    def clean(self):
        """
        Validation globale : Montant ne doit pas dépasser le montant TTC de la facture
        """
        cleaned_data = super().clean()
        montant = cleaned_data.get('montant_paye')
        facture = cleaned_data.get('facture')
        
        if montant and facture:
            if montant > facture.montant_ttc:
                raise forms.ValidationError({
                    'montant_paye': f"Le montant ne peut pas dépasser le montant TTC ({facture.montant_ttc:,.2f} DA)"
                })
        
        return cleaned_data

class IncidentForm(forms.ModelForm):
    """
    Formulaire de création/modification d'incident
    """
    
    class Meta:
        model = Incident
        fields = [
            'type_incident',
            'titre',
            'description',
            'date_heure_incident',
            'lieu_incident',
            'signale_par',
            'cout_estime',
            'expedition',
            'tournee',
            'document1',
            'document2',
            'photo1',
            'photo2',
        ]
        widgets = {
            'date_heure_incident': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'description': forms.Textarea(attrs={'rows': 4}),
            'titre': forms.TextInput(attrs={'size': 60}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Labels
        self.fields['type_incident'].label = "Type d'incident *"
        self.fields['titre'].label = "Titre (résumé court) *"
        self.fields['description'].label = "Description détaillée *"
        self.fields['date_heure_incident'].label = "Date et heure de l'incident *"
        self.fields['lieu_incident'].label = "Lieu de l'incident"
        self.fields['signale_par'].label = "Signalé par (nom) *"
        self.fields['cout_estime'].label = "Coût estimé (DA)"
        self.fields['expedition'].label = "Expédition concernée"
        self.fields['tournee'].label = "Tournée concernée"
        
        # Filtrer les expéditions (seulement celles en cours ou en attente)
        self.fields['expedition'].queryset = Expedition.objects.filter(
            statut__in=['EN_ATTENTE', 'EN_TRANSIT', 'COLIS_CREE', 'EN_LIVRAISON']
        ).order_by('-date_creation')
        
        # Filtrer les tournées (seulement PREVUE ou EN_COURS)
        self.fields['tournee'].queryset = Tournee.objects.filter(
            statut__in=['PREVUE', 'EN_COURS']
        ).order_by('-date_depart')
        
        # Help texts
        self.fields['cout_estime'].help_text = "Coût estimé des dommages en DA"
        self.fields['expedition'].help_text = "Laisser vide si incident lié à une tournée"
        self.fields['tournee'].help_text = "Laisser vide si incident lié à une expédition"
    
    def clean(self):
        """
        Validation : Un incident doit être lié à UNE expédition OU UNE tournée
        (pas les deux, pas aucun)
        """
        cleaned_data = super().clean()
        expedition = cleaned_data.get('expedition')
        tournee = cleaned_data.get('tournee')
        
        # Les deux sont remplis
        if expedition and tournee:
            raise forms.ValidationError(
                "Un incident ne peut être lié qu'à une expédition OU une tournée, pas les deux !"
            )
        
        # Aucun n'est rempli
        if not expedition and not tournee:
            raise forms.ValidationError(
                "Un incident doit être lié soit à une expédition soit à une tournée !"
            )
        
        return cleaned_data
    
    def clean_cout_estime(self):
        """Validation : Coût >= 0"""
        cout = self.cleaned_data.get('cout_estime')
        
        if cout and cout < 0:
            raise forms.ValidationError("Le coût ne peut pas être négatif")
        
        return cout

class IncidentModificationForm(forms.ModelForm):
    """
    Formulaire pour modifier un incident existant
    (champs limités)
    """
    
    class Meta:
        model = Incident
        fields = [
            'titre',
            'description',
            'lieu_incident',
            'cout_estime',
            'severite',
            'statut',
            'agent_responsable',
            'actions_entreprises',
            'remarques',
            'document1',
            'document2',
            'photo1',
            'photo2',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'actions_entreprises': forms.Textarea(attrs={'rows': 3}),
            'remarques': forms.Textarea(attrs={'rows': 2}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.fields['titre'].label = "Titre *"
        self.fields['description'].label = "Description *"
        self.fields['severite'].label = "Sévérité *"
        self.fields['statut'].label = "Statut *"
        self.fields['agent_responsable'].label = "Agent responsable"
        self.fields['actions_entreprises'].label = "Actions entreprises"

class IncidentResolutionForm(forms.Form):
    """
    Formulaire pour résoudre un incident
    """
    solution = forms.CharField(
        label="Solution appliquée *",
        widget=forms.Textarea(attrs={'rows': 4}),
        help_text="Décrivez la solution mise en place pour résoudre cet incident"
    )
    
    agent = forms.CharField(
        label="Agent responsable *",
        max_length=100,
        help_text="Nom de l'agent qui a résolu l'incident"
    )

class ReclamationForm(forms.ModelForm):
    """
    Formulaire de création/modification de réclamation
    """
    
    class Meta:
        model = Reclamation
        fields = [
            'client',
            'type_reclamation',
            'nature',
            'objet',
            'description',
            'expeditions',
            'facture',
            'service_concerne',
            'piece_jointe1',
            'piece_jointe2',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'objet': forms.TextInput(attrs={'size': 60}),
            'expeditions': forms.CheckboxSelectMultiple(),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Labels
        self.fields['client'].label = "Client *"
        self.fields['type_reclamation'].label = "Type de réclamation *"
        self.fields['nature'].label = "Nature *"
        self.fields['objet'].label = "Objet de la réclamation *"
        self.fields['description'].label = "Description détaillée *"
        self.fields['expeditions'].label = "Expéditions concernées"
        self.fields['facture'].label = "Facture concernée"
        self.fields['service_concerne'].label = "Service concerné"
        
        # Filtrer les expéditions
        self.fields['expeditions'].queryset = Expedition.objects.all().order_by('-date_creation')
        
        # Filtrer les factures (sauf annulées)
        self.fields['facture'].queryset = Facture.objects.exclude(
            statut='ANNULEE'
        ).order_by('-date_creation')
        
        # Help texts
        self.fields['expeditions'].help_text = "Sélectionner les expéditions concernées (si applicable)"
        self.fields['service_concerne'].help_text = "Obligatoire si type = SERVICE"
    
    def clean(self):
        """
        Validation : Si type = SERVICE, service_concerne est OBLIGATOIRE
        """
        cleaned_data = super().clean()
        type_reclamation = cleaned_data.get('type_reclamation')
        service_concerne = cleaned_data.get('service_concerne')
        
        # Si type SERVICE mais pas de service spécifié
        if type_reclamation == 'SERVICE' and not service_concerne:
            raise forms.ValidationError({
                'service_concerne': "Le service concerné est obligatoire pour une réclamation de type SERVICE"
            })
        
        # Si type != SERVICE mais service spécifié
        if type_reclamation != 'SERVICE' and service_concerne:
            raise forms.ValidationError({
                'service_concerne': "Le service concerné doit être vide si la réclamation n'est pas de type SERVICE"
            })
        
        return cleaned_data

class ReclamationModificationForm(forms.ModelForm):
    """
    Formulaire pour modifier une réclamation existante
    """
    
    class Meta:
        model = Reclamation
        fields = [
            'objet',
            'description',
            'priorite',
            'statut',
            'agent_responsable',
            'remarques',
            'expeditions',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'remarques': forms.Textarea(attrs={'rows': 2}),
            'expeditions': forms.CheckboxSelectMultiple(),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.fields['objet'].label = "Objet *"
        self.fields['description'].label = "Description *"
        self.fields['priorite'].label = "Priorité *"
        self.fields['statut'].label = "Statut *"
        self.fields['agent_responsable'].label = "Agent responsable"
        
        # Filtrer les expéditions
        self.fields['expeditions'].queryset = Expedition.objects.all().order_by('-date_creation')

class ReclamationReponseForm(forms.Form):
    """
    Formulaire pour répondre à une réclamation
    """
    reponse = forms.CharField(
        label="Réponse à la réclamation *",
        widget=forms.Textarea(attrs={'rows': 4}),
        help_text="Votre réponse au client"
    )
    
    solution = forms.CharField(
        label="Solution proposée *",
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text="Solution mise en place ou proposée"
    )
    
    agent = forms.CharField(
        label="Agent responsable *",
        max_length=100
    )

class ReclamationResolutionForm(forms.Form):
    """
    Formulaire pour résoudre une réclamation avec compensation
    """
    agent = forms.CharField(
        label="Agent responsable *",
        max_length=100
    )
    
    accorder_compensation = forms.BooleanField(
        label="Accorder une compensation",
        required=False,
        help_text="Cocher si vous souhaitez accorder une compensation au client"
    )
    
    montant_compensation = forms.DecimalField(
        label="Montant de la compensation (DA)",
        max_digits=10,
        decimal_places=2,
        required=False,
        initial=0,
        help_text="Montant en dinars algériens"
    )
    
    def clean(self):
        """
        Validation : Si compensation cochée, montant obligatoire
        """
        cleaned_data = super().clean()
        accorder = cleaned_data.get('accorder_compensation')
        montant = cleaned_data.get('montant_compensation')
        
        if accorder and (not montant or montant <= 0):
            raise forms.ValidationError({
                'montant_compensation': "Le montant doit être supérieur à 0 si vous accordez une compensation"
            })
        
        return cleaned_data

class AssignationForm(forms.Form):
    """
    Formulaire simple pour assigner un agent
    (utilisable pour incidents ET réclamations)
    """
    agent_nom = forms.CharField(
        label="Nom de l'agent *",
        max_length=100,
        help_text="Agent qui sera responsable du traitement"
    )

class LoginForm(AuthenticationForm):
    """Formulaire de connexion"""
    username = forms.CharField(
        label="Nom d'utilisateur",
        widget=forms.TextInput(attrs={
            'placeholder': "Nom d'utilisateur",
            'autofocus': True
        })
    )
    password = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(attrs={
            'placeholder': "Mot de passe"
        })
    )

class AjouterAgentForm(forms.ModelForm):
    """Formulaire pour ajouter un nouvel agent (par le responsable)"""
    
    class Meta:
        model = AgentUtilisateur
        fields = ['first_name', 'last_name', 'email', 'telephone']
        labels = {
            'first_name': 'Prénom',
            'last_name': 'Nom',
            'email': 'Email',
            'telephone': 'Téléphone',
        }
        widgets = {
            'first_name': forms.TextInput(attrs={'placeholder': 'Ahmed'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Benali'}),
            'email': forms.EmailInput(attrs={'placeholder': 'ahmed.benali@example.com'}),
            'telephone': forms.TextInput(attrs={'placeholder': '+213 555 123 456'}),
        }

class ChangerMotDePasseForm(forms.Form):
    """Formulaire pour changer le mot de passe"""
    ancien_mot_de_passe = forms.CharField(
        label="Mot de passe actuel",
        widget=forms.PasswordInput(attrs={'placeholder': 'Mot de passe actuel'})
    )
    nouveau_mot_de_passe = forms.CharField(
        label="Nouveau mot de passe",
        widget=forms.PasswordInput(attrs={'placeholder': 'Nouveau mot de passe'})
    )
    confirmer_mot_de_passe = forms.CharField(
        label="Confirmer le nouveau mot de passe",
        widget=forms.PasswordInput(attrs={'placeholder': 'Confirmer le mot de passe'})
    )
    
    def clean(self):
        cleaned_data = super().clean()
        nouveau = cleaned_data.get('nouveau_mot_de_passe')
        confirmer = cleaned_data.get('confirmer_mot_de_passe')
        
        if nouveau and confirmer and nouveau != confirmer:
            raise forms.ValidationError("Les mots de passe ne correspondent pas")
        
        return cleaned_data
















































