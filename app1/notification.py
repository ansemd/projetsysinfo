"""
Service d'envoi d'emails pour les alertes et notifications
"""

from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from threading import Thread


class EmailService:
    """
    Service centralisé pour l'envoi d'emails
    """
    
    @staticmethod
    def send_async_email(subject, message, recipient_list, html_message=None):
        """
        Envoie un email de manière asynchrone (sans bloquer l'application)
        """
        def send():
            try:
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=recipient_list,
                    html_message=html_message,
                    fail_silently=False,
                )
            except Exception as e:
                print(f"Erreur envoi email: {e}")
        
        # Lancer l'envoi dans un thread séparé
        Thread(target=send).start()
    
    @staticmethod
    def envoyer_email_avec_template(template_name, context, subject, recipient_list):
        """
        Envoie un email en utilisant un template HTML Django
        
        Args:
            template_name: chemin vers le template (ex: 'emails/alerte_incident.html')
            context: dictionnaire de variables pour le template
            subject: sujet de l'email
            recipient_list: liste d'adresses email
        """
        # Rendre le template HTML
        html_content = render_to_string(template_name, context)
        
        # Version texte (sans HTML)
        text_content = strip_tags(html_content)
        
        # Créer l'email
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipient_list
        )
        
        # Attacher la version HTML
        email.attach_alternative(html_content, "text/html")
        
        # Envoyer de manière asynchrone
        def send():
            try:
                email.send()
            except Exception as e:
                print(f"Erreur envoi email: {e}")
        
        Thread(target=send).start()


class AlerteEmailService:
    """
    Service spécialisé pour les emails d'alertes (incidents et réclamations)
    """
    
    @staticmethod
    def envoyer_alerte_incident_direction(incident):
        """
        Envoie une alerte email à la direction pour un incident
        """
        # Emails de la direction (à configurer dans settings.py)
        emails_direction = getattr(settings, 'EMAILS_DIRECTION', ['direction@transport.dz'])
        
        # Déterminer l'urgence selon la sévérité
        urgence_emoji = {
            'CRITIQUE': '🚨',
            'ELEVEE': '⚠️',
            'MOYENNE': '⚡',
            'FAIBLE': 'ℹ️'
        }
        
        emoji = urgence_emoji.get(incident.severite, 'ℹ️')
        
        # Sujet de l'email
        subject = f"{emoji} ALERTE INCIDENT {incident.severite} - {incident.get_type_incident_display()}"
        
        # Corps de l'email
        message = f"""
{emoji} ALERTE INCIDENT - Niveau {incident.severite}

Incident N° : {incident.numero_incident}
Type : {incident.get_type_incident_display()}
Sévérité : {incident.severite}
Statut : {incident.get_statut_display()}

TITRE : {incident.titre}

DESCRIPTION :
{incident.description}

DÉTAILS :
- Date/Heure : {incident.date_heure_incident.strftime('%d/%m/%Y à %H:%M')}
- Lieu : {incident.lieu_incident or 'Non spécifié'}
- Signalé par : {incident.signale_par}
"""
        
        # Ajouter les infos expédition si disponible
        if incident.expedition:
            message += f"""
EXPÉDITION CONCERNÉE :
- N° Expédition : {incident.expedition.get_numero_expedition()}
- Client : {incident.expedition.client}
- Destination : {incident.expedition.destination.ville}, {incident.expedition.destination.wilaya}
- Statut actuel : {incident.expedition.get_statut_display()}
"""
        
        # Ajouter les infos tournée si disponible
        if incident.tournee:
            message += f"""
TOURNÉE CONCERNÉE :
- Tournée N° : {incident.tournee.id}
- Chauffeur : {incident.tournee.chauffeur}
- Véhicule : {incident.tournee.vehicule}
- Zone : {incident.tournee.get_zone_cible_display()}
- Statut : {incident.tournee.get_statut_display()}
"""
        
        # Coût estimé
        if incident.cout_estime and incident.cout_estime > 0:
            message += f"\nCOÛT ESTIMÉ : {incident.cout_estime:,.2f} DA"
        
        message += f"""

---
Action requise : Cet incident nécessite votre attention immédiate.
Consultez le système pour plus de détails et pour entreprendre les actions nécessaires.

Plateforme de gestion : {settings.SITE_URL}
"""
        
        # Envoyer l'email
        EmailService.send_async_email(
            subject=subject,
            message=message,
            recipient_list=emails_direction
        )
    
    @staticmethod
    def envoyer_alerte_incident_client(incident):
        """
        Envoie une alerte email au client pour un incident sur son expédition
        """
        if not incident.expedition:
            return
        
        client = incident.expedition.client
        
        # Vérifier que le client a un email
        if not client.email:
            print(f"Client {client} n'a pas d'email configuré")
            return
        
        # Sujet selon le type d'incident
        sujets = {
            'RETARD': f"Retard sur votre expédition {incident.expedition.get_numero_expedition()}",
            'PERTE': f"URGENT - Incident sur votre expédition {incident.expedition.get_numero_expedition()}",
            'ENDOMMAGEMENT': f"Incident sur votre expédition {incident.expedition.get_numero_expedition()}",
            'PROBLEME_TECHNIQUE': f"Retard technique - Expédition {incident.expedition.get_numero_expedition()}",
        }
        
        subject = sujets.get(
            incident.type_incident, 
            f"Information sur votre expédition {incident.expedition.get_numero_expedition()}"
        )
        
        # Corps de l'email
        message = f"""
Bonjour {client.prenom} {client.nom},

Nous vous informons qu'un incident a été signalé concernant votre expédition.

DÉTAILS DE L'EXPÉDITION :
- N° Expédition : {incident.expedition.get_numero_expedition()}
- Destination : {incident.expedition.destination.ville}, {incident.expedition.destination.wilaya}
- Destinataire : {incident.expedition.nom_destinataire}

INCIDENT :
- Type : {incident.get_type_incident_display()}
- Date : {incident.date_heure_incident.strftime('%d/%m/%Y à %H:%M')}

DESCRIPTION :
{incident.description}
"""
        
        # Message personnalisé selon le type
        if incident.type_incident == 'RETARD':
            message += """
Nous mettons tout en œuvre pour livrer votre colis dans les plus brefs délais.
Nous vous tiendrons informé de l'évolution de la situation.
"""
        elif incident.type_incident == 'PERTE':
            message += """
Nos équipes ont lancé une recherche immédiate de votre colis.
Vous serez contacté dans les 24h pour un point de situation et les démarches de compensation.
"""
        elif incident.type_incident == 'ENDOMMAGEMENT':
            message += """
Nous sommes désolés pour ce désagrément.
Nos équipes vous contacteront rapidement pour évaluer les dommages et vous proposer une solution adaptée.
"""
        
        message += f"""

Pour toute question, vous pouvez nous contacter :
- Email : support@transport.dz
- Téléphone : +213 XX XX XX XX XX

Nous nous excusons pour la gêne occasionnée et restons à votre disposition.

Cordialement,
L'équipe Transport & Livraison

---
Ceci est un email automatique, merci de ne pas y répondre directement.
"""
        
        # Envoyer l'email
        EmailService.send_async_email(
            subject=subject,
            message=message,
            recipient_list=[client.email]
        )
    
    @staticmethod
    def envoyer_notification_nouvelle_reclamation(reclamation):
        """
        Notifie l'équipe support d'une nouvelle réclamation
        """
        emails_support = getattr(settings, 'EMAILS_SUPPORT', ['support@transport.dz'])
        
        # Emoji selon la priorité
        priority_emoji = {
            'URGENTE': '🔥',
            'HAUTE': '⚠️',
            'NORMALE': '📋',
            'BASSE': 'ℹ️'
        }
        
        emoji = priority_emoji.get(reclamation.priorite, '📋')
        
        subject = f"{emoji} Nouvelle réclamation {reclamation.priorite} - {reclamation.numero_reclamation}"
        
        message = f"""
{emoji} NOUVELLE RÉCLAMATION

N° Réclamation : {reclamation.numero_reclamation}
Client : {reclamation.client.prenom} {reclamation.client.nom}
Nature : {reclamation.get_nature_display()}
Priorité : {reclamation.priorite}

OBJET :
{reclamation.objet}

DESCRIPTION :
{reclamation.description}

Date de création : {reclamation.date_creation.strftime('%d/%m/%Y à %H:%M')}
"""
        
        # Ajouter les expéditions concernées
        if reclamation.expeditions.exists():
            message += "\nEXPÉDITIONS CONCERNÉES :\n"
            for exp in reclamation.expeditions.all():
                message += f"- {exp.get_numero_expedition()} → {exp.destination.ville}\n"
        
        # Ajouter la facture si présente
        if reclamation.facture:
            message += f"\nFACTURE : {reclamation.facture.numero_facture} - {reclamation.facture.montant_ttc} DA\n"
        
        message += """

Action requise : Cette réclamation doit être traitée rapidement.
Connectez-vous au système pour l'assigner et la traiter.
"""
        
        EmailService.send_async_email(
            subject=subject,
            message=message,
            recipient_list=emails_support
        )
    
    @staticmethod
    def envoyer_reponse_reclamation_client(reclamation):
        """
        Informe le client qu'une réponse a été apportée à sa réclamation
        """
        client = reclamation.client
        
        if not client.email:
            print(f"Client {client} n'a pas d'email configuré")
            return
        
        subject = f"Réponse à votre réclamation {reclamation.numero_reclamation}"
        
        message = f"""
Bonjour {client.prenom} {client.nom},

Nous avons le plaisir de vous informer qu'une réponse a été apportée à votre réclamation.

VOTRE RÉCLAMATION :
- N° : {reclamation.numero_reclamation}
- Nature : {reclamation.get_nature_display()}
- Objet : {reclamation.objet}
- Date : {reclamation.date_creation.strftime('%d/%m/%Y')}

NOTRE RÉPONSE :
{reclamation.reponse_agent}

SOLUTION PROPOSÉE :
{reclamation.solution_proposee}
"""
        
        if reclamation.compensation_accordee and reclamation.montant_compensation > 0:
            message += f"""
COMPENSATION :
Un avoir de {reclamation.montant_compensation:,.2f} DA a été crédité sur votre compte client.
"""
        
        message += """

Si cette réponse vous convient, aucune action n'est requise de votre part.
Si vous souhaitez des précisions supplémentaires, n'hésitez pas à nous recontacter.

Cordialement,
L'équipe Service Client

---
Email : support@transport.dz
Téléphone : +213 XX XX XX XX XX
"""
        
        EmailService.send_async_email(
            subject=subject,
            message=message,
            recipient_list=[client.email]
        )
    
    @staticmethod
    def envoyer_confirmation_resolution_reclamation(reclamation):
        """
        Confirme au client que sa réclamation est résolue
        """
        client = reclamation.client
        
        if not client.email:
            return
        
        subject = f"Réclamation résolue - {reclamation.numero_reclamation}"
        
        message = f"""
Bonjour {client.prenom} {client.nom},

Nous vous confirmons que votre réclamation a été traitée et résolue.

RÉCLAMATION :
- N° : {reclamation.numero_reclamation}
- Nature : {reclamation.get_nature_display()}
- Date de création : {reclamation.date_creation.strftime('%d/%m/%Y')}
- Date de résolution : {reclamation.date_resolution.strftime('%d/%m/%Y')}
- Délai de traitement : {reclamation.delai_traitement_jours} jour(s)
"""
        
        if reclamation.compensation_accordee:
            message += f"""
COMPENSATION ACCORDÉE : {reclamation.montant_compensation:,.2f} DA
Ce montant a été crédité sur votre compte.
"""
        
        message += """

Nous espérons que cette résolution vous satisfait pleinement.
Votre satisfaction est notre priorité.

Si vous le souhaitez, vous pouvez évaluer notre traitement de votre réclamation 
en vous connectant à votre espace client.

Nous vous remercions de votre confiance.

Cordialement,
L'équipe Transport & Livraison
"""
        
        EmailService.send_async_email(
            subject=subject,
            message=message,
            recipient_list=[client.email]
        )


# ========== EMAILS POUR LES EXPÉDITIONS ==========

class ExpeditionEmailService:
    """
    Service d'emails pour les expéditions
    """
    
    @staticmethod
    def envoyer_confirmation_expedition(expedition):
        """
        Envoie une confirmation de création d'expédition au client
        """
        client = expedition.client
        
        if not client.email:
            return
        
        subject = f"Confirmation expédition {expedition.get_numero_expedition()}"
        
        message = f"""
Bonjour {client.prenom} {client.nom},

Votre expédition a été enregistrée avec succès dans notre système.

DÉTAILS DE L'EXPÉDITION :
- N° Expédition : {expedition.get_numero_expedition()}
- Type de service : {expedition.type_service.type_service}
- Date de création : {expedition.date_creation.strftime('%d/%m/%Y à %H:%M')}

DESTINATAIRE :
- Nom : {expedition.nom_destinataire}
- Téléphone : {expedition.telephone_destinataire}
- Adresse : {expedition.adresse_destinataire}
- Destination : {expedition.destination.ville}, {expedition.destination.wilaya}

COLIS :
- Poids : {expedition.poids} kg
- Volume : {expedition.volume} m³
- Description : {expedition.description or 'Non spécifiée'}

TARIFICATION :
- Montant : {expedition.montant_total:,.2f} DA
"""
        
        if expedition.date_livraison_prevue:
            message += f"- Livraison prévue : {expedition.date_livraison_prevue.strftime('%d/%m/%Y')}\n"
        
        if expedition.tournee:
            message += f"\nVotre colis a été affecté à la tournée #{expedition.tournee.id}\n"
            message += f"Départ prévu : {expedition.tournee.date_depart.strftime('%d/%m/%Y à %H:%M')}\n"
        
        message += """

Vous pouvez suivre votre colis en temps réel sur notre plateforme.

Merci de votre confiance !

Cordialement,
L'équipe Transport & Livraison
"""
        
        EmailService.send_async_email(
            subject=subject,
            message=message,
            recipient_list=[client.email]
        )
    
    @staticmethod
    def envoyer_notification_livraison(expedition):
        """
        Notifie le client que son colis a été livré
        """
        client = expedition.client
        
        if not client.email:
            return
        
        subject = f"Colis livré - {expedition.get_numero_expedition()}"
        
        message = f"""
Bonjour {client.prenom} {client.nom},

Bonne nouvelle ! Votre colis a été livré avec succès.

N° Expédition : {expedition.get_numero_expedition()}
Destinataire : {expedition.nom_destinataire}
Destination : {expedition.destination.ville}, {expedition.destination.wilaya}
Date de livraison : {expedition.date_livraison_reelle.strftime('%d/%m/%Y') if expedition.date_livraison_reelle else 'Aujourd\'hui'}

Nous espérons que le service vous a satisfait.

Si vous constatez un problème, n'hésitez pas à nous contacter immédiatement.

Merci de votre confiance !

Cordialement,
L'équipe Transport & Livraison
"""
        
        EmailService.send_async_email(
            subject=subject,
            message=message,
            recipient_list=[client.email]
        )