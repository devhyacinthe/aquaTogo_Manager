import sys

from django.core.management.base import BaseCommand

from core.reporting import generate_sales_report, generate_services_report
from core.telegram_utils import send_telegram_message


class Command(BaseCommand):
    help = "Génère et envoie le résumé quotidien sur Telegram (2 messages)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Affiche les messages sans les envoyer.",
        )

    def handle(self, *args, **options):
        self.stdout.write("Génération des rapports...")
        sales_report = generate_sales_report()
        services_report = generate_services_report()

        if options["dry_run"]:
            for report in (sales_report, services_report):
                sys.stdout.buffer.write(("\n" + report + "\n").encode("utf-8"))
                sys.stdout.buffer.flush()
            self.stdout.write(self.style.WARNING("Mode dry-run : messages non envoyés."))
            return

        self.stdout.write("Envoi vers Telegram...")
        ok1 = send_telegram_message(sales_report)
        ok2 = send_telegram_message(services_report)

        if ok1 and ok2:
            self.stdout.write(self.style.SUCCESS("2 messages envoyés avec succès."))
        else:
            self.stderr.write(self.style.ERROR(
                "Échec d'un ou plusieurs envois. Vérifiez TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID."
            ))
            raise SystemExit(1)
