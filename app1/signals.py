"""
Signals pour créer automatiquement les tarifications
quand on crée une nouvelle destination dans l'admin
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Destination, TypeService, Tarification


@receiver(post_save, sender=Destination)
def creer_tarifications_automatiquement(sender, instance, created, **kwargs):
    """
    Dès qu'une nouvelle Destination est créée,
    on crée automatiquement ses tarifications
    """
    
    # Seulement si c'est une NOUVELLE destination (pas une modification)
    if created:
        
        if instance.zone_geographique == 'INTERNATIONALE':
            # Destination internationale → INTERNATIONAL uniquement
            international = TypeService.objects.get(type_service='INTERNATIONAL')
            Tarification.objects.get_or_create(
                destination=instance,
                type_service=international,
                defaults={
                    'tarif_poids': 25.00,
                    'tarif_volume': 50.00
                }
            )
        
        else:
            # Destination nationale → STANDARD et EXPRESS
            standard = TypeService.objects.get(type_service='STANDARD')
            express = TypeService.objects.get(type_service='EXPRESS')
            
            Tarification.objects.get_or_create(
                destination=instance,
                type_service=standard,
                defaults={
                    'tarif_poids': 10.00,
                    'tarif_volume': 20.00
                }
            )
            
            Tarification.objects.get_or_create(
                destination=instance,
                type_service=express,
                defaults={
                    'tarif_poids': 10.00,
                    'tarif_volume': 20.00
                }
            )