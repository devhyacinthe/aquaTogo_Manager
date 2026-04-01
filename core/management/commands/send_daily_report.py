import sys

from django.core.management.base import BaseCommand

from core.reporting import generate_daily_report
from core.telegram_utils import send_telegram_message


class Command(BaseCommand):
    help = "Génère et envoie le résumé quotidien sur Telegram."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Affiche le message sans l'envoyer.",
        )

    def handle(self, *args, **options):
        self.stdout.write("Génération du rapport...")
        report = generate_daily_report()

        if options["dry_run"]:
            sys.stdout.buffer.write(("\n" + report + "\n").encode("utf-8"))
            sys.stdout.buffer.flush()
            self.stdout.write(self.style.WARNING("Mode dry-run : message non envoyé."))
            return

        self.stdout.write("Envoi vers Telegram...")
        success = send_telegram_message(report)

        if success:
            self.stdout.write(self.style.SUCCESS("Rapport envoyé avec succès."))
        else:
            self.stderr.write(self.style.ERROR(
                "Échec de l'envoi. Vérifiez les logs et la config TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID."
            ))
            raise SystemExit(1)
