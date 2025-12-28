from django.contrib import admin
from django.shortcuts import redirect
from django.db.models import Max
from .models import Client, Chauffeur, Vehicule, Destination, TypeService, Tarification, Tournee, Expedition, TrackingExpedition, Facture, Paiement

# ========== CLIENT ==========
class ClientAdmin(admin.ModelAdmin):
    list_display = ['get_id', 'nom', 'prenom', 'solde']
    search_fields = ['nom', 'prenom', 'email']
    
    def get_id(self, obj):
        return f"CL-{obj.id:03d}"
    get_id.short_description = "ID"
    get_id.admin_order_field = 'id'

admin.site.register(Client, ClientAdmin)

# ========== CHAUFFEUR ==========
class ChauffeurAdmin(admin.ModelAdmin):
    list_display = ['get_id', 'nom', 'prenom', 'statut_disponibilite']
    list_filter = ['statut_disponibilite']
    search_fields = ['nom', 'prenom']
    
    def get_id(self, obj):
        return f"CH-{obj.id:03d}"
    get_id.short_description = "ID"
    get_id.admin_order_field = 'id'

admin.site.register(Chauffeur, ChauffeurAdmin)

# ========== VEHICULE ==========
class VehiculeAdmin(admin.ModelAdmin):
    list_display = ['numero_immatriculation', 'marque', 'modele', 'type_vehicule', 'statut']
    search_fields = ['numero_immatriculation', 'marque', 'modele']

admin.site.register(Vehicule, VehiculeAdmin)

# ========== DESTINATION ==========
class DestinationAdmin(admin.ModelAdmin):
    list_display = ['ville', 'wilaya', 'pays', 'zone_geographique', 'tarif_base']
    list_filter = ['zone_geographique', 'zone_logistique']
    search_fields = ['ville', 'wilaya']

admin.site.register(Destination, DestinationAdmin)

# ========== TYPE SERVICE ==========
class TypeServiceAdmin(admin.ModelAdmin):
    list_display = ['type_service', 'description']

admin.site.register(TypeService, TypeServiceAdmin)

# ========== TARIFICATION ==========
class TarificationAdmin(admin.ModelAdmin):
    list_display = ['destination', 'type_service', 'tarif_poids', 'tarif_volume']

admin.site.register(Tarification, TarificationAdmin)

# ========== TOURNEE ==========
class ExpeditionInline(admin.TabularInline):
    model = Expedition
    extra = 0
    can_delete = False
    fields = ['get_numero', 'client', 'destination', 'poids', 'montant_total', 'statut']
    readonly_fields = ['get_numero', 'client', 'destination', 'poids', 'montant_total', 'statut']
    
    def get_numero(self, obj):
        return obj.get_numero_expedition() if obj.id else "Nouveau"
    get_numero.short_description = "N° Expédition"

class TourneeAdmin(admin.ModelAdmin):
    list_display = ['zone_cible', 'chauffeur', 'vehicule', 'date_depart', 'statut', 'est_privee']
    list_filter = ['statut', 'zone_cible', 'est_privee']
    inlines = [ExpeditionInline]

admin.site.register(Tournee, TourneeAdmin)

# ========== EXPEDITION ==========
class HistoriqueInline(admin.TabularInline):
    model = TrackingExpedition
    extra = 0
    can_delete = False  # ← Garde False
    fields = ['statut_etape', 'date_heure', 'commentaire']
    readonly_fields = ['statut_etape', 'date_heure', 'commentaire']
    verbose_name = "Étape de suivi"
    verbose_name_plural = "Historique complet"
    
    def has_add_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return True  
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.order_by('-date_heure')

class ExpeditionAdmin(admin.ModelAdmin):
    list_display = ['get_numero_expedition', 'client', 'destination', 'tournee', 'poids', 'montant_total', 'statut']
    list_filter = ['statut', 'type_service']
    readonly_fields = ['montant_total', 'date_livraison_prevue']
    search_fields = ['client__nom', 'client__prenom', 'nom_destinataire']
    inlines = [HistoriqueInline]
    
    def get_numero_expedition(self, obj):
        return obj.get_numero_expedition() if obj.id else "Nouveau"
    get_numero_expedition.short_description = "N° Expédition"
    get_numero_expedition.admin_order_field = 'id'

admin.site.register(Expedition, ExpeditionAdmin)

# ========== TRACKING ==========
class TrackingExpeditionAdmin(admin.ModelAdmin):
    list_display = ['get_expedition', 'get_tournee', 'get_statut', 'date_heure']
    list_filter = ['expedition__tournee', 'expedition__statut']
    search_fields = ['expedition__client__nom', 'expedition__nom_destinataire']
    
    def get_expedition(self, obj):
        return f"EXP-{obj.expedition.id:06d}"
    get_expedition.short_description = "Expédition"
    get_expedition.admin_order_field = 'expedition__id'
    
    def get_tournee(self, obj):
        if obj.expedition.tournee:
            return f"Tournée #{obj.expedition.tournee.id}"
        return "Sans tournée"
    get_tournee.short_description = "Tournée"
    
    def get_statut(self, obj):
        return obj.expedition.get_statut_display()
    get_statut.short_description = "Statut"
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return True
    
    def change_view(self, request, object_id, form_url='', extra_context=None):
        """Rediriger vers la page Expédition pour voir l'historique"""
        tracking = self.get_object(request, object_id)
        return redirect(f'/admin/app1/expedition/{tracking.expedition.id}/change/')
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        derniers_ids = TrackingExpedition.objects.values('expedition').annotate(
            dernier_id=Max('id')
        ).values_list('dernier_id', flat=True)
        return qs.filter(id__in=derniers_ids)

admin.site.register(TrackingExpedition, TrackingExpeditionAdmin)

# ========== SECTION 3 : FACTURATION ==========

class PaiementInline(admin.TabularInline):
    """
    Inline pour afficher les paiements dans la page d'administration d'une facture
    """
    model = Paiement
    extra = 0
    fields = ['montant_paye', 'mode_paiement', 'statut', 'date_paiement', 'reference_transaction']
    readonly_fields = ['date_paiement']


class FactureAdmin(admin.ModelAdmin):
    """
    Configuration de l'administration des factures
    """
    list_display = ['numero_facture', 'client', 'montant_ttc', 'get_montant_restant', 'statut', 'date_creation', 'date_echeance']
    list_filter = ['statut', 'date_creation']
    search_fields = ['numero_facture', 'client__nom', 'client__prenom']
    readonly_fields = ['numero_facture', 'montant_ht', 'montant_tva', 'montant_ttc', 'date_creation']
    inlines = [PaiementInline]
    
    def get_montant_restant(self, obj):
        """Afficher le montant restant à payer"""
        from .utils import FacturationService
        return f"{FacturationService.calculer_montant_restant(obj)} DA"
    get_montant_restant.short_description = "Reste à payer"


class PaiementAdmin(admin.ModelAdmin):
    """
    Configuration de l'administration des paiements
    """
    list_display = ['facture', 'client', 'montant_paye', 'mode_paiement', 'statut', 'date_paiement']
    list_filter = ['mode_paiement', 'statut', 'date_paiement']
    search_fields = ['facture__numero_facture', 'client__nom', 'reference_transaction']
    readonly_fields = ['date_paiement']


admin.site.register(Facture, FactureAdmin)
admin.site.register(Paiement, PaiementAdmin)