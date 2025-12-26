from django.db import models
from phonenumber_field.modelfields import PhoneNumberField
import math
from decimal import Decimal
from datetime import date, timedelta 
from django.utils import timezone

# SECTION 1 : TABLES DE BASE
class Client(models.Model):

    nom = models.CharField(max_length=20)
    prenom = models.CharField(max_length=20)
    date_naissance = models.DateField(default='2000-01-01')
    telephone = PhoneNumberField(region='DZ', unique=True)
    email = models.EmailField(blank=True, null=True)
    adresse = models.TextField(blank=True, null=True)
    ville = models.CharField(max_length=100, blank=True, null=True)
    wilaya = models.CharField(max_length=100, blank=True, null=True)
    solde = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    date_inscription = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    remarques = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"CL-{self.id:03d} {self.prenom} {self.nom}"

class Chauffeur(models.Model):

    nom = models.CharField(max_length=50)
    prenom = models.CharField(max_length=50)
    date_naissance = models.DateField(default='2000-01-01')
    telephone = PhoneNumberField(region='DZ')
    email = models.EmailField(blank=True, null=True)
    adresse = models.TextField(blank=True, null=True)
    ville = models.CharField(max_length=100, blank=True, null=True)
    wilaya = models.CharField(max_length=100, blank=True, null=True)
    numero_permis = models.CharField(max_length=50, unique=True)
    date_obtention_permis = models.DateField()
    date_expiration_permis = models.DateField()
    date_embauche = models.DateField()
    salaire = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    statut_disponibilite = models.CharField(max_length=20, choices=[('DISPONIBLE', 'Disponible'),('EN_TOURNEE', 'En tournée'),('CONGE', 'En congé'),('MALADIE', 'Maladie'),('AUTRE', 'Autre raison'),], default='DISPONIBLE')
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    remarques = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.prenom} {self.nom} - {self.get_id_chauffeur()}"

    def get_id_chauffeur(self):
        return f"CH-{self.id:03d}"

class Vehicule(models.Model):

    numero_immatriculation = models.CharField(max_length=50, unique=True)
    marque = models.CharField(max_length=100)
    modele = models.CharField(max_length=100)
    annee = models.IntegerField()
    type_vehicule = models.CharField(max_length=20, choices=[('CAMIONNETTE', 'Camionnette'),('CAMION', 'Camion'),('FOURGON', 'Fourgon'),('MOTO', 'Moto'),])
    capacite_poids = models.DecimalField(max_digits=8, decimal_places=2, help_text="Capacité en kg")
    capacite_volume = models.DecimalField(max_digits=8, decimal_places=2, help_text="Volume en m³")
    consommation_moyenne = models.DecimalField(max_digits=5, decimal_places=2, help_text="Consommation en L/100km")
    etat = models.CharField(max_length=20, choices=[('EXCELLENT', 'Excellent'),('BON', 'Bon'),('MOYEN', 'Moyen'),('MAUVAIS', 'Mauvais'),], default='BON')
    statut = models.CharField(max_length=20, choices=[('DISPONIBLE', 'Disponible'),('EN_TOURNEE', 'En tournée'),('EN_MAINTENANCE', 'En maintenance'),('HORS_SERVICE', 'Hors service'),], default='DISPONIBLE')
    date_derniere_revision = models.DateField(blank=True, null=True)
    date_prochaine_revision = models.DateField(blank=True, null=True)
    kilometrage = models.PositiveIntegerField(default=0, help_text="Compteur kilométrique total")
    date_acquisition = models.DateField()
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    remarques = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.marque} {self.modele} - {self.numero_immatriculation}"
    def save(self, *args, **kwargs):
        from .utils import VehiculeService
        VehiculeService.gerer_revision(self)
        super().save(*args, **kwargs)

class Destination(models.Model):

    ville = models.CharField(max_length=100, blank=True, null=True)
    wilaya = models.CharField(max_length=100)
    pays = models.CharField(max_length=100, default='Algérie')
    zone_geographique = models.CharField(max_length=20, choices=[('LOCALE', 'Locale (même wilaya)'),('NATIONALE', 'Nationale'),('INTERNATIONALE', 'Internationale'),])
    zone_logistique = models.CharField(max_length=10, choices=[('CENTRE', 'Centre (Alger, Blida...)'),('EST', 'Est (Constantine, Annaba, Sétif...)'),('OUEST', 'Ouest (Oran, Tlemcen, Sidi Bel Abbès...)'),('SUD', 'Sud (Tamanrasset, Adrar, Bechar...)'),], default='CENTRE')
    distance_estimee = models.IntegerField(help_text="Distance en km depuis le dépôt principal")
    tarif_base = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Tarif de base en DA")
    delai_livraison_estime = models.IntegerField(default=1, help_text="Délai estimé en jours")
    code_postal = models.CharField(max_length=10, blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    remarques = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.ville} - {self.wilaya} - {self.pays}"

class TypeService(models.Model):

    type_service = models.CharField(max_length=20, choices=[('STANDARD', 'Standard'),('EXPRESS', 'Express'),('INTERNATIONAL', 'International'), ], unique=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.type_service

class Tarification(models.Model):

    destination = models.ForeignKey(Destination, on_delete=models.CASCADE)
    type_service = models.ForeignKey(TypeService, on_delete=models.CASCADE)
    tarif_poids = models.DecimalField(max_digits=10, decimal_places=2, default=10.00, help_text="Tarif par kg en DA")
    tarif_volume = models.DecimalField(max_digits=10, decimal_places=2, default=20.00, help_text="Tarif par m³ en DA")
    
    class Meta:
        unique_together = ['destination', 'type_service']

    def __str__(self):
        return f"{self.destination.ville} - {self.destination.wilaya} - {self.type_service}"

    def calculer_prix(self, poids, volume):
        poids = Decimal(str(poids))
        volume = Decimal(str(volume))
        
        if self.type_service.type_service == 'EXPRESS':
            # EXPRESS : tarif de base calculé selon distance
            tarif_base_express = Decimal(str(self.destination.distance_estimee)) * Decimal('25.00')
            prix = tarif_base_express + (poids * self.tarif_poids) + (volume * self.tarif_volume)
        else:
            # STANDARD et INTERNATIONAL : tarif_base normal
            prix = self.destination.tarif_base + (poids * self.tarif_poids) + (volume * self.tarif_volume)
        
        return prix
    
    def calculer_delai(self):

        if self.type_service.type_service == 'EXPRESS':
            # EXPRESS : délai selon distance
            if self.destination.distance_estimee < 500:
                return 1  # 1 jour
            else:
                return 2  # 2 jours
        else:
            # STANDARD et INTERNATIONAL : délai de la destination
            return self.destination.delai_livraison_estime

# SECTION 2 : Gestions
 
class Tournee(models.Model):
    chauffeur = models.ForeignKey('Chauffeur', on_delete=models.PROTECT)
    vehicule = models.ForeignKey('Vehicule', on_delete=models.PROTECT)
    date_depart = models.DateTimeField()
    date_retour_prevue = models.DateTimeField(blank=True, null=True)
    date_retour_reelle = models.DateTimeField(blank=True, null=True)
    zone_cible = models.CharField(max_length=10, choices=[('CENTRE', 'Centre'), ('EST', 'Est'), ('OUEST', 'Ouest'), ('SUD', 'Sud')])
    kilometrage_depart = models.PositiveIntegerField(blank=True, null=True, editable=False)
    kilometrage_arrivee = models.PositiveIntegerField(blank=True, null=True)
    kilometrage_parcouru = models.PositiveIntegerField(blank=True, null=True, editable=False)
    consommation_carburant = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True, editable=False)
    statut = models.CharField(max_length=20, choices=[('PREVUE', 'Prévue'), ('EN_COURS', 'En cours'), ('TERMINEE', 'Terminée')], default='PREVUE')
    est_privee = models.BooleanField(default=False, help_text="Tournée privée EXPRESS")
    remarques = models.TextField(blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Tournée #{self.id} - {self.chauffeur} - {self.statut}"
    
    def save(self, *args, **kwargs):
        from .utils import TourneeService
        TourneeService.traiter_tournee(self)
        super().save(*args, **kwargs)

class Expedition(models.Model):

    client = models.ForeignKey('Client', on_delete=models.PROTECT)
    destination = models.ForeignKey('Destination', on_delete=models.PROTECT)
    type_service = models.ForeignKey('TypeService', on_delete=models.PROTECT)
    tournee = models.ForeignKey('Tournee', on_delete=models.SET_NULL, null=True, blank=True, related_name='expeditions')
    nom_destinataire = models.CharField(max_length=100)
    telephone_destinataire = PhoneNumberField(region='DZ')
    email_destinataire = models.EmailField()  
    adresse_destinataire = models.TextField()
    poids = models.DecimalField(max_digits=8, decimal_places=2, help_text="Poids en kg")
    volume = models.DecimalField(max_digits=8, decimal_places=2, help_text="Volume en m³")
    description = models.TextField(blank=True, null=True)
    montant_total = models.DecimalField(max_digits=10, decimal_places=2, default=0, editable=False)
    date_livraison_prevue = models.DateField(blank=True, null=True, editable=False)
    statut = models.CharField(max_length=20, choices=[('EN_ATTENTE', 'En attente'),('EN_TRANSIT', 'En transit'),('LIVRE', 'Livré'),('ECHEC', 'Échec'),], default='EN_ATTENTE')
    date_creation = models.DateTimeField(auto_now_add=True)
    date_livraison_reelle = models.DateField(blank=True, null=True)
    remarques = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"{self.client} → {self.destination.ville}"
    
    def get_numero_expedition(self):
        return f"EXP-{self.id:06d}"
    
    def save(self, *args, **kwargs):
        from .utils import ExpeditionService, TrackingService
        
        is_new = self.pk is None
        
        ExpeditionService.avant_sauvegarde(self)
        super().save(*args, **kwargs)
        
        # Trackings automatiques APRÈS save (pour avoir expedition.id)
        if is_new:
            TrackingService.creer_suivi(self, 'COLIS_CREE', "Colis enregistré dans le système")
            
            if self.tournee:
                TrackingService.creer_suivi(
                    self,
                    'EN_ATTENTE',
                    f"Affecté à la tournée #{self.tournee.id}. Départ prévu: {self.tournee.date_depart.strftime('%d/%m/%Y')}"
                )

    def delete(self, *args, **kwargs):
        from .utils import ExpeditionService
        ExpeditionService.avant_suppression(self)
        super().delete(*args, **kwargs)
        
class TrackingExpedition(models.Model):
    expedition = models.ForeignKey('Expedition', on_delete=models.CASCADE, related_name='suivis')
    statut_etape = models.CharField(max_length=20, choices=[('COLIS_CREE', 'Colis créé'),('EN_ATTENTE', 'En attente'),('EN_TRANSIT', 'En transit'),('LIVRE', 'Livré'),('ECHEC', 'Échec'),])
    date_heure = models.DateTimeField(auto_now_add=True)
    commentaire = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-date_heure']
    
    def __str__(self):
        return f"{self.expedition} - {self.get_statut_etape_display()}"