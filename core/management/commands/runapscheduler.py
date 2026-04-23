import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from django.core.management.base import BaseCommand
from django_apscheduler.jobstores import DjangoJobStore
from django_apscheduler.models import DjangoJobExecution

from core.scheduler import job_send_alerts, job_send_daily_report

logger = logging.getLogger(__name__)


def delete_old_executions(max_age=604_800):
    """Supprime les exécutions de jobs vieilles de plus de 7 jours."""
    DjangoJobExecution.objects.delete_old_job_executions(max_age)


class Command(BaseCommand):
    help = "Lance le planificateur de tâches automatiques (alertes Telegram, etc.)."

    def handle(self, *args, **options):
        scheduler = BlockingScheduler(timezone="Africa/Abidjan")  # UTC+0, même fuseau que Lomé
        scheduler.add_jobstore(DjangoJobStore(), "default")

        # ── Alertes : tous les jours à 08h00 ─────────────────────────────────
        scheduler.add_job(
            job_send_alerts,
            trigger=CronTrigger(hour=8, minute=0),
            id="send_alerts",
            name="Alertes quotidiennes (stock faible, retards)",
            jobstore="default",
            replace_existing=True,
        )

        # ── Rapport quotidien : tous les jours à 20h00 ───────────────────────
        scheduler.add_job(
            job_send_daily_report,
            trigger=CronTrigger(hour=20, minute=0),
            id="send_daily_report",
            name="Rapport quotidien (ventes + prestations demain)",
            jobstore="default",
            replace_existing=True,
        )

        # ── Nettoyage des anciennes exécutions : tous les lundis à 00h30 ─────
        scheduler.add_job(
            delete_old_executions,
            trigger=CronTrigger(day_of_week="mon", hour=0, minute=30),
            id="delete_old_executions",
            name="Nettoyage des logs d'exécution",
            jobstore="default",
            replace_existing=True,
        )

        self.stdout.write(self.style.SUCCESS("Planificateur démarré :"))
        self.stdout.write("  • Alertes        → chaque jour à 08h00")
        self.stdout.write("  • Rapport du soir → chaque jour à 20h00")
        self.stdout.write("Appuyez sur Ctrl+C pour arrêter.\n")

        try:
            scheduler.start()
        except KeyboardInterrupt:
            scheduler.shutdown()
            self.stdout.write(self.style.WARNING("Planificateur arrêté."))
