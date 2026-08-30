"""
Helper functions called from Celery tasks to send messages via Bot API.
Uses httpx (sync) since Celery workers are not async.
"""
from core.config import settings

BOT_API = f"https://api.telegram.org/bot{settings.bot_token}"


async def send_ping(telegram_id: int, session_id: int) -> int | None:
    """Send a check-in ping to the user.

    Returns the session's current ping_generation if the ping was sent, or
    None if the session is no longer active (in which case the caller should
    not arm an escalation timer for it).
    """
    from core.database import async_session_factory, engine
    from core.models import User, DateSession, SessionStatus

    try:
        async with async_session_factory() as db:
            session = await db.get(DateSession, session_id)
            if not session or session.status != SessionStatus.ACTIVE:
                return None
            user = await db.get(User, telegram_id)
            lang = user.language.value if user else "ru"
            generation = session.ping_generation
    finally:
        await engine.dispose()

    from aiogram import Bot
    bot = Bot(token=settings.bot_token)
    try:
        from core.ping_messages import SHORT_QUESTIONS, short_ping_kb
        await bot.send_message(
            chat_id=telegram_id,
            text=SHORT_QUESTIONS[lang],
            reply_markup=short_ping_kb(session_id, lang),
        )
    finally:
        await bot.session.close()

    return generation


async def notify_telegram_contact(telegram_id: int, text: str, reply_markup=None):
    """Send alert message to a trusted contact on Telegram."""
    from aiogram import Bot
    bot = Bot(token=settings.bot_token)
    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=reply_markup,
        )
    finally:
        await bot.session.close()
