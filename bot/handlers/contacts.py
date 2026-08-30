import secrets

from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from core.models import TrustedContact
from bot.middlewares.i18n import t
from bot.keyboards.main import contacts_kb, contacts_edit_kb, skip_kb

router = Router()


class AddContact(StatesGroup):
    name = State()
    phone = State()
    email = State()
    username = State()


async def _contacts_text(db, user_id: int, lang: str) -> tuple[str, list]:
    result = await db.execute(
        select(TrustedContact)
        .where(TrustedContact.user_id == user_id)
        .order_by(TrustedContact.priority)
    )
    contacts = result.scalars().all()
    if contacts:
        text = t("contacts_list", lang) + "\n"
        for c in contacts:
            details = []
            if c.phone: details.append(c.phone.replace(" ", ""))
            if c.email: details.append(c.email)
            if c.telegram_username: details.append(f"@{c.telegram_username}")
            elif c.invite_token:
                details.append(t("contact_pending", lang))
            text += f"\n<b>{c.name}</b>\n{' · '.join(details)}\n"
    else:
        text = t("contacts_empty", lang)
    return text, contacts


@router.message(Command("contacts"))
async def cmd_contacts(message: Message, db: AsyncSession, lang: str):
    text, contacts = await _contacts_text(db, message.from_user.id, lang)
    await message.answer(text, reply_markup=contacts_kb(lang, contacts))


@router.callback_query(F.data == "contact:add")
async def start_add_contact(callback: CallbackQuery, state: FSMContext, lang: str):
    await callback.message.answer(t("ask_contact_name", lang))
    await state.set_state(AddContact.name)
    await callback.answer()


@router.message(AddContact.name, F.text, ~F.text.startswith("/"))
async def contact_name(message: Message, state: FSMContext, lang: str):
    await state.update_data(name=message.text.strip())
    await message.answer(t("ask_contact_phone", lang), reply_markup=skip_kb(lang))
    await state.set_state(AddContact.phone)


@router.message(AddContact.phone, F.text, ~F.text.startswith("/"))
async def contact_phone(message: Message, state: FSMContext, lang: str):
    await state.update_data(phone=message.text.strip())
    await message.answer(t("ask_contact_email", lang), reply_markup=skip_kb(lang))
    await state.set_state(AddContact.email)


@router.message(AddContact.email, F.text, ~F.text.startswith("/"))
async def contact_email(message: Message, state: FSMContext, lang: str):
    await state.update_data(email=message.text.strip())
    await message.answer(t("ask_contact_username", lang), reply_markup=skip_kb(lang))
    await state.set_state(AddContact.username)


@router.message(AddContact.username, F.text, ~F.text.startswith("/"))
async def contact_username(message: Message, state: FSMContext, db: AsyncSession, lang: str):
    username = message.text.strip().lstrip("@")
    await _finish_add_contact(
        user_id=message.from_user.id,
        username=username,
        state=state,
        db=db,
        bot=message.bot,
        reply_target=message,
        lang=lang,
    )


@router.callback_query(F.data == "step:skip", StateFilter(AddContact.phone, AddContact.email, AddContact.username))
async def contact_skip(callback: CallbackQuery, state: FSMContext, db: AsyncSession, lang: str):
    current = await state.get_state()
    await callback.answer()

    if current == AddContact.phone:
        await state.update_data(phone=None)
        await callback.message.answer(t("ask_contact_email", lang), reply_markup=skip_kb(lang))
        await state.set_state(AddContact.email)
    elif current == AddContact.email:
        await state.update_data(email=None)
        await callback.message.answer(t("ask_contact_username", lang), reply_markup=skip_kb(lang))
        await state.set_state(AddContact.username)
    elif current == AddContact.username:
        await _finish_add_contact(
            user_id=callback.from_user.id,
            username=None,
            state=state,
            db=db,
            bot=callback.bot,
            reply_target=callback.message,
            lang=lang,
        )


async def _finish_add_contact(user_id, username, state, db, bot, reply_target, lang):
    data = await state.get_data()
    result = await db.execute(select(TrustedContact).where(TrustedContact.user_id == user_id))
    count = len(result.scalars().all())
    invite_token = secrets.token_urlsafe(16)
    contact = TrustedContact(
        user_id=user_id,
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
    bot_user = await bot.get_me()
    invite_link = f"https://t.me/{bot_user.username}?start=trust_{invite_token}"
    await reply_target.answer(t("contact_saved", lang, name=data["name"]))
    await reply_target.answer(t("contact_invite_link", lang, name=data["name"], link=invite_link))


@router.callback_query(lambda c: c.data and c.data.startswith("contact:resend:"))
async def resend_invite(callback: CallbackQuery, db: AsyncSession, lang: str):
    contact_id = int(callback.data.split(":")[2])
    contact = await db.get(TrustedContact, contact_id)
    if not contact or contact.user_id != callback.from_user.id:
        await callback.answer()
        return

    if not contact.invite_token:
        # Already connected — nothing to resend.
        await callback.answer(t("contact_connected", lang), show_alert=True)
        return

    bot_user = await callback.bot.get_me()
    invite_link = f"https://t.me/{bot_user.username}?start=trust_{contact.invite_token}"
    await callback.message.answer(t("contact_invite_link", lang, name=contact.name, link=invite_link))
    await callback.answer()


@router.callback_query(F.data == "contact:edit_mode")
async def contacts_edit_mode(callback: CallbackQuery, db: AsyncSession, lang: str):
    text, contacts = await _contacts_text(db, callback.from_user.id, lang)
    edit_hint = {"ru": "\n\nНажми на имя чтобы удалить контакт:", "en": "\n\nTap a name to remove:", "tr": "\n\nSilmek için isme dokun:"}.get(lang, "")
    await callback.message.edit_text(text + edit_hint, reply_markup=contacts_edit_kb(lang, contacts))
    await callback.answer()


@router.callback_query(F.data == "contact:view_mode")
async def contacts_view_mode(callback: CallbackQuery, db: AsyncSession, lang: str):
    text, contacts = await _contacts_text(db, callback.from_user.id, lang)
    await callback.message.edit_text(text, reply_markup=contacts_kb(lang, contacts))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("contact:delete:"))
async def delete_contact(callback: CallbackQuery, db: AsyncSession, lang: str):
    contact_id = int(callback.data.split(":")[2])
    await db.execute(
        delete(TrustedContact)
        .where(TrustedContact.id == contact_id)
        .where(TrustedContact.user_id == callback.from_user.id)
    )
    await db.commit()
    await callback.answer()
    text, contacts = await _contacts_text(db, callback.from_user.id, lang)
    edit_hint = {"ru": "\n\nНажми на имя чтобы удалить контакт:", "en": "\n\nTap a name to remove:", "tr": "\n\nSilmek için isme dokun:"}.get(lang, "")
    if contacts:
        await callback.message.edit_text(text + edit_hint, reply_markup=contacts_edit_kb(lang, contacts))
    else:
        await callback.message.edit_text(text, reply_markup=contacts_kb(lang, contacts))
