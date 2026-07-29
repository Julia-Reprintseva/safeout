import secrets

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from core.models import TrustedContact
from bot.middlewares.i18n import t
from bot.keyboards.main import contacts_kb

router = Router()


class AddContact(StatesGroup):
    name = State()
    phone = State()
    email = State()
    username = State()


@router.message(Command("contacts"))
async def cmd_contacts(message: Message, db: AsyncSession, lang: str):
    result = await db.execute(
        select(TrustedContact)
        .where(TrustedContact.user_id == message.from_user.id)
        .order_by(TrustedContact.priority)
    )
    contacts = result.scalars().all()

    if contacts:
        text = t("contacts_list", lang) + "\n\n"
        for c in contacts:
            channels = []
            if c.phone:
                channels.append(f"📱 {c.phone}")
            if c.email:
                channels.append(f"✉️ {c.email}")
            if c.telegram_username:
                channels.append(f"💬 @{c.telegram_username}")
            if c.telegram_id:
                channels.append(t("contact_connected", lang))
            elif c.invite_token:
                channels.append(t("contact_pending", lang))
            text += f"• {c.name}: {', '.join(channels)}\n"
    else:
        text = t("contacts_empty", lang)

    await message.answer(text, reply_markup=contacts_kb(lang, contacts))


@router.callback_query(F.data == "contact:add")
async def start_add_contact(callback: CallbackQuery, state: FSMContext, lang: str):
    await callback.message.answer(t("ask_contact_name", lang))
    await state.set_state(AddContact.name)
    await callback.answer()


@router.message(AddContact.name)
async def contact_name(message: Message, state: FSMContext, lang: str):
    await state.update_data(name=message.text.strip())
    await message.answer(t("ask_contact_phone", lang))
    await state.set_state(AddContact.phone)


@router.message(AddContact.phone)
async def contact_phone(message: Message, state: FSMContext, lang: str):
    value = None if message.text.strip().lower() in ("/skip", "skip") else message.text.strip()
    await state.update_data(phone=value)
    await message.answer(t("ask_contact_email", lang))
    await state.set_state(AddContact.email)


@router.message(AddContact.email)
async def contact_email(message: Message, state: FSMContext, lang: str):
    value = None if message.text.strip().lower() in ("/skip", "skip") else message.text.strip()
    await state.update_data(email=value)
    await message.answer(t("ask_contact_username", lang))
    await state.set_state(AddContact.username)


@router.message(AddContact.username)
async def contact_username(message: Message, state: FSMContext, db: AsyncSession, lang: str):
    raw = message.text.strip()
    username = None if raw.lower() in ("/skip", "skip") else raw.lstrip("@")
    data = await state.get_data()

    # Count existing contacts for priority
    result = await db.execute(
        select(TrustedContact).where(TrustedContact.user_id == message.from_user.id)
    )
    count = len(result.scalars().all())

    # telegram_username is just a label — it lets us show a t.me/<username>
    # link (e.g. in the "call this contact" action) even before they connect.
    # It does NOT let the bot message them: a bot can't message a user who
    # has never started a chat with it, so we still send an invite deep-link
    # and fill telegram_id in automatically once they press Start.
    invite_token = secrets.token_urlsafe(16)
    contact = TrustedContact(
        user_id=message.from_user.id,
        name=data["name"],
        phone=data.get("phone"),
        email=data.get("email"),
        telegram_username=username,
        telegram_id=None,
        invite_token=invite_token,
        priority=count + 1,
    )
    db.add(contact)
    await db.commit()
    await state.clear()

    bot_user = await message.bot.get_me()
    invite_link = f"https://t.me/{bot_user.username}?start=trust_{invite_token}"
    await message.answer(t("contact_saved", lang, name=data["name"]))
    await message.answer(t("contact_invite_link", lang, name=data["name"], link=invite_link))


@router.callback_query(lambda c: c.data and c.data.startswith("contact:delete:"))
async def delete_contact(callback: CallbackQuery, db: AsyncSession, lang: str):
    contact_id = int(callback.data.split(":")[2])
    await db.execute(
        delete(TrustedContact)
        .where(TrustedContact.id == contact_id)
        .where(TrustedContact.user_id == callback.from_user.id)
    )
    await db.commit()
    await callback.answer("Удалено")
    await cmd_contacts.__wrapped__(callback.message, db, lang)
