"""
FSM flow for creating and running a date session.

States:
  date_name → profile_url → meeting_place → destination →
  car → extra → return_time → files → [session starts]
"""
import secrets
from datetime import datetime, timedelta, timezone

from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Ordered list of (state_key, question_i18n_key) for back navigation
FLOW_STEPS = [
    ("NewDate:date_name",     "new_date_start"),
    ("NewDate:profile_url",   "ask_profile_url"),
    ("NewDate:meeting_place", "ask_meeting_place"),
    ("NewDate:destination",   "ask_destination"),
    ("NewDate:car",           "ask_car"),
    ("NewDate:extra",         "ask_extra"),
    ("NewDate:return_time",   "ask_return_time"),
]
_FLOW_KEYS = [s for s, _ in FLOW_STEPS]
_FLOW_QUESTIONS = dict(FLOW_STEPS)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from core.models import DateSession, SessionFile, FileType, TrustedContact, SessionStatus, Tubik
from core.config import settings
from core.tasks import escalate_sos, ping_user
from bot.middlewares.i18n import t
from bot.keyboards.main import start_date_kb, active_session_kb, files_done_kb, skip_kb

router = Router()

SKIP_VALUES = {"/skip", "skip"}


class NewDate(StatesGroup):
    date_name = State()
    profile_url = State()
    meeting_place = State()
    destination = State()
    car = State()
    extra = State()
    return_time = State()
    files = State()


class TubikFlow(StatesGroup):
    waiting_name = State()
    waiting_comment = State()


def _parse_return_time(text: str) -> datetime | None:
    """Parse user input like '23:00' or 'через 3 часа' / 'in 3 hours'."""
    text = text.strip().lower()
    now = datetime.utcnow()  # naive UTC — matches TIMESTAMP WITHOUT TIME ZONE column

    # "через N минут/мин" / "in N minutes/min"
    for kw in ["минут", "мин", "minute", "min"]:
        if kw in text:
            try:
                parts = text.split()
                for p in parts:
                    if p.isdigit():
                        return now + timedelta(minutes=int(p))
            except Exception:
                pass

    # "через N часов/час" / "in N hours"
    for template in ["через {} час", "через {} ч", "in {} hour", "in {} h"]:
        if template.split("{}")[0] in text:
            try:
                parts = text.split()
                for p in parts:
                    if p.isdigit():
                        return now + timedelta(hours=int(p))
            except Exception:
                pass

    # "HH:MM"
    for fmt in ("%H:%M", "%H.%M"):
        try:
            t_parsed = datetime.strptime(text, fmt)
            candidate = now.replace(hour=t_parsed.hour, minute=t_parsed.minute, second=0, microsecond=0)
            if candidate < now:
                candidate += timedelta(days=1)
            return candidate
        except ValueError:
            pass

    return None


@router.message(
    StateFilter(
        NewDate.profile_url, NewDate.meeting_place, NewDate.destination,
        NewDate.car, NewDate.extra, NewDate.return_time,
    ),
    Command("back"),
)
async def step_back(message: Message, state: FSMContext, lang: str):
    current = await state.get_state()
    idx = _FLOW_KEYS.index(current) if current in _FLOW_KEYS else -1
    if idx <= 0:
        return
    prev_key = _FLOW_KEYS[idx - 1]
    question_key = _FLOW_QUESTIONS[prev_key]
    await state.set_state(prev_key)
    await message.answer(f"↩️ {t(question_key, lang)}")


MAX_FIELD_LEN = 500


def _truncate(text: str) -> str:
    return text[:MAX_FIELD_LEN] if text else text


@router.message(Command("newdate"))
async def cmd_newdate(message: Message, state: FSMContext, db: AsyncSession, lang: str):
    # Block if there's already an active session
    active = await db.execute(
        select(DateSession)
        .where(DateSession.user_id == message.from_user.id)
        .where(DateSession.status == SessionStatus.ACTIVE)
    )
    active_session = active.scalars().first()
    if active_session:
        await message.answer(t("already_active", lang), reply_markup=active_session_kb(lang, active_session.id))
        return

    # Paywall check
    from core.models import User
    from core.config import settings as cfg
    user_obj = await db.get(User, message.from_user.id)
    is_admin = message.from_user.id == cfg.admin_id
    if user_obj and not user_obj.is_premium and not is_admin and user_obj.sessions_used >= cfg.free_sessions_limit:
        await _show_paywall(message, lang)
        return

    # Warn if no contacts
    result = await db.execute(
        select(TrustedContact).where(TrustedContact.user_id == message.from_user.id)
    )
    contacts = result.scalars().all()
    if not contacts:
        await message.answer(t("no_contacts_warning", lang))

    await message.answer(t("new_date_start", lang))
    await state.set_state(NewDate.date_name)


@router.message(NewDate.date_name, F.text, ~F.text.startswith("/"))
async def step_date_name(message: Message, state: FSMContext, lang: str):
    await state.update_data(date_name=_truncate(message.text.strip()))
    await message.answer(t("ask_profile_url", lang), reply_markup=skip_kb(lang))
    await state.set_state(NewDate.profile_url)


@router.message(NewDate.profile_url, F.text, ~F.text.startswith("/"))
async def step_profile_url(message: Message, state: FSMContext, lang: str):
    await state.update_data(profile_url=_truncate(message.text.strip()))
    await message.answer(t("ask_meeting_place", lang))
    await state.set_state(NewDate.meeting_place)


@router.message(NewDate.meeting_place, F.text, ~F.text.startswith("/"))
async def step_meeting_place(message: Message, state: FSMContext, lang: str):
    await state.update_data(meeting_place=_truncate(message.text.strip()))
    await message.answer(t("ask_destination", lang), reply_markup=skip_kb(lang))
    await state.set_state(NewDate.destination)


@router.message(NewDate.destination, F.text, ~F.text.startswith("/"))
async def step_destination(message: Message, state: FSMContext, lang: str):
    await state.update_data(destination=message.text.strip())
    await message.answer(t("ask_car", lang), reply_markup=skip_kb(lang))
    await state.set_state(NewDate.car)


@router.message(NewDate.car, F.text, ~F.text.startswith("/"))
async def step_car(message: Message, state: FSMContext, lang: str):
    await state.update_data(car=message.text.strip())
    await message.answer(t("ask_extra", lang), reply_markup=skip_kb(lang))
    await state.set_state(NewDate.extra)


@router.message(NewDate.extra, F.text, ~F.text.startswith("/"))
async def step_extra(message: Message, state: FSMContext, lang: str):
    await state.update_data(extra=message.text.strip())
    await message.answer(t("ask_return_time", lang))
    await state.set_state(NewDate.return_time)


@router.callback_query(F.data == "step:skip", StateFilter(NewDate.profile_url, NewDate.destination, NewDate.car, NewDate.extra))
async def step_skip(callback: CallbackQuery, state: FSMContext, db: AsyncSession, lang: str):
    """Handle 'Пропустить' button — advance FSM without saving a value."""
    current = await state.get_state()
    await callback.answer()

    if current == NewDate.profile_url:
        await state.update_data(profile_url=None)
        await callback.message.answer(t("ask_meeting_place", lang))
        await state.set_state(NewDate.meeting_place)
    elif current == NewDate.destination:
        await state.update_data(destination=None)
        await callback.message.answer(t("ask_car", lang), reply_markup=skip_kb(lang))
        await state.set_state(NewDate.car)
    elif current == NewDate.car:
        await state.update_data(car=None)
        await callback.message.answer(t("ask_extra", lang), reply_markup=skip_kb(lang))
        await state.set_state(NewDate.extra)
    elif current == NewDate.extra:
        await state.update_data(extra=None)
        await callback.message.answer(t("ask_return_time", lang))
        await state.set_state(NewDate.return_time)


@router.message(NewDate.return_time, F.text, F.text.func(lambda t: not t.startswith("/") or t.strip().lower() == "/skip"))
async def step_return_time(message: Message, state: FSMContext, db: AsyncSession, lang: str):
    return_dt = _parse_return_time(message.text)
    await state.update_data(return_time=return_dt.isoformat() if return_dt else None)

    data = await state.get_data()

    # Create session in DB
    session_obj = DateSession(
        user_id=message.from_user.id,
        date_name=data.get("date_name"),
        date_profile_url=data.get("profile_url"),
        meeting_place=data.get("meeting_place"),
        destination=data.get("destination"),
        car_plate=data.get("car"),
        extra_info=data.get("extra"),
        expected_return=return_dt,
        alert_token=secrets.token_urlsafe(32),
        status=SessionStatus.PENDING,
    )
    db.add(session_obj)
    await db.commit()
    await db.refresh(session_obj)

    await state.update_data(session_id=session_obj.id)
    await state.set_state(NewDate.files)

    done_msg = await message.answer(
        t("ask_files", lang),
        reply_markup=files_done_kb(lang, session_obj.id),
    )
    await state.update_data(done_msg_id=done_msg.message_id)


async def _handle_file(message: Message, state: FSMContext, db: AsyncSession, file_type: FileType, lang: str):
    data = await state.get_data()
    session_id = data.get("session_id")
    if not session_id:
        return

    if file_type == FileType.PHOTO:
        file_id = message.photo[-1].file_id
        original_name = None
    elif file_type == FileType.VOICE:
        file_id = message.voice.file_id
        original_name = None
    else:
        file_id = message.document.file_id
        original_name = message.document.file_name

    db.add(SessionFile(session_id=session_id, file_type=file_type, s3_key=file_id, original_name=original_name))
    await db.commit()

    # Move the "done" button to the bottom after each new file
    old_msg_id = data.get("done_msg_id")
    if old_msg_id:
        try:
            await message.bot.delete_message(message.chat.id, old_msg_id)
        except Exception:
            pass
    done_msg = await message.answer(
        t("ask_files", lang),
        reply_markup=files_done_kb(lang, session_id),
    )
    await state.update_data(done_msg_id=done_msg.message_id)


@router.message(NewDate.files, F.photo)
async def file_photo(message: Message, state: FSMContext, db: AsyncSession, lang: str):
    await _handle_file(message, state, db, FileType.PHOTO, lang)


@router.message(NewDate.files, F.document)
async def file_document(message: Message, state: FSMContext, db: AsyncSession, lang: str):
    await _handle_file(message, state, db, FileType.DOCUMENT, lang)


@router.message(NewDate.files, F.voice)
async def file_voice(message: Message, state: FSMContext, db: AsyncSession, lang: str):
    await _handle_file(message, state, db, FileType.VOICE, lang)


@router.callback_query(lambda c: c.data and c.data.startswith("files:done:"))
async def files_done(callback: CallbackQuery, state: FSMContext, db: AsyncSession, lang: str):
    session_id = int(callback.data.split(":")[2])
    await callback.message.edit_reply_markup()
    await state.clear()

    # Show checklist before start button — smart check of what's already filled
    from bot.handlers.checklist import show_checklist
    await show_checklist(callback.message, session_id, db, lang)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("session:start:"))
async def start_session(callback: CallbackQuery, db: AsyncSession, lang: str):
    await callback.answer()  # answer first to stop Telegram retries
    session_id = int(callback.data.split(":")[2])
    session_obj = await db.get(DateSession, session_id)
    if not session_obj or session_obj.user_id != callback.from_user.id:
        return
    if session_obj.status == SessionStatus.ACTIVE:
        return  # already started

    result = await db.execute(
        select(TrustedContact).where(TrustedContact.user_id == callback.from_user.id)
    )
    contacts = result.scalars().all()
    if not contacts:
        await callback.message.answer(t("no_reachable_contacts", lang))
        return

    session_obj.status = SessionStatus.ACTIVE
    session_obj.started_at = datetime.utcnow()

    # Increment free sessions counter
    from core.models import User
    user_obj = await db.get(User, callback.from_user.id)
    if user_obj:
        user_obj.sessions_used = (user_obj.sessions_used or 0) + 1

    await db.commit()

    # Schedule first ping; ping_user itself arms the L1 escalation timer
    # once it actually sends that ping (see core/tasks.py).
    ping_user.apply_async(
        (session_id, callback.from_user.id),
        countdown=settings.ping_interval_minutes * 60,
    )

    await callback.message.edit_reply_markup()
    await callback.message.answer(
        t("session_started", lang, interval=settings.ping_interval_minutes),
        reply_markup=active_session_kb(lang, session_id),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("session:sos:"))
async def trigger_sos(callback: CallbackQuery, db: AsyncSession, lang: str):
    session_id = int(callback.data.split(":")[2])
    session_obj = await db.get(DateSession, session_id)
    if not session_obj:
        await callback.answer()
        return

    session_obj.status = SessionStatus.SOS
    await db.commit()

    escalate_sos.delay(session_id)

    await callback.message.answer(t("sos_triggered", lang), reply_markup=active_session_kb(lang, session_id))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("session:end:"))
async def end_session(callback: CallbackQuery, db: AsyncSession, lang: str):
    await callback.answer()  # always answer first to stop Telegram retries
    session_id = int(callback.data.split(":")[2])
    session_obj = await db.get(DateSession, session_id)
    if not session_obj:
        return
    if session_obj.status == SessionStatus.SAFE:
        return  # already ended, ignore duplicate callbacks

    session_obj.status = SessionStatus.SAFE
    session_obj.ended_at = datetime.utcnow()
    await db.commit()

    await callback.message.edit_reply_markup()

    builder = InlineKeyboardBuilder()
    builder.button(text=t("review_fire", lang),  callback_data=f"review:fire:{session_id}")
    builder.button(text=t("review_ok", lang),    callback_data=f"review:ok:{session_id}")
    builder.button(text=t("review_tubik", lang), callback_data=f"review:tubik:{session_id}")
    builder.adjust(3)
    await callback.message.answer(t("safe_return", lang), reply_markup=builder.as_markup())


@router.callback_query(lambda c: c.data and c.data.startswith("ping:ok"))
async def ping_ok(callback: CallbackQuery, db: AsyncSession, lang: str):
    """User confirms they're safe — reschedule next ping."""
    # Find active session for this user
    result = await db.execute(
        select(DateSession)
        .where(DateSession.user_id == callback.from_user.id)
        .where(DateSession.status == SessionStatus.ACTIVE)
        .order_by(DateSession.started_at.desc())
    )
    session_obj = result.scalars().first()

    if session_obj:
        # Invalidate the L1 escalation timer armed for the ping we're
        # acknowledging, then schedule the next ping (which arms its own).
        session_obj.ping_generation += 1
        await db.commit()
        ping_user.apply_async(
            (session_obj.id, callback.from_user.id),
            countdown=settings.ping_interval_minutes * 60,
        )

    await callback.message.edit_reply_markup()
    await callback.message.answer(t("ping_ok_response", lang, interval=settings.ping_interval_minutes))
    await callback.answer()


@router.callback_query(F.data == "ping:sos")
async def ping_sos(callback: CallbackQuery, db: AsyncSession, lang: str):
    """User pressed SOS from ping message."""
    result = await db.execute(
        select(DateSession)
        .where(DateSession.user_id == callback.from_user.id)
        .where(DateSession.status == SessionStatus.ACTIVE)
        .order_by(DateSession.started_at.desc())
    )
    session_obj = result.scalars().first()
    if session_obj:
        # Reuse trigger_sos logic directly
        session_obj.status = SessionStatus.SOS
        await db.commit()
        escalate_sos.delay(session_obj.id)
        await callback.message.answer(t("sos_triggered", lang), reply_markup=active_session_kb(lang, session_obj.id))
        await callback.answer()


@router.message(NewDate.files, F.location)
async def file_location(message: Message, state: FSMContext, db: AsyncSession):
    """Save live location update to session."""
    data = await state.get_data()
    session_id = data.get("session_id")
    if not session_id:
        return
    session_obj = await db.get(DateSession, session_id)
    if session_obj:
        session_obj.last_lat = message.location.latitude
        session_obj.last_lon = message.location.longitude
        session_obj.last_location_at = datetime.utcnow()
        await db.commit()


async def _save_active_location(message: Message, db: AsyncSession):
    result = await db.execute(
        select(DateSession)
        .where(DateSession.user_id == message.from_user.id)
        .where(DateSession.status == SessionStatus.ACTIVE)
        .order_by(DateSession.started_at.desc())
    )
    session_obj = result.scalars().first()
    if session_obj:
        session_obj.last_lat = message.location.latitude
        session_obj.last_lon = message.location.longitude
        session_obj.last_location_at = datetime.utcnow()
        await db.commit()


@router.message(StateFilter(None), F.location)
async def active_location_update(message: Message, db: AsyncSession):
    """Initial location share (live or static) sent outside any FSM flow —
    i.e. while a date is active. Live location keeps arriving as edits, see
    active_location_edit below."""
    await _save_active_location(message, db)


@router.edited_message(F.location)
async def active_location_edit(message: Message, db: AsyncSession):
    """Telegram sends periodic live-location updates as message edits."""
    await _save_active_location(message, db)


# ---------------------------------------------------------------------------
# Отзыв после свидания
# ---------------------------------------------------------------------------

@router.callback_query(lambda c: c.data and c.data.startswith("review:"))
async def handle_review(callback: CallbackQuery, db: AsyncSession, lang: str, state: FSMContext):
    parts = callback.data.split(":")
    verdict = parts[1]
    session_id = int(parts[2])

    session_obj = await db.get(DateSession, session_id)
    if session_obj:
        session_obj.review = verdict
        await db.commit()

    await callback.message.edit_reply_markup()

    if verdict == "tubik":
        await callback.message.answer(t("review_thanks_tubik", lang))
        await state.set_state(TubikFlow.waiting_name)
        await state.update_data(tubik_session_id=session_id)
    elif verdict == "fire":
        await callback.message.answer(t("review_thanks_fire", lang))
    else:
        await callback.message.answer(t("review_thanks_ok", lang))

    await callback.answer()


@router.message(TubikFlow.waiting_name, F.text, F.text.func(lambda t: not t.startswith("/") or t.strip().lower() == "/skip"))
async def tubik_got_name(message: Message, db: AsyncSession, lang: str, state: FSMContext):
    name = message.text.strip()[:256]
    await state.update_data(tubik_name=name)
    await state.set_state(TubikFlow.waiting_comment)
    ask = {"ru": "Что запомнилось? (или /skip)", "en": "What do you remember? (or /skip)", "tr": "Ne aklında kaldı? (veya /skip)"}.get(lang, "Что запомнилось?")
    await message.answer(ask)


@router.message(TubikFlow.waiting_comment, F.text, F.text.func(lambda t: not t.startswith("/") or t.strip().lower() == "/skip"))
async def tubik_got_comment(message: Message, db: AsyncSession, lang: str, state: FSMContext):
    data = await state.get_data()
    comment = None if message.text.strip() == "/skip" else message.text.strip()[:500]
    tubik = Tubik(
        user_id=message.from_user.id,
        name=data["tubik_name"],
        comment=comment,
        date_session_id=data.get("tubik_session_id"),
    )
    db.add(tubik)
    await db.commit()
    await state.clear()
    await message.answer(t("tubik_saved", lang))


@router.message(Command("tubiki"))
async def cmd_tubiki(message: Message, db: AsyncSession, lang: str):
    result = await db.execute(
        select(Tubik)
        .where(Tubik.user_id == message.from_user.id)
        .order_by(Tubik.created_at.desc())
    )
    tubiks = result.scalars().all()

    if not tubiks:
        await message.answer(t("tubik_list_empty", lang))
        return

    for tubik in tubiks:
        date = tubik.created_at.strftime("%d.%m.%Y")
        text = f"<b>{tubik.name}</b> — {date}"
        if tubik.comment:
            text += f"\n{tubik.comment}"

        builder = InlineKeyboardBuilder()
        builder.button(text="🗑 Удалить", callback_data=f"tubik:del:{tubik.id}")
        await message.answer(text, reply_markup=builder.as_markup())


@router.callback_query(lambda c: c.data and c.data.startswith("tubik:del:"))
async def tubik_delete(callback: CallbackQuery, db: AsyncSession, lang: str):
    tubik_id = int(callback.data.split(":")[2])
    tubik = await db.get(Tubik, tubik_id)
    if tubik and tubik.user_id == callback.from_user.id:
        await db.delete(tubik)
        await db.commit()
        await callback.message.delete()
    await callback.answer()


async def _show_paywall(message, lang: str):
    from core.crypto_pay import PRICE_USDT
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    text = {
        "ru": (
            f"🔒 У тебя закончились бесплатные свидания.\n\n"
            f"SafeOut Premium — <b>{PRICE_USDT} USDT/месяц</b>\n"
            f"✓ Безлимитные свидания\n"
            f"✓ Все функции без ограничений\n\n"
            f"Оплата через @CryptoBot (USDT)"
        ),
        "en": (
            f"🔒 You've used all your free dates.\n\n"
            f"SafeOut Premium — <b>{PRICE_USDT} USDT/month</b>\n"
            f"✓ Unlimited dates\n"
            f"✓ All features\n\n"
            f"Pay via @CryptoBot (USDT)"
        ),
    }.get(lang, f"🔒 Free dates used up.\n\nPremium — {PRICE_USDT} USDT/month")

    builder = InlineKeyboardBuilder()
    builder.button(text=f"💳 Оплатить {PRICE_USDT} USDT", callback_data="pay:crypto")
    await message.answer(text, reply_markup=builder.as_markup())


@router.callback_query(F.data == "pay:crypto")
async def pay_crypto(callback: CallbackQuery, lang: str):
    from core.crypto_pay import create_invoice
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    await callback.answer()
    invoice = await create_invoice(callback.from_user.id)
    if not invoice:
        await callback.message.answer("⚠️ Не удалось создать счёт. Попробуй позже.")
        return
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Оплатить в CryptoBot", url=invoice["pay_url"])
    text = {
        "ru": "Нажми кнопку ниже — откроется @CryptoBot для оплаты. После оплаты напиши /newdate.",
        "en": "Tap the button below to pay in @CryptoBot. After payment, type /newdate.",
    }.get(lang, "Tap below to pay.")
    await callback.message.answer(text, reply_markup=builder.as_markup())
