import sys

from django.core.management.base import BaseCommand

from core.alerts import generate_alerts_message
from core.telegram_utils import send_telegram_message


class Command(BaseCommand):
    help = "Détecte les alertes (retards de paiement, stock faible) et les envoie sur Telegram."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Affiche le message sans l'envoyer.",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Seuil de retard de paiement en jours (défaut : 30).",
        )

    def handle(self, *args, **options):
        self.stdout.write("Analyse des alertes...")
        message = generate_alerts_message(overdue_days=options["days"])

        if message is None:
            self.stdout.write(self.style.SUCCESS("Aucune alerte à envoyer."))
            return

        if options["dry_run"]:
            sys.stdout.buffer.write(("\n" + message + "\n").encode("utf-8"))
            sys.stdout.buffer.flush()
            self.stdout.write(self.style.WARNING("Mode dry-run : message non envoyé."))
            return

        self.stdout.write("Envoi vers Telegram...")
        success = send_telegram_message(message)

        if success:
            self.stdout.write(self.style.SUCCESS("Alertes envoyées avec succès."))
        else:
            self.stderr.write(self.style.ERROR(
                "Échec de l'envoi. Vérifiez TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID."
            ))
            raise SystemExit(1)
