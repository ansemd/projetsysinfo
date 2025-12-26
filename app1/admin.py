from django.contrib import admin
from .models import Client, Chauffeur, Vehicule, Destination, TypeService, Tarification, Tournee, Expedition, TrackingExpedition

# ========== SIMPLE ==========
admin.site.register(Client)
admin.site.register(Chauffeur)
admin.site.register(Vehicule)
admin.site.register(TypeService)
admin.site.register(Tarification)

# ========== DESTINATION ==========
class DestinationAdmin(admin.ModelAdmin):
    list_display = ['ville', 'wilaya', 'pays', 'zone_geographique', 'tarif_base']
    list_filter = ['zone_geographique', 'zone_logistique']
    search_fields = ['ville', 'wilaya']

admin.site.register(Destination, DestinationAdmin)

# ========== TOURNEE ==========
class ExpeditionInline(admin.TabularInline):
    model = Expedition
    extra = 0
    can_delete = False
    fields = ['client', 'destination', 'poids', 'montant_total', 'statut']
    readonly_fields = ['client', 'destination', 'poids', 'montant_total', 'statut']

class TourneeAdmin(admin.ModelAdmin):
    list_display = ['id', 'chauffeur', 'vehicule', 'zone_cible', 'date_depart', 'statut', 'est_privee']
    list_filter = ['statut', 'zone_cible', 'est_privee']
    inlines = [ExpeditionInline]

admin.site.register(Tournee, TourneeAdmin)

# ========== EXPEDITION ==========
class TrackingInline(admin.TabularInline):
    model = TrackingExpedition
    extra = 0
    can_delete = False
    fields = ['statut_etape', 'date_heure', 'commentaire']
    readonly_fields = ['statut_etape', 'date_heure', 'commentaire']

class ExpeditionAdmin(admin.ModelAdmin):
    list_display = ['id', 'client', 'destination', 'tournee', 'poids', 'montant_total', 'statut']
    list_filter = ['statut', 'type_service']
    readonly_fields = ['montant_total', 'date_livraison_prevue']
    inlines = [TrackingInline]

admin.site.register(Expedition, ExpeditionAdmin)

# ========== TRACKING ==========
class TrackingExpeditionAdmin(admin.ModelAdmin):
    list_display = ['get_tournee', 'get_expedition', 'get_statut', 'date_heure']
    list_filter = ['expedition__tournee', 'expedition__statut']
    
    def get_tournee(self, obj):
        return f"Tournée #{obj.expedition.tournee.id}" if obj.expedition.tournee else "Sans tournée"
    get_tournee.short_description = "Tournée"
    
    def get_expedition(self, obj):
        return f"EXP-{obj.expedition.id:06d}"
    get_expedition.short_description = "Expédition"
    
    def get_statut(self, obj):
        return obj.expedition.get_statut_display()
    get_statut.short_description = "Statut"
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False

admin.site.register(TrackingExpedition, TrackingExpeditionAdmin)