import logging

from core.alerts import generate_alerts_message
from core.reporting import generate_sales_report, generate_services_report
from core.telegram_utils import send_telegram_message

logger = logging.getLogger(__name__)


def job_send_alerts():
    """Vérifie et envoie les alertes Telegram (stock faible, retards de paiement)."""
    try:
        message = generate_alerts_message(overdue_days=30)
        if message is None:
            logger.info("send_alerts : aucune alerte à envoyer.")
            return
        ok = send_telegram_message(message)
        if ok:
            logger.info("send_alerts : alertes envoyées avec succès.")
        else:
            logger.error("send_alerts : échec de l'envoi Telegram.")
    except Exception:
        logger.exception("send_alerts : erreur inattendue.")


def job_send_daily_report():
    """Envoie le rapport des ventes du jour puis les prestations de demain."""
    try:
        ok1 = send_telegram_message(generate_sales_report())
        ok2 = send_telegram_message(generate_services_report())
        if ok1 and ok2:
            logger.info("send_daily_report : rapport envoyé avec succès.")
        else:
            logger.error("send_daily_report : échec de l'envoi d'un ou plusieurs messages.")
    except Exception:
        logger.exception("send_daily_report : erreur inattendue.")
