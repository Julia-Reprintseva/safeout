"""
Celery tasks for SafeOut.

Escalation flow:
  ping_user      — sent every PING_INTERVAL_MINUTES while session is active;
                    on send, arms escalate_l1 for the ping it just sent.
  escalate_l1    — fires ESCALATION_L1_MINUTES after a ping if the user hasn't
                    acknowledged a *later* ping since (checked via
                    ping_generation — see core/models.py); notifies contacts.
  escalate_l2    — fires if L1 wasn't resolved; notifies support orgs.
  escalate_sos   — user-triggered: fires L1 unconditionally + L2 immediately.
"""
import asyncio
import logging

from celery import Celery

from core.config import settings
from core.notifications import send_sms, send_email

logger = logging.getLogger(__name__)

celery_app = Celery("safeout", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.timezone = "UTC"


def _alert_page_url(token: str) -> str:
    return f"{settings.app_base_url}/alert/{token}"


def _build_sms_text(session_data: dict, level: int, lang: str = "ru") -> str:
    name = session_data.get("user_name", "")
    place = session_data.get("meeting_place", "")
    url = _alert_page_url(session_data["alert_token"])

    if lang == "ru":
        if level == 1:
            return (
                f"⚠️ SafeOut: {name} не отвечает на проверку.\n"
                f"Место встречи: {place}\n"
                f"Все данные: {url}"
            )
        return (
            f"🆘 SafeOut SOS: {name} нажала кнопку ЭКСТРЕННОЙ ПОМОЩИ.\n"
            f"Место: {place}\n"
            f"Данные: {url}"
        )
    # English fallback
    if level == 1:
        return (
            f"⚠️ SafeOut: {name} is not responding to check-in.\n"
            f"Meeting place: {place}\n"
            f"Details: {url}"
        )
    return (
        f"🆘 SafeOut SOS: {name} pressed the EMERGENCY button.\n"
        f"Location: {place}\n"
        f"Details: {url}"
    )


@celery_app.task(bind=True, max_retries=3)
def ping_user(self, session_id: int, telegram_id: int):
    """Send a check-in ping, then arm the L1 escalation timer for it."""
    from core.bot_api import send_ping  # imported here to avoid circular imports
    try:
        generation = asyncio.run(send_ping(telegram_id, session_id))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)

    if generation is not None:
        escalate_l1.apply_async(
            (session_id, generation),
            countdown=settings.escalation_l1_minutes * 60,
        )


@celery_app.task(bind=True, max_retries=3)
def escalate_l1(self, session_id: int, generation: int | None = None):
    """Level 1: notify all trusted contacts (SMS + email + Telegram).

    `generation` ties this call to the ping that armed it. If the user has
    since acknowledged a later ping, ping_generation has moved on and this
    is a stale no-op. escalate_sos passes generation=None to force it.
    """
    from core.bot_api import notify_telegram_contact  # circular-safe import
    from core.db_sync import get_escalation_context

    ctx = get_escalation_context(session_id)
    if not ctx or ctx["status"] in ("safe", "cancelled"):
        return
    if generation is not None and ctx["ping_generation"] != generation:
        return

    session_data = ctx["session_data"]
    contacts = session_data.get("contacts", [])
    url = _alert_page_url(session_data["alert_token"])
    lang = session_data.get("lang", "ru")
    sms_text = _build_sms_text(session_data, level=1, lang=lang)
    subject = "⚠️ SafeOut — проверка не пройдена" if lang == "ru" else "⚠️ SafeOut — check-in missed"

    for contact in contacts:
        if contact.get("phone"):
            send_sms(contact["phone"], sms_text)
        if contact.get("email"):
            send_email(contact["email"], subject, _email_html(session_data, url, lang))
        if contact.get("telegram_id"):
            try:
                asyncio.run(notify_telegram_contact(contact["telegram_id"], sms_text))
            except Exception:
                logger.exception("Failed Telegram notify for contact %s", contact.get("telegram_id"))

    # Schedule L2 if no acknowledgement within window
    escalate_l2.apply_async(
        (session_id,),
        countdown=settings.escalation_l2_minutes * 60,
    )


@celery_app.task(bind=True, max_retries=3)
def escalate_l2(self, session_id: int):
    """Level 2: notify support organisations (Liza Alert, etc.)."""
    from core.db_sync import get_escalation_context

    ctx = get_escalation_context(session_id)
    if not ctx or ctx["status"] in ("safe", "cancelled"):
        return

    session_data = ctx["session_data"]
    orgs = _get_org_contacts(session_data.get("country", "ru"))
    lang = session_data.get("lang", "ru")
    url = _alert_page_url(session_data["alert_token"])
    subject = "🆘 SafeOut — запрос помощи" if lang == "ru" else "🆘 SafeOut — help request"

    for org in orgs:
        if org.get("email"):
            send_email(org["email"], subject, _email_html(session_data, url, lang, org_mode=True))
        if org.get("phone"):
            send_sms(org["phone"], _build_sms_text(session_data, level=2, lang=lang))


@celery_app.task
def escalate_sos(session_id: int):
    """Immediate SOS: fire all levels simultaneously, ignoring ping generation."""
    escalate_l1.apply_async((session_id, None))
    escalate_l2.apply_async((session_id,), countdown=0)


def _get_org_contacts(country: str) -> list[dict]:
    """Returns hardcoded org contacts by country. Extend as needed."""
    orgs = {
        "ru": [
            {"name": "Liza Alert", "email": "info@lizaalert.org", "phone": None},
            {"name": "Кризисный центр помощи женщинам", "email": "anna@anna.org.ru", "phone": None},
        ],
        "tr": [
            {"name": "İstanbul Kadın Kuruluşları Birliği", "email": "info@ikk.org.tr", "phone": None},
        ],
    }
    return orgs.get(country, orgs["ru"])


def _email_html(session_data: dict, url: str, lang: str, org_mode: bool = False) -> str:
    name = session_data.get("user_name", "")
    place = session_data.get("meeting_place", "")
    date_name = session_data.get("date_name", "")
    car = session_data.get("car_plate", "")
    dest = session_data.get("destination", "")
    hotel = session_data.get("hotel_info", "")

    if lang == "ru":
        intro = (
            f"<b>{'Организация' if org_mode else 'Доверенный контакт'},</b><br><br>"
            f"Пользователь SafeOut <b>{name}</b> не прошёл(а) проверку. "
            f"Возможно, она нуждается в помощи.<br><br>"
        )
    else:
        intro = (
            f"<b>{'Organization' if org_mode else 'Trusted contact'},</b><br><br>"
            f"SafeOut user <b>{name}</b> missed their check-in. "
            f"They may need assistance.<br><br>"
        )

    details = f"""
    <table>
      <tr><td><b>Место встречи</b></td><td>{place}</td></tr>
      <tr><td><b>Куда едут</b></td><td>{dest}</td></tr>
      <tr><td><b>Отель/адрес</b></td><td>{hotel}</td></tr>
      <tr><td><b>Человек</b></td><td>{date_name}</td></tr>
      <tr><td><b>Машина</b></td><td>{car}</td></tr>
    </table>
    <br>
    <a href="{url}" style="background:#e53935;color:white;padding:12px 24px;
       text-decoration:none;border-radius:6px;font-weight:bold;">
      {'Открыть все данные' if lang == 'ru' else 'View all details'}
    </a>
    """
    return f"<html><body>{intro}{details}</body></html>"
