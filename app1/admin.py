from django.contrib import admin
from .models import Client, Chauffeur, Vehicule, Destination, TypeService, Tarification, Expedition, Tournee, TrackingExpedition

class TrackingInline(admin.TabularInline):
    model = TrackingExpedition
    extra = 0
    readonly_fields = ['date_evenement', 'statut_etape', 'commentaire']

class ExpeditionAdmin(admin.ModelAdmin):
    readonly_fields = ['montant_total', 'date_livraison_prevue']
    inlines = [TrackingInline]


@admin.register(Tournee)
class TourneeAdmin(admin.ModelAdmin):
    def render_change_form(self, request, context, *args, **kwargs):
        obj = kwargs.get('obj')
        
        # On garde les disponibles OU ceux déjà affectés à cette tournée précise
        vehicules_libres = Vehicule.objects.filter(statut='DISPONIBLE')
        chauffeurs_libres = Chauffeur.objects.filter(statut_disponibilite='DISPONIBLE')

        if obj: # Si on est en train de modifier une tournée existante
            vehicules_libres |= Vehicule.objects.filter(id=obj.vehicule.id)
            chauffeurs_libres |= Chauffeur.objects.filter(id=obj.chauffeur.id)

        context['adminform'].form.fields['vehicule'].queryset = vehicules_libres
        context['adminform'].form.fields['chauffeur'].queryset = chauffeurs_libres
        
        return super().render_change_form(request, context, *args, **kwargs)


admin.site.register(Client)
admin.site.register(Chauffeur)
admin.site.register(Vehicule)
admin.site.register(TypeService)
admin.site.register(Tarification)
admin.site.register(Expedition, ExpeditionAdmin)
admin.site.register(TrackingExpedition)

class DestinationAdmin(admin.ModelAdmin):
    list_display = ['ville', 'wilaya', 'pays', 'zone_geographique', 'tarif_base']
    list_filter = ['zone_geographique', 'zone_logistique']
    search_fields = ['ville', 'wilaya']

admin.site.register(Destination, DestinationAdmin)



