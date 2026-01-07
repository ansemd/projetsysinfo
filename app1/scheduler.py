from apscheduler.schedulers.background import BackgroundScheduler # type: ignore
from django.core.management import call_command

def executer_taches_matin():
    """Exécute les tâches du matin à 8h"""
    print("Exécution tâches du MATIN (8h)")
    call_command('taches_quotidiennes', '--mode=matin')

def executer_taches_soir():
    """Exécute les tâches du soir à 17h30"""
    print("Exécution tâches du SOIR (17h30)")
    call_command('taches_quotidiennes', '--mode=soir')

def demarrer_scheduler():
    """Démarre le scheduler avec 2 exécutions par jour"""
    scheduler = BackgroundScheduler()
    
    scheduler.add_job(
        executer_taches_matin,
        'cron',
        hour=8,
        minute=0,
        id='taches_matin'
    )
    
    scheduler.add_job(
        executer_taches_soir,
        'cron',
        hour=17,
        minute=30,
        id='taches_soir'
    )
    
    # ✅ AJOUTER CES 2 LIGNES ICI :
    print("🚀 Exécution initiale des tâches du matin...")
    executer_taches_matin()
    
    scheduler.start()
    print("Scheduler démarré : 8h (matin) et 17h30 (soir)")