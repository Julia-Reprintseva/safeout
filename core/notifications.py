import logging
from twilio.rest import Client as TwilioClient
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from core.config import settings

logger = logging.getLogger(__name__)


def send_sms(to: str, body: str) -> bool:
    if not settings.twilio_account_sid:
        logger.warning("Twilio not configured, skipping SMS to %s", to)
        return False
    try:
        client = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)
        client.messages.create(to=to, from_=settings.twilio_from_number, body=body)
        return True
    except Exception:
        logger.exception("Failed to send SMS to %s", to)
        return False


def send_email(to: str, subject: str, html_body: str) -> bool:
    if not settings.sendgrid_api_key:
        logger.warning("SendGrid not configured, skipping email to %s", to)
        return False
    try:
        sg = SendGridAPIClient(settings.sendgrid_api_key)
        message = Mail(
            from_email=settings.sendgrid_from_email,
            to_emails=to,
            subject=subject,
            html_content=html_body,
        )
        sg.send(message)
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to)
        return False
