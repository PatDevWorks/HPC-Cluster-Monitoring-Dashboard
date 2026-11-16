
import os
import requests
from typing import Optional
import time
import logging

logger = logging.getLogger(__name__)

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


class EmailDeliveryError(Exception):
    """Raised when a transactional email cannot be sent."""


def send_transactional_email(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None,
) -> str:
    """
    Send a transactional email through Brevo.

    Returns the Brevo message ID.
    Never logs or returns the API key or email contents.
    """

    api_key = os.getenv("BREVO_API_KEY", "").strip()
    sender_email = os.getenv("BREVO_SENDER_EMAIL", "").strip()
    sender_name = os.getenv("BREVO_SENDER_NAME", "").strip()

    # Validate required configuration.
    if not all([api_key, sender_email, sender_name]):
        raise EmailDeliveryError(
            "Email service is not fully configured."
        )

    if not to_email or "@" not in to_email:
        raise EmailDeliveryError("Invalid recipient email address.")

    payload = {
        "sender": {
            "name": sender_name,
            "email": sender_email,
        },
        "to": [
            {"email": to_email}
        ],
        "subject": subject,
        "htmlContent": html_content,
    }

    if text_content:
        payload["textContent"] = text_content

    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json",
    }

    
    try:
        start_time = time.perf_counter()

        response = requests.post(
            BREVO_API_URL,
            json=payload,
            headers=headers,
            timeout=20,
        )

        elapsed = time.perf_counter() - start_time

        logger.info(
            "Brevo email API responded in %.2f seconds (HTTP %s)",
            elapsed,
            response.status_code
        )

        if response.status_code not in (200, 201):
            raise EmailDeliveryError(
                f"Brevo rejected the email request "
                f"(HTTP {response.status_code})."
            )

        result = response.json()
        message_id = result.get("messageId")

        if not message_id:
            raise EmailDeliveryError(
                "Brevo did not return a message ID."
            )

        return message_id

    except requests.Timeout:
        raise EmailDeliveryError(
            "Brevo email request timed out."
        ) from None

    except requests.RequestException:
        raise EmailDeliveryError(
            "Could not connect to Brevo."
        ) from None
