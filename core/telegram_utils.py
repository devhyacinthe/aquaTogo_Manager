import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def send_telegram_message(message: str) -> bool:
    """
    Envoie un message au chat Telegram configuré.
    Retourne True si l'envoi a réussi, False sinon.
    """
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
    chat_id = getattr(settings, "TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        logger.error("TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID non configuré dans settings.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
    }

    try:
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            logger.error("Telegram API error: %s", data)
            return False
        return True
    except requests.exceptions.Timeout:
        logger.error("Timeout lors de l'envoi du message Telegram.")
        return False
    except requests.exceptions.RequestException as exc:
        logger.error("Erreur lors de l'envoi du message Telegram : %s", exc)
        return False
