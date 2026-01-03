from django.apps import AppConfig


class App1Config(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app1'

    def ready(self):
        # Importer les signals pour qu'ils soient actifs
        import app1.signals
        from .scheduler import demarrer_scheduler
        demarrer_scheduler()