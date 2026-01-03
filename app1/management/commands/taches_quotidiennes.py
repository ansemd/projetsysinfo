from django.core.management.base import BaseCommand
from django.utils import timezone
from app1.models import Tournee
from app1.utils import VehiculeService


class Command(BaseCommand):
    help = 'Tâche quotidienne : Matin (8h) ou Soir (17h30)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--mode',
            type=str,
            choices=['matin', 'soir'],
            required=True,
            help='Mode d\'exécution : matin (8h) ou soir (17h30)'
        )

    def handle(self, *args, **options):
        mode = options['mode']
        
        self.stdout.write("=" * 70)
        self.stdout.write(self.style.SUCCESS(f"Tâche quotidienne - Mode: {mode.upper()} - {timezone.now()}"))
        self.stdout.write("=" * 70)
        
        if mode == 'matin':
            self.execution_matin()
        else:
            self.execution_soir()
        
        self.stdout.write("=" * 70)
        self.stdout.write(self.style.SUCCESS("✓ Tâche terminée"))
        self.stdout.write("=" * 70)
    
    
    def execution_matin(self):
        """Exécution du MATIN à 8h"""
        
        # 1. Mettre à jour les tournées
        self.mettre_a_jour_tournees()
        
        # 2. Mettre à jour les factures (statuts EN_RETARD)
        self.mettre_a_jour_factures()
        
        # 3. Gérer les retours de maintenance (J+1, J+2, ...)
        self.gerer_retours_maintenance()
    
    
    def execution_soir(self):
        """Exécution du SOIR à 17h30"""
        
        # Gérer les maintenances du lendemain (J-1)
        self.gerer_maintenance_veille()
    
    
    def mettre_a_jour_tournees(self):
            """Met à jour les statuts des tournées PREVUE → EN_COURS"""
            self.stdout.write("\n--- 1. Mise à jour des tournées ---")
            
            from app1.utils import TourneeService
            
            tournees_a_demarrer = Tournee.objects.filter(
                statut='PREVUE',
                date_depart__lte=timezone.now()
            )
            
            count = 0
            for tournee in tournees_a_demarrer:
                # Vérifier qu'il y a au moins 1 expédition
                peut_demarrer, raison = TourneeService.peut_demarrer(tournee)
                
                if peut_demarrer:
                    self.stdout.write(f"  → Démarrage tournée #{tournee.id} - {tournee.chauffeur}")
                    tournee.statut = 'EN_COURS'
                    tournee.save()
                    count += 1
                else:
                    self.stdout.write(self.style.WARNING(f"  ⚠️ Tournée #{tournee.id} ignorée: {raison}"))
            
            if count > 0:
                self.stdout.write(self.style.SUCCESS(f"✓ {count} tournée(s) passée(s) en EN_COURS"))
            else:
                self.stdout.write(self.style.WARNING("  Aucune tournée à mettre à jour"))

    
    def mettre_a_jour_factures(self):
        """Met à jour les statuts des factures (vérifier échéances)"""
        self.stdout.write("\n--- 2. Mise à jour des factures ---")
        
        from datetime import date
        from app1.models import Facture
        from app1.utils import FacturationService
        
        # Toutes les factures IMPAYEE ou PARTIELLEMENT_PAYEE
        factures_a_verifier = Facture.objects.filter(
            statut__in=['IMPAYEE', 'PARTIELLEMENT_PAYEE'],
            date_echeance__lt=date.today()  # Échéance dépassée
        )
        
        count = 0
        for facture in factures_a_verifier:
            self.stdout.write(f"  → Facture #{facture.id} en retard (échéance: {facture.date_echeance})")
            FacturationService.mettre_a_jour_statut_facture(facture)
            count += 1
        
        if count > 0:
            self.stdout.write(self.style.WARNING(f"⚠️ {count} facture(s) passée(s) en EN_RETARD"))
        else:
            self.stdout.write(self.style.SUCCESS("  Aucune facture en retard"))
    
    
    def gerer_maintenance_veille(self):
        """Gère les maintenances du LENDEMAIN (J-1 à 17h30)"""
        self.stdout.write("\n--- Gestion maintenances de DEMAIN (J-1) ---")
        
        stats = VehiculeService.gerer_maintenance_veille_soir()
        
        if stats['notifications_vehicule_en_tournee'] > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"  ⚠️ {stats['notifications_vehicule_en_tournee']} véhicule(s) en tournée - notification créée"
                )
            )
        
        if stats['notifications_confirmation'] > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"  ✓ {stats['notifications_confirmation']} notification(s) de confirmation créée(s)"
                )
            )
        
        if sum(stats.values()) == 0:
            self.stdout.write(self.style.WARNING("  Aucune maintenance prévue demain"))
    
    
    def gerer_retours_maintenance(self):
        """Gère les retours de maintenance (J+1, J+2, ... à 8h)"""
        self.stdout.write("\n--- 3. Vérification retours de maintenance ---")
        
        stats = VehiculeService.gerer_retour_maintenance_matin()
        
        if stats['notifications_retour'] > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"  ✓ {stats['notifications_retour']} notification(s) de retour créée(s)"
                )
            )
        else:
            self.stdout.write(self.style.WARNING("  Aucun véhicule en attente de retour"))