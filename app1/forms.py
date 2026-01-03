from django import forms
from .models import Client, Chauffeur, Vehicule, TypeService, Destination, Tarification, Tournee, Expedition, TrackingExpedition

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



















































