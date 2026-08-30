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


# Checklist item labels (RU only, for contact alerts)
_CHECKLIST_LABELS_RU = {
    "same_person":    "Не тот же человек, что на фото",
    "right_place":    "Встретились не там, где договаривались",
    "route_ok":       "Маршрут не совпадает с планом",
    "no_plan_change": "Он пытается изменить план без согласия",
    "car_matches":    "Машина не та, что была записана",
}


def _get_checklist_problems(user_id: int, session_id: int) -> list[str]:
    """Read problem keys from Redis and return human-readable labels."""
    try:
        redis = celery_app.backend.client
        raw = redis.smembers(f"sc:problems:{user_id}:{session_id}")
        keys = {(v.decode() if isinstance(v, bytes) else v) for v in raw}
        return [_CHECKLIST_LABELS_RU[k] for k in keys if k in _CHECKLIST_LABELS_RU]
    except Exception:
        return []


def _build_contact_message(session_data: dict, level: int, lang: str = "ru", problems: list[str] | None = None) -> str:
    name = session_data.get("user_name", "—")
    place = session_data.get("meeting_place") or "—"
    destination = session_data.get("destination") or "—"
    car = session_data.get("car_plate") or "—"
    profile = session_data.get("date_profile_url")
    date_name = session_data.get("date_name") or "—"
    has_location = session_data.get("has_location", False)
    has_files = session_data.get("has_files", False)

    if level == 0:
        header = f"⚠️ <b>SafeOut:</b> {name} отметила тревожные сигналы во время свидания."
    elif level == 1:
        header = f"⚠️ <b>SafeOut:</b> {name} не отвечает на проверку безопасности."
    else:
        header = f"🆘 <b>SafeOut SOS:</b> {name} нажала кнопку экстренной помощи!"

    profile_line = f'<a href="{profile}">открыть профиль</a>' if profile else "не указан"

    details = (
        f"\n\n<b>──── Данные о свидании ────</b>\n"
        f"👤 <b>Человек:</b> {date_name}\n"
        f"🔗 <b>Профиль:</b> {profile_line}\n"
        f"📍 <b>Место встречи:</b> {place}\n"
        f"🗺 <b>Куда едут:</b> {destination}\n"
        f"🚗 <b>Машина:</b> {car}"
    )

    loc_line = "📌 Геолокация: передана" if has_location else "📌 Геолокация: не передавалась"
    files_line = "📎 Файлы: прикреплены" if has_files else "📎 Файлы: не прикреплялись"
    extra = f"\n\n{loc_line}\n{files_line}"

    notes = session_data.get("notes")
    notes_block = f"\n\n<b>📝 Заметка во время свидания:</b>\n{notes}" if notes else ""

    problems_block = ""
    if problems:
        problems_block = "\n\n<b>⚠️ Отметила в чеклисте:</b>\n" + "\n".join(f"— {p}" for p in problems)

    return header + details + extra + notes_block + problems_block


def _build_contact_keyboard(session_data: dict):
    """Inline keyboard for trusted contact: quick link to chat + call button."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    name = session_data.get("user_name", "её")
    user_tg_id = session_data.get("user_telegram_id")
    user_username = session_data.get("user_username")
    phone = None  # user phone not stored; contact's phone used for SMS only

    buttons = []
    if user_username:
        chat_url = f"https://t.me/{user_username}"
    elif user_tg_id:
        chat_url = f"tg://user?id={user_tg_id}"
    else:
        chat_url = None

    if chat_url:
        buttons.append(InlineKeyboardButton(text="💬 Написать", url=chat_url))

    if not buttons:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def _build_sms_text(session_data: dict, level: int, lang: str = "ru", problems: list[str] | None = None) -> str:
    """Short SMS version (no formatting)."""
    name = session_data.get("user_name", "")
    place = session_data.get("meeting_place", "")
    if level == 1:
        return f"SafeOut: {name} не отвечает на проверку. Место: {place}"
    return f"SafeOut SOS: {name} нажала экстренную кнопку. Место: {place}"


async def _send_user_alert(telegram_id: int, session_id: int, text: str, lang: str):
    """Send an alert message to the user with ping keyboard (for post-escalation warning)."""
    from aiogram import Bot
    from core.ping_messages import short_ping_kb
    bot = Bot(token=settings.bot_token)
    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=text,
            reply_markup=short_ping_kb(session_id, lang),
        )
    finally:
        await bot.session.close()


@celery_app.task(bind=True, max_retries=3)
def ping_user(self, session_id: int, telegram_id: int):
    """Send a check-in ping, then arm the L1 escalation timer for it."""
    from core.bot_api import send_ping  # imported here to avoid circular imports
    logger.info("ping_user: session=%s telegram_id=%s attempt=%s", session_id, telegram_id, self.request.retries)
    try:
        generation = asyncio.run(send_ping(telegram_id, session_id))
    except Exception as exc:
        logger.exception("ping_user failed: session=%s", session_id)
        raise self.retry(exc=exc, countdown=60)

    if generation is not None:
        escalate_l1.apply_async(
            (session_id, generation),
            countdown=settings.escalation_l1_minutes * 60,
        )


@celery_app.task(bind=True, max_retries=3)
def escalate_l1(self, session_id: int, generation: int | None = None, is_sos: bool = False):
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
    user_telegram_id = session_data.get("user_telegram_id")
    problems = _get_checklist_problems(user_telegram_id, session_id) if user_telegram_id else []
    msg_level = 2 if is_sos else 1
    sms_text = _build_sms_text(session_data, level=msg_level, lang=lang, problems=problems)
    subject = (
        "🆘 SafeOut — SOS сигнал" if is_sos else "⚠️ SafeOut — проверка не пройдена"
    ) if lang == "ru" else (
        "🆘 SafeOut — SOS alert" if is_sos else "⚠️ SafeOut — check-in missed"
    )
    tg_text = _build_contact_message(session_data, level=msg_level, lang=lang, problems=problems)
    tg_kb = _build_contact_keyboard(session_data)
    for contact in contacts:
        if contact.get("phone"):
            send_sms(contact["phone"], sms_text)
        if contact.get("email"):
            send_email(contact["email"], subject, _email_html(session_data, url, lang))
        if contact.get("telegram_id"):
            try:
                asyncio.run(notify_telegram_contact(contact["telegram_id"], tg_text, tg_kb))
            except Exception:
                logger.exception("Failed Telegram notify for contact %s", contact.get("telegram_id"))

    # Notify the user that contacts were alerted, keep pings going
    if user_telegram_id:
        alert_text = {
            "ru": (
                "⚠️ Ты не ответила на проверку — я уже написала твоим контактам.\n\n"
                "Если всё хорошо — нажми кнопку ниже. Если нужна помощь — SOS."
            ),
            "en": (
                "⚠️ You missed the check-in — I've already alerted your contacts.\n\n"
                "If you're okay — press the button below. If you need help — SOS."
            ),
            "tr": (
                "⚠️ Kontrolü kaçırdın — kişilerini uyardım.\n\n"
                "Her şey yolundaysa — aşağıdaki düğmeye bas. Yardıma ihtiyacın varsa — SOS."
            ),
        }.get(lang, "⚠️ Check-in missed. Contacts alerted.")
        try:
            asyncio.run(_send_user_alert(user_telegram_id, session_id, alert_text, lang))
        except Exception:
            logger.exception("Failed to notify user after L1 escalation")

        # Keep pinging — reschedule next check-in
        ping_user.apply_async(
            (session_id, user_telegram_id),
            countdown=settings.ping_interval_minutes * 60,
        )

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
    escalate_l1.apply_async((session_id, None, True))  # is_sos=True → level 2 message text
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
