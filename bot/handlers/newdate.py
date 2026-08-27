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
from sqlalchemy import select

from core.models import DateSession, SessionFile, FileType, TrustedContact, SessionStatus
from core.config import settings
from core.tasks import escalate_sos, ping_user
from bot.middlewares.i18n import t
from bot.keyboards.main import start_date_kb, active_session_kb, files_done_kb

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


@router.message(Command("newdate"))
async def cmd_newdate(message: Message, state: FSMContext, db: AsyncSession, lang: str):
    # Warn if no contacts
    result = await db.execute(
        select(TrustedContact).where(TrustedContact.user_id == message.from_user.id)
    )
    contacts = result.scalars().all()
    if not contacts:
        await message.answer(t("no_contacts_warning", lang))

    await message.answer(t("new_date_start", lang))
    await state.set_state(NewDate.date_name)


@router.message(NewDate.date_name)
async def step_date_name(message: Message, state: FSMContext, lang: str):
    await state.update_data(date_name=message.text.strip())
    await message.answer(t("ask_profile_url", lang))
    await state.set_state(NewDate.profile_url)


@router.message(NewDate.profile_url)
async def step_profile_url(message: Message, state: FSMContext, lang: str):
    val = None if message.text.strip().lower() in SKIP_VALUES else message.text.strip()
    await state.update_data(profile_url=val)
    await message.answer(t("ask_meeting_place", lang))
    await state.set_state(NewDate.meeting_place)


@router.message(NewDate.meeting_place)
async def step_meeting_place(message: Message, state: FSMContext, lang: str):
    await state.update_data(meeting_place=message.text.strip())
    await message.answer(t("ask_destination", lang))
    await state.set_state(NewDate.destination)


@router.message(NewDate.destination)
async def step_destination(message: Message, state: FSMContext, lang: str):
    val = None if message.text.strip().lower() in SKIP_VALUES else message.text.strip()
    await state.update_data(destination=val)
    await message.answer(t("ask_car", lang))
    await state.set_state(NewDate.car)


@router.message(NewDate.car)
async def step_car(message: Message, state: FSMContext, lang: str):
    val = None if message.text.strip().lower() in SKIP_VALUES else message.text.strip()
    await state.update_data(car=val)
    await message.answer(t("ask_extra", lang))
    await state.set_state(NewDate.extra)


@router.message(NewDate.extra)
async def step_extra(message: Message, state: FSMContext, lang: str):
    val = None if message.text.strip().lower() in SKIP_VALUES else message.text.strip()
    await state.update_data(extra=val)
    await message.answer(t("ask_return_time", lang))
    await state.set_state(NewDate.return_time)


@router.message(NewDate.return_time)
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

    await message.answer(
        t("ask_files", lang),
        reply_markup=files_done_kb(lang, session_obj.id),
    )


async def _handle_file(message: Message, state: FSMContext, db: AsyncSession, file_type: FileType):
    data = await state.get_data()
    session_id = data.get("session_id")
    if not session_id:
        return

    # Store Telegram's own file_id rather than re-uploading to S3/R2 (not
    # configured by default). api/routes.py proxies it through the Bot API
    # when rendering the alert page for trusted contacts.
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
    await message.react([])  # acknowledge silently


@router.message(NewDate.files, F.photo)
async def file_photo(message: Message, state: FSMContext, db: AsyncSession):
    await _handle_file(message, state, db, FileType.PHOTO)


@router.message(NewDate.files, F.document)
async def file_document(message: Message, state: FSMContext, db: AsyncSession):
    await _handle_file(message, state, db, FileType.DOCUMENT)


@router.message(NewDate.files, F.voice)
async def file_voice(message: Message, state: FSMContext, db: AsyncSession):
    await _handle_file(message, state, db, FileType.VOICE)


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
    session_id = int(callback.data.split(":")[2])
    session_obj = await db.get(DateSession, session_id)
    if not session_obj or session_obj.user_id != callback.from_user.id:
        await callback.answer("Сессия не найдена")
        return

    result = await db.execute(
        select(TrustedContact).where(TrustedContact.user_id == callback.from_user.id)
    )
    contacts = result.scalars().all()
    if not any(c.phone or c.telegram_id for c in contacts):
        await callback.answer(t("no_reachable_contacts", lang), show_alert=True)
        return

    session_obj.status = SessionStatus.ACTIVE
    session_obj.started_at = datetime.now(timezone.utc)
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
    await callback.answer()


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

    await callback.message.answer(t("sos_triggered", lang))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("session:end:"))
async def end_session(callback: CallbackQuery, db: AsyncSession, lang: str):
    session_id = int(callback.data.split(":")[2])
    session_obj = await db.get(DateSession, session_id)
    if not session_obj:
        await callback.answer()
        return

    session_obj.status = SessionStatus.SAFE
    session_obj.ended_at = datetime.now(timezone.utc)
    await db.commit()

    await callback.message.answer(t("safe_return", lang))
    await callback.answer()


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
        await trigger_sos.__wrapped__(callback, db, lang)


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
        session_obj.last_location_at = datetime.now(timezone.utc)
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
        session_obj.last_location_at = datetime.now(timezone.utc)
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
