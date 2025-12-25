from django.db import models
from phonenumber_field.modelfields import PhoneNumberField
import math
from decimal import Decimal
from datetime import date, timedelta 
from django.utils import timezone
from django.db.models import Sum

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

class Destination(models.Model):

    ville = models.CharField(max_length=100)
    wilaya = models.CharField(max_length=100, blank=True, null=True)
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
    # --- RELATIONS ---
    client = models.ForeignKey(Client, on_delete=models.PROTECT)
    type_service = models.ForeignKey(TypeService, on_delete=models.PROTECT)
    destination = models.ForeignKey(Destination, on_delete=models.PROTECT)
    # ForeignKey vers Tournee (placée après Tournee dans le code pour éviter les erreurs)
    tournee = models.ForeignKey(   ##modifiable
        Tournee, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='expeditions'
    )

    # --- INFOS DESTINATAIRE ---
    adresse_destinataire = models.TextField(help_text="Adresse complète de livraison")
    nom_destinataire = models.CharField(max_length=100, blank=True, null=True)
    telephone_destinataire = PhoneNumberField(region='DZ', blank=True, null=True)
    ##if date_depart.tournee -1 : notifier par sms/email le destinataire "votre colis est destinee demain, il est prevue d'arriver 'date livraison"

    # --- CARACTÉRISTIQUES COLIS ---
    poids = models.DecimalField(max_digits=8, decimal_places=2, help_text="kg")
    volume = models.DecimalField(max_digits=8, decimal_places=2, help_text="m³")
    description = models.TextField(blank=True, null=True)

    # --- FINANCES & STATUTS ---
    montant_total = models.DecimalField(max_digits=10, decimal_places=2, default=0, editable=False)
    statut = models.CharField(
        max_length=20, 
        choices=[
            ('EN_ATTENTE', 'En attente'),
            ('EN_TRANSIT', 'En transit'),
            ('LIVRE', 'Livré'),
            ('ECHEC', 'Échec'),
        ], 
        default='EN_ATTENTE'
    )

    # --- DATES ---
    date_creation = models.DateTimeField(auto_now_add=True)
    date_livraison_prevue = models.DateField(blank=True, null=True, editable=False)
    date_livraison_reelle = models.DateField(blank=True, null=True, editable=False)
    
    def get_numero_expedition(self):
        return f"EXP-{self.id:06d}" if self.id else "EXP-NOUVEAU"
    
    def save(self, *args, **kwargs):
        from datetime import date, timedelta 
        from django.utils import timezone
        import math 
        from .models import TrackingExpedition

        # Garder en mémoire si c'est une création
        is_new = self.pk is None

        # 1. CALCULS FINANCIERS ET DÉLAIS
        montant, delai = Tarification.obtenir_calculs(
            self.destination, self.type_service, self.poids, self.volume
        )
        self.montant_total = montant

        # 2. LOGIQUE D'AFFECTATION INTELLIGENTE (Si pas déjà affecté)
        if not self.tournee:
            # --- CAS A : SERVICE EXPRESS ---
            if self.type_service.type_service == 'EXPRESS':
                chauffeur_dispo = Chauffeur.objects.filter(statut_disponibilite='DISPONIBLE').first()
                vehicule_dispo = Vehicule.objects.filter(statut='DISPONIBLE').first()
                
                if chauffeur_dispo and vehicule_dispo:
                    nouvelle_tournee = Tournee.objects.create(
                        chauffeur=chauffeur_dispo,
                        vehicule=vehicule_dispo,
                        date_depart=timezone.now(),
                        zone_cible=self.destination.zone_logistique,
                        statut='PREVUE'
                    )
                    self.tournee = nouvelle_tournee
                    self.statut = 'EN_ATTENTE'

            # --- CAS B : SERVICE STANDARD ---
            else:
                tournees_candidates = Tournee.objects.filter(
                    zone_cible=self.destination.zone_logistique,
                    statut='PREVUE',
                    date_depart__gte=timezone.now()
                ).order_by('date_depart')
                
                for tournee in tournees_candidates:
                    poids_actuel = tournee.expeditions.aggregate(total=Sum('poids'))['total'] or 0
                    volume_actuel = tournee.expeditions.aggregate(total=Sum('volume'))['total'] or 0
                    
                    if (float(poids_actuel) + float(self.poids) <= float(tournee.vehicule.capacite_poids) and 
                        float(volume_actuel) + float(self.volume) <= float(tournee.vehicule.capacite_volume)):
                        self.tournee = tournee
                        break
        
        # --- MISE À JOUR DU STATUT SELON LA TOURNÉE ---
        if self.tournee:
            self.statut = 'EN_TRANSIT' if self.tournee.statut == 'EN_COURS' else 'EN_ATTENTE'

        # 3. CALCUL DE LA DATE DE LIVRAISON PRÉVUE (Sorti du bloc if/else)
        date_base = self.tournee.date_depart.date() if self.tournee else date.today()
        self.date_livraison_prevue = date_base + timedelta(days=math.ceil(float(delai)))
        
        # 4. SAUVEGARDE PHYSIQUE (Obligatoire pour avoir un ID pour le tracking)
        super().save(*args, **kwargs)

        # 5. GÉNÉRATION AUTOMATIQUE DU TRACKING (Maintenant hors du bloc else)
        if is_new:
            TrackingExpedition.objects.create(
                expedition=self, 
                statut_etape='COLIS_CREE',
                commentaire="Colis enregistré dans le système."
            )

        if self.tournee and not self.historique_tracking.filter(statut_etape='AFFECTE_TOURNEE').exists():
            TrackingExpedition.objects.create(
                expedition=self, 
                statut_etape='AFFECTE_TOURNEE',
                commentaire=f"Affecté à la Tournée {self.tournee.id}"
            )

class TrackingExpedition(models.Model):
    expedition = models.ForeignKey(Expedition, on_delete=models.CASCADE, related_name='historique_tracking')
    date_evenement = models.DateTimeField(auto_now_add=True)
    
    STATUT_TRACKING_CHOICES = [
        ('COLIS_CREE', 'Colis enregistré'),
        ('AFFECTE_TOURNEE', 'Affecté à une tournée'),
        ('EN_CHARGEMENT', 'En cours de chargement (2h avant départ)'),
        ('EN_TRANSIT', 'En transit (Camion en route)'),
        ('LIVRE', 'Livré à destination'),
        ('ECHEC_LIVRAISON', 'Échec de livraison (Incident)'),
        ('RETOUR_DEPOT', 'Retour au dépôt'),
    ]
    
    statut_etape = models.CharField(max_length=30, choices=STATUT_TRACKING_CHOICES, blank=True)
    commentaire = models.TextField(blank=True, null=True)
    


    class Meta:
        ordering = ['-date_evenement']