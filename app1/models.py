from django.db import models
from phonenumber_field.modelfields import PhoneNumberField
import math
from decimal import Decimal
from datetime import date, timedelta 
from django.utils import timezone
from django.core.exceptions import ValidationError

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
    compensation_autorisee = models.BooleanField(default=True,help_text="Autoriser la compensation automatique du crédit sur les factures")

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
    
    def get_numero_tournee(self):
        """
        Génère un ID personnalisé : TR-{ZONE}-{DD-MM}-{NomChauffeur}
        Exemple : TR-CENTRE-04-01-Benali
        """
        if self.date_depart:
            date_str = self.date_depart.strftime('%d-%m')
        else:
            date_str = "00-00"
        
        nom_chauffeur = self.chauffeur.nom[:10] if self.chauffeur else "INCONNU"
        
        return f"TR-{self.zone_cible}-{date_str}-{nom_chauffeur}"
    
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
        from .utils import ExpeditionService, TrackingService, FacturationService
        
        is_new = self.pk is None
        
        # Calcul automatique du montant si non fourni
        if not self.montant_total:
            ExpeditionService.calculer_montant(self)
        
        # Sauvegarder d'abord pour avoir un ID
        super().save(*args, **kwargs)
        
        # Actions APRÈS save (quand on a un ID)
        if is_new:
            # 1. Affectation tournée
            if self.type_service.type_service == 'EXPRESS':
                ExpeditionService.creer_tournee_express(self)
            else:
                ExpeditionService.affecter_tournee_intelligente(self)
            
            # 2. Calculer date livraison si tournée assignée
            if self.tournee:
                ExpeditionService.calculer_date_livraison(self)
                # Sauvegarder à nouveau pour enregistrer la date
                super().save(update_fields=['date_livraison_prevue', 'tournee'])
            
            # 3. Trackings
            TrackingService.creer_suivi(self, 'COLIS_CREE', "Colis enregistré dans le système")
            
            if self.tournee:
                TrackingService.creer_suivi(
                    self,
                    'EN_ATTENTE',
                    f"Affecté à la tournée #{self.tournee.id}. Départ prévu: {self.tournee.date_depart.strftime('%d/%m/%Y')}"
                )
            
            # 4. Créer ou ajouter à une facture
            FacturationService.gerer_facture_expedition(self)

class TrackingExpedition(models.Model):
    expedition = models.ForeignKey('Expedition', on_delete=models.CASCADE, related_name='suivis')
    statut_etape = models.CharField(max_length=20, choices=[('COLIS_CREE', 'Colis créé'),('EN_ATTENTE', 'En attente'),('EN_TRANSIT', 'En transit'),('LIVRE', 'Livré'),('ECHEC', 'Échec'),])
    date_heure = models.DateTimeField(auto_now_add=True)
    commentaire = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-date_heure']
    
    def __str__(self):
        return f"{self.expedition} - {self.get_statut_etape_display()}"
    
# ========== SECTION 3 : FACTURATION ET PAIEMENTS ==========

class Facture(models.Model):
    
    client = models.ForeignKey('Client', on_delete=models.CASCADE, related_name='factures')
    expeditions = models.ManyToManyField('Expedition', related_name='factures')
    numero_facture = models.CharField(max_length=50, unique=True, blank=True)
    montant_ht = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    montant_tva = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    montant_ttc = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    taux_tva = models.DecimalField(max_digits=5, decimal_places=2, default=19.00)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_echeance = models.DateField()
    statut = models.CharField(max_length=20, choices=[('IMPAYEE', 'Impayée'),('PARTIELLEMENT_PAYEE', 'Partiellement payée'),('PAYEE', 'Payée'),('EN_RETARD', 'En retard'),('ANNULEE', 'Annulée'),], default='IMPAYEE')
    remarques = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-date_creation']
    
    def __str__(self):
        return f"{self.numero_facture} - {self.client}"
    
    def save(self, *args, **kwargs):
        if not self.numero_facture:
            super().save(*args, **kwargs)
            
            # Compter les factures du client ce jour-là
            nb = Facture.objects.filter(
                client=self.client,
                date_creation__date=self.date_creation.date()
            ).count()
            
            self.numero_facture = f"F-{self.date_creation.strftime('%Y%m%d')}-CL-{self.client.id:03d}-{nb:03d}"
            kwargs['force_insert'] = False
        
        super().save(*args, **kwargs)
    

class Paiement(models.Model):
    
    facture = models.ForeignKey('Facture', on_delete=models.CASCADE, related_name='paiements')
    client = models.ForeignKey('Client', on_delete=models.CASCADE, related_name='paiements')
    montant_paye = models.DecimalField(max_digits=10, decimal_places=2)
    date_paiement = models.DateTimeField(auto_now_add=True)
    mode_paiement = models.CharField(max_length=20, choices=[('ESPECES', 'Espèces'),('CARTE', 'Carte bancaire'),('VIREMENT', 'Virement'),('CHEQUE', 'Chèque'),])
    reference_transaction = models.CharField(max_length=100, blank=True, null=True)
    remarques = models.TextField(blank=True, null=True)
    statut = models.CharField(max_length=20, default='VALIDE')
    
    class Meta:
        ordering = ['-date_paiement']
    
    def __str__(self):
        return f"Paiement {self.montant_paye} DA - {self.facture.numero_facture}"
    
    def save(self, *args, **kwargs):
        """Validation et mise à jour automatique"""
        from .utils import FacturationService
        from django.core.exceptions import ValidationError

        is_new = self.pk is None

        # ========== VALIDATION CRITIQUE ==========
        if self.facture.client != self.client:
            raise ValidationError(
                f"ERREUR : Le client du paiement ({self.client}) ne correspond pas "
                f"au client de la facture ({self.facture.client})."
            )

        # Validations pour nouveaux paiements uniquement
        if is_new:
            if self.facture.statut == 'ANNULEE':
                raise ValidationError("Impossible de payer une facture annulée")

            if self.facture.statut == 'PAYEE':
                raise ValidationError("Cette facture est déjà entièrement payée")

            montant_restant = FacturationService.calculer_montant_restant(self.facture)

            if montant_restant <= 0:
                raise ValidationError("Cette facture est déjà entièrement payée")

            if self.montant_paye > montant_restant:
                raise ValidationError(
                    f"Le montant ({self.montant_paye} DA) dépasse le montant restant ({montant_restant} DA)"
                )

            if self.montant_paye <= 0:
                raise ValidationError("Le montant doit être supérieur à 0")

            # Génération numéro paiement
            super().save(*args, **kwargs)  # obtenir PK
            nb = Paiement.objects.filter(facture=self.facture).count()
            self.numero_paiement = f"P-{self.facture.numero_facture}-{nb:02d}"

        super().save(*args, **kwargs)

        # Mise à jour solde client
        if is_new and self.statut == 'VALIDE':
            self.client.solde -= self.montant_paye
            self.client.save()

            FacturationService.mettre_a_jour_statut_facture(self.facture)

class Notification(models.Model):
    """
    Système de notifications pour l'agent
    Exemples : maintenance véhicule, alertes, etc.
    """
    
    type_notification = models.CharField(max_length=30, choices=[('MAINTENANCE_AVANT', 'Maintenance prévue demain'),('MAINTENANCE_APRES', 'Véhicule en maintenance - Retour?'),('SOLDE_NEGATIF', 'Client en crédit'),('REMBOURSEMENT_REQUIS', 'Remboursement incident requis'),('TOURNEE_TERMINEE', 'Tournée terminée'),('INFO', 'Information'),('ALERTE', 'Alerte'),])
    titre = models.CharField(max_length=200)
    message = models.TextField()
    statut = models.CharField(max_length=20, choices=[('NON_LUE', 'Non lue'),('LUE', 'Lue'),('TRAITEE', 'Traitée'),], default='NON_LUE')
    
    vehicule = models.ForeignKey('Vehicule', on_delete=models.CASCADE, null=True, blank=True)
    chauffeur = models.ForeignKey('Chauffeur', on_delete=models.CASCADE, null=True, blank=True)
    tournee = models.ForeignKey('Tournee', on_delete=models.CASCADE, null=True, blank=True)
    client = models.ForeignKey('Client', on_delete=models.CASCADE, null=True, blank=True)
    
    action_effectuee = models.CharField(max_length=50, blank=True, null=True, help_text="Action effectuée par l'agent (ex: COMPENSATION_AUTORISEE, REMBOURSE, REVISION_CONFIRMEE)")
    commentaire_traitement = models.TextField(blank=True, null=True, help_text="Commentaire de l'agent lors du traitement")
    date_creation = models.DateTimeField(auto_now_add=True)
    date_traitement = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-date_creation']
    
    def __str__(self):
        return f"{self.get_type_notification_display()} - {self.titre}"
    
# ========== SECTION 4 : INCIDENTS ==========

class Incident(models.Model):

    #ici une exp/tourne peuvent avoir pleusieur incidents 
    #pour le delete alors si on supprime une exp l'icident sera automatiquement supprimer de la liste 
    expedition = models.ForeignKey(
        'Expedition', on_delete=models.CASCADE, related_name='incidents',null=True,blank=True,
        help_text="Expédition concernée (si applicable)")
    
    tournee = models.ForeignKey('Tournee', on_delete=models.CASCADE, related_name='incidents',null=True,
        blank=True,help_text="Tournée concernée (si applicable)")
    
    numero_incident = models.CharField(max_length=50, unique=True, blank=True, editable=False)
    
    type_incident = models.CharField(max_length=30, choices=[
        ('RETARD', 'Retard de livraison'),('PERTE', 'Perte de colis'),('ENDOMMAGEMENT', 'Endommagement'),
        ('PROBLEME_TECHNIQUE', 'Problème technique véhicule'), ('ACCIDENT', 'Accident'),('REFUS_DESTINATAIRE', 'Refus du destinataire'),
        ('ADRESSE_INCORRECTE', 'Adresse incorrecte'),('DESTINATAIRE_ABSENT', 'Destinataire absent'),('AUTRE', 'Autre'),])
    
    severite = models.CharField(max_length=20, choices=[('FAIBLE', 'Faible'), ('MOYENNE', 'Moyenne'), ('ELEVEE', 'Élevée'),
        ('CRITIQUE', 'Critique'),], default='MOYENNE')
    
    titre = models.CharField(max_length=200, help_text="Résumé court de l'incident")
    description = models.TextField(help_text="Description détaillée de l'incident")
    lieu_incident = models.CharField(max_length=200, blank=True, null=True)
    date_heure_incident = models.DateTimeField(help_text="Date et heure de survenue de l'incident")\
    
    statut = models.CharField(max_length=20, choices=[ ('SIGNALE', 'Signalé'), ('EN_COURS', 'En cours de traitement'),
        ('RESOLU', 'Résolu'),('CLOS', 'Clôturé'),] , default='SIGNALE')
    
    signale_par = models.CharField(max_length=100, help_text="Nom de la personne ayant signalé")
    agent_responsable = models.CharField(max_length=100, blank=True, null=True, help_text="Agent en charge du traitement")
    actions_entreprises = models.TextField(blank=True, null=True, help_text="Actions effectuées pour résoudre l'incident")
    date_resolution = models.DateTimeField(blank=True, null=True)
    cout_estime = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Coût estimé en DA")

    #On ne peut pas justifier l'incident par un seul document et si on met plus que 2 on risque de Complexité inutile
    #exemple des justification document1 → rapport du chauffeur document2 → rapport de l’agence / assurance
    #photo1 → photo du colis abîmé photo2 → photo du véhicule ou du lieu 

    document1 = models.FileField(upload_to='incidents/documents/', blank=True, null=True)
    document2 = models.FileField(upload_to='incidents/documents/', blank=True, null=True)
    photo1 = models.ImageField(upload_to='incidents/photos/', blank=True, null=True)
    photo2 = models.ImageField(upload_to='incidents/photos/', blank=True, null=True)
    alerte_direction = models.BooleanField(default=False, help_text="Alerter la direction")
    alerte_client = models.BooleanField(default=False, help_text="Alerter le client")
    remboursement_effectue = models.BooleanField(default=False, help_text="Remboursement effectué au client")
    montant_rembourse = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Montant remboursé en DA")
    taux_remboursement = models.DecimalField(max_digits=5, decimal_places=2, default=100.00,help_text="Pourcentage de remboursement (0-100%)")
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    remarques = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-date_heure_incident']
        verbose_name = "Incident"
        verbose_name_plural = "Incidents"
    
    def __str__(self):
        cible = "Non lié"
        if self.expedition:
            cible = f"Expédition #{self.expedition.id}"
        elif self.tournee:
            cible = f"Tournée #{self.tournee.id}"

        return f"{self.numero_incident} - {self.get_type_incident_display()} ({cible})"
    
    def save(self, *args, **kwargs):
        from .utils import IncidentService
        
        is_new = self.pk is None
        
        # Générer le numéro d'incident
        if not self.numero_incident:
            super().save(*args, **kwargs)
            self.numero_incident = f"INC-{self.date_creation.strftime('%Y%m%d')}-{self.id:05d}"
            kwargs['force_insert'] = False
        
        super().save(*args, **kwargs)
        
        # Traitement post-sauvegarde
        if is_new:
            IncidentService.traiter_nouvel_incident(self)

    def clean(self):
        if self.expedition and self.tournee:
         raise ValidationError(
            "Un incident ne peut pas être lié à une expédition ET une tournée."
        )

        if not self.expedition and not self.tournee:
         raise ValidationError(
            "Un incident doit être lié soit à une expédition soit à une tournée."
        )

class HistoriqueIncident(models.Model):
    
    incident = models.ForeignKey(
        'Incident', 
        on_delete=models.CASCADE, 
        related_name='historique'
    )
    date_action = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=100, help_text="Type d'action effectuée")
    auteur = models.CharField(max_length=100, help_text="Qui a effectué l'action")
    details = models.TextField(blank=True, null=True)
    ancien_statut = models.CharField(max_length=20, blank=True, null=True)
    nouveau_statut = models.CharField(max_length=20, blank=True, null=True)
    
    class Meta:
        ordering = ['-date_action']
        verbose_name = "Historique d'incident"
        verbose_name_plural = "Historiques d'incidents"
    
    def __str__(self):
        return f"{self.incident.numero_incident} - {self.action} - {self.date_action.strftime('%d/%m/%Y %H:%M')}"
    
# ========== SECTION 4 : RECLAMATIONS ==========

class Reclamation(models.Model):

    numero_reclamation = models.CharField(max_length=50, unique=True, blank=True, editable=False)
    client = models.ForeignKey('Client', on_delete=models.CASCADE, related_name='reclamations')
    
    type_reclamation = models.CharField(max_length=20,choices=[('EXPEDITION', 'Liée à une expédition'),('FACTURE', 'Liée à une facture'),
        ('SERVICE', 'Liée à un service'),('AUTRE', 'Autre'),],default='EXPEDITION',help_text="Type de réclamation")

    expeditions = models.ManyToManyField('Expedition', related_name='reclamations',blank=True,help_text="Expéditions concernées")

    facture = models.ForeignKey('Facture', on_delete=models.SET_NULL, related_name='reclamations',null=True,blank=True,
        help_text="Facture concernée (si applicable)")
    
    service_concerne = models.CharField(max_length=50,blank=True,null=True,choices=[('LIVRAISON', 'Service de livraison'),
        ('FACTURATION', 'Service facturation'),('CLIENT', 'Service client'),('TECHNIQUE', 'Service technique'),
        ('COMMERCIAL', 'Service commercial'),('AUTRE', 'Autre'),],help_text="Service concerné (si type = SERVICE)")
    
    nature = models.CharField(max_length=30, choices=[('RETARD_LIVRAISON', 'Retard de livraison'),('COLIS_ENDOMMAGE', 'Colis endommagé'),
        ('COLIS_PERDU', 'Colis perdu'),('ERREUR_FACTURATION', 'Erreur de facturation'),('MAUVAIS_SERVICE', 'Mauvais service'),
        ('COMPORTEMENT_CHAUFFEUR', 'Comportement du chauffeur'),('COLIS_INCOMPLET', 'Colis incomplet'),
        ('REMBOURSEMENT', 'Demande de remboursement'),('AUTRE', 'Autre'),])
    
    priorite = models.CharField(max_length=20, choices=[('BASSE', 'Basse'),('NORMALE', 'Normale'),
        ('HAUTE', 'Haute'),('URGENTE', 'Urgente'),], default='NORMALE')
    
    objet = models.CharField(max_length=200, help_text="Objet de la réclamation")
    description = models.TextField(help_text="Description détaillée de la réclamation")

    statut = models.CharField(max_length=30, choices=[('OUVERTE', 'Ouverte'),('EN_COURS', 'En cours de traitement'),
        ('EN_ATTENTE_CLIENT', 'En attente de réponse du client'),('RESOLUE', 'Résolue'),
        ('CLOSE', 'Clôturée'),('ANNULEE', 'Annulée'),], default='OUVERTE')
    
    agent_responsable = models.CharField(max_length=100, blank=True, null=True, help_text="Agent assigné")
    date_assignation = models.DateTimeField(blank=True, null=True)
    reponse_agent = models.TextField(blank=True, null=True, help_text="Réponse de l'agent")
    solution_proposee = models.TextField(blank=True, null=True)
    date_resolution = models.DateTimeField(blank=True, null=True)
    delai_traitement_jours = models.IntegerField(blank=True, null=True, editable=False, help_text="Calculé automatiquement")
    commentaire_client = models.TextField(blank=True, null=True)
    piece_jointe1 = models.FileField(upload_to='reclamations/documents/', blank=True, null=True)
    piece_jointe2 = models.FileField(upload_to='reclamations/documents/', blank=True, null=True)
    compensation_accordee = models.BooleanField(default=False)
    montant_compensation = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Montant en DA")
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    remarques = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-date_creation']
        verbose_name = "Réclamation"
        verbose_name_plural = "Réclamations"
    
    def __str__(self):
        return f"{self.numero_reclamation} - {self.client} - {self.get_nature_display()}"
    
    def save(self, *args, **kwargs):
        from .utils import ReclamationService
        
        is_new = self.pk is None
        
        # Générer le numéro de réclamation
        if not self.numero_reclamation:
            super().save(*args, **kwargs)
            self.numero_reclamation = f"REC-{self.date_creation.strftime('%Y%m%d')}-{self.id:05d}"
            kwargs['force_insert'] = False
        
        super().save(*args, **kwargs)
        
        # Traitement post-sauvegarde
        if is_new:
            ReclamationService.traiter_nouvelle_reclamation(self)
        else:
            ReclamationService.calculer_delai_traitement(self)
    
    def clean(self):
        from django.core.exceptions import ValidationError

        if self.type_reclamation == 'SERVICE' and not self.service_concerne:
            raise ValidationError(
            "Le service concerné est obligatoire pour une réclamation de type SERVICE."
        )

        if self.type_reclamation != 'SERVICE' and self.service_concerne:
            raise ValidationError(
            "Le service concerné doit être vide si la réclamation n'est pas de type SERVICE."
        )

class HistoriqueReclamation(models.Model):
    """
    Historique des actions effectuées sur une réclamation
    """
    reclamation = models.ForeignKey('Reclamation', on_delete=models.CASCADE, related_name='historique')
    date_action = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=100, help_text="Type d'action effectuée")
    auteur = models.CharField(max_length=100, help_text="Qui a effectué l'action")
    details = models.TextField(blank=True, null=True)
    ancien_statut = models.CharField(max_length=30, blank=True, null=True)
    nouveau_statut = models.CharField(max_length=30, blank=True, null=True)
    
    class Meta:
        ordering = ['-date_action']
        verbose_name = "Historique de réclamation"
        verbose_name_plural = "Historiques de réclamations"
    
    def __str__(self):
        return f"{self.reclamation.numero_reclamation} - {self.action} - {self.date_action.strftime('%d/%m/%Y %H:%M')}"