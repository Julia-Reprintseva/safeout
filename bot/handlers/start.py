from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.models import User, Language, TrustedContact
from bot.middlewares.i18n import t
from bot.keyboards.main import language_kb

router = Router()


async def get_or_create_user(session: AsyncSession, tg_user) -> User:
    result = await session.get(User, tg_user.id)
    if not result:
        lang_code = (tg_user.language_code or "ru")[:2]
        lang = Language(lang_code) if lang_code in ("ru", "en", "tr") else Language.RU
        result = User(
            id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            language=lang,
        )
        session.add(result)
        await session.commit()
    return result


async def _connect_trust_invite(message: Message, db: AsyncSession, token: str, lang: str) -> bool:
    """Handles a /start trust_<token> deep-link: links the clicking user as
    the telegram_id for the trusted contact who was sent this invite.
    Returns True if the payload was handled (so the caller skips /start's
    normal welcome message)."""
    result = await db.execute(
        select(TrustedContact).where(TrustedContact.invite_token == token)
    )
    contact = result.scalars().first()
    if not contact:
        await message.answer(t("trust_link_invalid", lang))
        return True
    if contact.user_id == message.from_user.id:
        await message.answer(t("trust_link_self", lang))
        return True

    contact.telegram_id = message.from_user.id
    contact.invite_token = None
    await db.commit()
    await message.answer(t("trust_link_connected", lang, name=contact.name))

    owner = await db.get(User, contact.user_id)
    owner_lang = owner.language.value if owner else "ru"
    try:
        await message.bot.send_message(
            contact.user_id,
            t("trust_link_owner_notified", owner_lang, name=contact.name),
        )
    except Exception:
        pass
    return True


@router.message(CommandStart())
async def cmd_start(message: Message, db: AsyncSession, lang: str):
    await get_or_create_user(db, message.from_user)

    parts = (message.text or "").split(maxsplit=1)
    payload = parts[1].strip() if len(parts) > 1 else None
    if payload and payload.startswith("trust_"):
        if await _connect_trust_invite(message, db, payload[len("trust_"):], lang):
            return

    user = await db.get(User, message.from_user.id)
    if not user or not user.consent_given:
        builder = InlineKeyboardBuilder()
        builder.button(text=t("consent_accept_btn", lang), callback_data="consent:accept")
        await message.answer(t("consent_notice", lang), reply_markup=builder.as_markup(), parse_mode="HTML")
        return

    await message.answer(t("welcome", lang))


@router.callback_query(lambda c: c.data == "consent:accept")
async def consent_accept(callback: CallbackQuery, db: AsyncSession, lang: str):
    user = await db.get(User, callback.from_user.id)
    if user:
        user.consent_given = True
        await db.commit()
    await callback.message.edit_reply_markup()
    await callback.message.answer(t("consent_accepted", lang) + t("welcome", lang), parse_mode="HTML")
    await callback.answer()


@router.message(Command("language"))
async def cmd_language(message: Message, lang: str):
    await message.answer(t("choose_language", lang), reply_markup=language_kb())


@router.callback_query(lambda c: c.data and c.data.startswith("lang:"))
async def set_language(callback: CallbackQuery, db: AsyncSession):
    lang_code = callback.data.split(":")[1]
    user = await db.get(User, callback.from_user.id)
    if user and lang_code in ("ru", "en", "tr"):
        user.language = Language(lang_code)
        await db.commit()
    await callback.message.edit_text(t("language_set", lang_code))
    await callback.answer()
