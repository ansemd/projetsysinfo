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
        return f"{self.prenom} {self.nom}"

    def get_id_client(self):
        return f"CL-{self.id:03d}"


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


    STATUT_CHOICES = [
        ('DISPONIBLE', 'Disponible'),
        ('EN_TOURNEE', 'En tournée'),
        ('CONGE', 'En congé'),
        ('MALADIE', 'Maladie'),
        ('AUTRE', 'Autre raison'),
    ]
    statut_disponibilite = models.CharField(max_length=20, choices=STATUT_CHOICES, default='DISPONIBLE')


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


    TYPE_CHOICES = [
        ('CAMIONNETTE', 'Camionnette'),
        ('CAMION', 'Camion'),
        ('FOURGON', 'Fourgon'),
        ('MOTO', 'Moto'),
    ]
    type_vehicule = models.CharField(max_length=20, choices=TYPE_CHOICES)


    capacite_poids = models.DecimalField(max_digits=8, decimal_places=2, help_text="Capacité en kg")
    capacite_volume = models.DecimalField(max_digits=8, decimal_places=2, help_text="Volume en m³")
    consommation_moyenne = models.DecimalField(max_digits=5, decimal_places=2, help_text="Consommation en L/100km")


    ETAT_CHOICES = [
        ('EXCELLENT', 'Excellent'),
        ('BON', 'Bon'),
        ('MOYEN', 'Moyen'),
        ('MAUVAIS', 'Mauvais'),
    ]
    etat = models.CharField(max_length=20, choices=ETAT_CHOICES, default='BON')


    STATUT_CHOICES = [
        ('DISPONIBLE', 'Disponible'),
        ('EN_TOURNEE', 'En tournée'),
        ('EN_MAINTENANCE', 'En maintenance'),
        ('HORS_SERVICE', 'Hors service'),
    ]
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='DISPONIBLE')


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


    ZONE_CHOICES = [
        ('LOCALE', 'Locale (même wilaya)'),
        ('NATIONALE', 'Nationale'),
        ('INTERNATIONALE', 'Internationale'),
    ]
    zone_geographique = models.CharField(max_length=20, choices=ZONE_CHOICES)


    ZONE_LOGISTIQUE_CHOICES = [
        ('CENTRE', 'Centre (Alger, Blida...)'),
        ('EST', 'Est (Constantine, Annaba, Sétif...)'),
        ('OUEST', 'Ouest (Oran, Tlemcen, Sidi Bel Abbès...)'),
        ('SUD', 'Sud (Tamanrasset, Adrar, Bechar...)'),
    ]
    zone_logistique = models.CharField(max_length=10, choices=ZONE_LOGISTIQUE_CHOICES, default='CENTRE')


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

    
    TYPE_CHOICES = [
        ('STANDARD', 'Standard'),
        ('EXPRESS', 'Express'),
        ('INTERNATIONAL', 'International'),
    ]
    type_service = models.CharField(max_length=20, choices=TYPE_CHOICES, unique=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.type_service


class Tarification(models.Model):

    
    destination = models.ForeignKey(Destination, on_delete=models.CASCADE)
    type_service = models.ForeignKey(TypeService, on_delete=models.CASCADE)


    tarif_poids = models.DecimalField(max_digits=10, decimal_places=2, default=10.00, help_text="Tarif par kg en DA")
    tarif_volume = models.DecimalField(max_digits=10, decimal_places=2, default=20.00, help_text="Tarif par m³ en DA")


    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['destination', 'type_service']

    def __str__(self):
        return f"{self.destination.ville} - {self.type_service}"

    def calculer_prix(self, poids, volume):

        poids = Decimal(str(poids))
        volume = Decimal(str(volume))
        

        prix = self.destination.tarif_base + (poids * self.tarif_poids) + (volume * self.tarif_volume)
        

        if self.type_service.type_service == 'EXPRESS':
            prix = prix * 2
        
        return prix

class Tournee(models.Model):
    # --- RELATIONS ---
    chauffeur = models.ForeignKey(Chauffeur, on_delete=models.PROTECT)
    vehicule = models.ForeignKey(Vehicule, on_delete=models.PROTECT)
    
    # --- PLANIFICATION ---
    date_depart = models.DateTimeField()
    date_retour_prevue = models.DateTimeField(blank=True, null=True)
    zone_cible = models.CharField(
        max_length=10, 
        choices=Destination.ZONE_LOGISTIQUE_CHOICES
    )
    
    # --- SUIVI OPÉRATIONNEL (Cahier des charges) ---
    kilometrage_depart = models.PositiveIntegerField(blank=True,null=True,help_text="Auto-rempli depuis le véhicule au départ")
    kilometrage_arrivee = models.PositiveIntegerField(blank=True, null=True, help_text="À saisir au retour")
    consommation_carburant = models.DecimalField(
        max_digits=6, decimal_places=2, blank=True, null=True, help_text="En litres"
    )
    
    statut = models.CharField(
        max_length=20, 
        choices=[('PREVUE', 'Prévue'), ('EN_COURS', 'En cours'), ('TERMINEE', 'Terminée')],
        default='PREVUE'
    )

    def __str__(self):
        date_f = self.date_depart.strftime('%d/%m/%Y %H:%M')
        return f"Tournée {self.id} | {date_f} | {self.zone_cible} - {self.statut}"

    def save(self, *args, **kwargs):
        from decimal import Decimal
        from django.utils import timezone
        from .models import TrackingExpedition

        # 0. Détecter le changement de statut pour le tracking
        old_status = None
        if self.pk:
            old_status = Tournee.objects.get(pk=self.pk).statut

        # 1. AUTOMATISATION : Kilométrage et Consommation
        if not self.pk and not self.kilometrage_depart:
            self.kilometrage_depart = self.vehicule.kilometrage

        if self.kilometrage_arrivee and self.kilometrage_depart:
            distance = self.kilometrage_arrivee - self.kilometrage_depart
            # Calcul Decimal pour éviter les erreurs de type avec float
            self.consommation_carburant = (Decimal(distance) / Decimal('100')) * self.vehicule.consommation_moyenne

        # 2. LOGIQUE DE FLUX (Statuts Véhicule et Chauffeur)
        if self.statut in ['PREVUE', 'EN_COURS']:
            self.vehicule.statut = 'EN_TOURNEE'
            self.chauffeur.statut_disponibilite = 'EN_TOURNEE'
        elif self.statut == 'TERMINEE':
            self.vehicule.statut = 'DISPONIBLE'
            self.chauffeur.statut_disponibilite = 'DISPONIBLE'
            if self.kilometrage_arrivee:
                self.vehicule.kilometrage = self.kilometrage_arrivee

        # 3. SAUVEGARDE DES OBJETS LIÉS ET DE LA TOURNÉE
        self.vehicule.save()
        self.chauffeur.save()
        super().save(*args, **kwargs)

        # 4. LOGIQUE AUTOMATIQUE DE TRACKING (BACKEND)
        
        # A. Passage en TRANSIT (Quand la tournée démarre)
        if old_status == 'PREVUE' and self.statut == 'EN_COURS':
            for exp in self.expeditions.all():
                exp.statut = 'EN_TRANSIT'
                exp.save() # Met à jour le statut du colis
                TrackingExpedition.objects.create(
                    expedition=exp, 
                    statut_etape='EN_TRANSIT',
                    commentaire=f"Camion {self.vehicule.numero_immatriculation} en route."
                )

        # B. Clôture de mission (LIVRAISON ou ECHEC/RETOUR)
        elif old_status == 'EN_COURS' and self.statut == 'TERMINEE':
            for exp in self.expeditions.all():
                if exp.statut == 'ECHEC':
                    # On crée l'étape d'échec puis celle du retour physique au dépôt
                    TrackingExpedition.objects.create(
                        expedition=exp, 
                        statut_etape='ECHEC_LIVRAISON', 
                        commentaire="Incident lors de la livraison."
                    )
                    TrackingExpedition.objects.create(
                        expedition=exp, 
                        statut_etape='RETOUR_DEPOT', 
                        commentaire="Colis retourné au dépôt par le chauffeur."
                    )
                else:
                    # Livraison réussie par défaut si pas d'échec marqué
                    exp.statut = 'LIVRE'
                    exp.date_livraison_reelle = timezone.now().date()
                    exp.save()
                    TrackingExpedition.objects.create(
                        expedition=exp, 
                        statut_etape='LIVRE',
                        commentaire="Livraison confirmée à la fermeture de la tournée."
                    )

    def verifier_chargement(self):
        """Déclenche l'étape EN_CHARGEMENT 2h avant le départ"""
        from datetime import timedelta
        from django.utils import timezone
        
        temps_restant = self.date_depart - timezone.now()
        if self.statut == 'PREVUE' and timedelta(hours=0) < temps_restant <= timedelta(hours=2):
            for exp in self.expeditions.all():
                if not exp.historique_tracking.filter(statut_etape='EN_CHARGEMENT').exists():
                    TrackingExpedition.objects.create(
                        expedition=exp, 
                        statut_etape='EN_CHARGEMENT',
                        commentaire="Colis chargé dans le véhicule."
                    )

    def verifier_et_demarrer(self):
        """Vérifie les ressources et démarre la tournée"""
        from django.utils import timezone
        
        est_heure_depart = timezone.now() >= self.date_depart
        chauffeur_pret = self.chauffeur.statut_disponibilite in ['DISPONIBLE', 'EN_TOURNEE']
        vehicule_pret = self.vehicule.statut in ['DISPONIBLE', 'EN_TOURNEE']

        if self.statut == 'PREVUE' and est_heure_depart:
            if chauffeur_pret and vehicule_pret:
                self.statut = 'EN_COURS'
                self.save() # Le save() ci-dessus déclenchera le tracking EN_TRANSIT
                return True, "Tournée démarrée."
            else:
                return False, "Ressources indisponibles (Chauffeur/Véhicule)."
        return False, "Conditions de départ non remplies."

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