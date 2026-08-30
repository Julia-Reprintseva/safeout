"""
During-date status check — sent with every ping.

Flow:
  ping arrives → short check (3 questions + buttons)
    "Всё ок"       → reschedule next ping
    "Есть проблема" → full checklist, then suggest action
    "SOS"           → immediate escalation

Full checklist (/status command or after "Есть проблема"):
  Block 1 — Reality matches promises
  Block 2 — How you feel right now
  Block 3 — His behaviour

After full checklist: bot counts red flags and suggests action.
"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.models import DateSession, SessionStatus, TrustedContact
from core.config import settings

router = Router()


class NoteFlow(StatesGroup):
    waiting_note = State()


async def _ack_ping(db: AsyncSession, session_id: int):
    """Bump ping_generation so the L1 escalation timer armed for the ping
    being acknowledged becomes stale and no-ops (see core/tasks.py)."""
    session_obj = await db.get(DateSession, session_id)
    if session_obj:
        session_obj.ping_generation += 1
        await db.commit()


# ---------------------------------------------------------------------------
# Checklist definition
# ---------------------------------------------------------------------------
STATUS_CHECKS: list[dict] = [
    {
        "key": "same_person",
        "block": 1,
        "ru": "Это тот же человек, что на фото",
        "en": "He looks like his photos",
        "tr": "Fotoğraftaki kişiyle aynı",
        "red_flag": True,
    },
    {
        "key": "right_place",
        "block": 1,
        "ru": "Вы встретились там, где договаривались",
        "en": "You met where you agreed",
        "tr": "Anlaştığınız yerde buluştunuz",
        "red_flag": True,
    },
    {
        "key": "route_ok",
        "block": 1,
        "ru": "Маршрут совпадает с тем, что планировали",
        "en": "The route matches what was planned",
        "tr": "Güzergah planlandığı gibi",
        "red_flag": True,
    },
    {
        "key": "no_plan_change",
        "block": 1,
        "ru": "Он не пытается изменить план без твоего согласия",
        "en": "He's not trying to change plans without your agreement",
        "tr": "Planı senin rızan olmadan değiştirmeye çalışmıyor",
        "red_flag": True,
    },
    {
        "key": "car_matches",
        "block": 1,
        "ru": "Машина та же, что ты записала",
        "en": "The car matches what you noted",
        "tr": "Araç kaydettiğinle aynı",
        "red_flag": True,
    },
]

BLOCK_TITLES = {
    1: {"ru": "📍 Реальность совпадает с обещанным",  "en": "📍 Reality matches promises",    "tr": "📍 Gerçeklik söylenenlere uyuyor"},
    2: {"ru": "💛 Твои ощущения прямо сейчас",        "en": "💛 How you feel right now",        "tr": "💛 Şu an nasıl hissediyorsun"},
    3: {"ru": "🔍 Его поведение",                     "en": "🔍 His behaviour",                 "tr": "🔍 Onun davranışı"},
}

from core.ping_messages import SHORT_QUESTIONS, short_ping_kb  # noqa: F401
from bot.keyboards.main import active_session_kb

CONCERN_QUESTION = {
    "ru": "Хорошо, не волнуйся. Что именно тебя беспокоит?",
    "en": "Okay, take a breath. What specifically is worrying you?",
    "tr": "Tamam, derin bir nefes al. Seni tam olarak ne endişelendiriyor?",
}

ACTIONS = {
    "ru": {
        "call_friend":   "📞 Позвонить подруге прямо сейчас",
        "full_check":    "📋 Пройти полный чек-лист",
        "note_and_go":   "📝 Записать и продолжить — я слежу",
        "sos":           "🆘 SOS — нужна срочная помощь",
    },
    "en": {
        "call_friend":   "📞 Call a friend right now",
        "full_check":    "📋 Go through full checklist",
        "note_and_go":   "📝 Note it and continue — I'm watching",
        "sos":           "🆘 SOS — I need urgent help",
    },
    "tr": {
        "call_friend":   "📞 Şimdi bir arkadaşı ara",
        "full_check":    "📋 Tam kontrol listesini geç",
        "note_and_go":   "📝 Not al ve devam et — izliyorum",
        "sos":           "🆘 SOS — acil yardıma ihtiyacım var",
    },
}

RESULT_MESSAGES = {
    "safe": {
        "ru": "✅ Хорошо! Всё под контролем. Следующая проверка через {interval} минут.",
        "en": "✅ Great! Everything looks fine. Next check-in in {interval} minutes.",
        "tr": "✅ Harika! Her şey yolunda görünüyor. Sonraki kontrol {interval} dakika sonra.",
    },
    "concern": {
        "ru": (
            "⚠️ Я вижу {count} тревожных сигналов.\n\n"
            "Доверяй своей интуиции — если что-то кажется неправильным, скорее всего так и есть.\n\n"
            "Что хочешь сделать?"
        ),
        "en": (
            "⚠️ I see {count} warning sign(s).\n\n"
            "Trust your instincts — if something feels off, it probably is.\n\n"
            "What do you want to do?"
        ),
        "tr": (
            "⚠️ {count} uyarı işareti görüyorum.\n\n"
            "İçgüdülerine güven — bir şey yanlış hissettiriyorsa, muhtemelen öyledir.\n\n"
            "Ne yapmak istersin?"
        ),
    },
    "danger": {
        "ru": (
            "🚨 Серьёзные тревожные сигналы ({count} пунктов).\n\n"
            "Твоя безопасность важнее всего. "
            "Попробуй оказаться среди людей — кафе, магазин, улица.\n\n"
            "Что делаем?"
        ),
        "en": (
            "🚨 Serious warning signs ({count} items).\n\n"
            "Your safety matters most. "
            "Try to get around other people — café, shop, street.\n\n"
            "What do we do?"
        ),
        "tr": (
            "🚨 Ciddi uyarı işaretleri ({count} madde).\n\n"
            "Güvenliğin her şeyden önemli. "
            "İnsanların arasına girmeye çalış — kafe, dükkan, cadde.\n\n"
            "Ne yapıyoruz?"
        ),
    },
}


async def _notify_contacts_soft(db: AsyncSession, user_id: int, session_id: int, lang: str):
    """Send a soft alert to all Telegram contacts when checklist shows red flags."""
    from core.db_sync import get_escalation_context
    from core.tasks import _get_checklist_problems, _build_contact_message, _build_contact_keyboard
    import asyncio

    def _run():
        ctx = get_escalation_context(session_id)
        if not ctx:
            return
        session_data = ctx["session_data"]
        problems = _get_checklist_problems(user_id, session_id)
        text = _build_contact_message(session_data, level=0, lang=lang, problems=problems)
        kb = _build_contact_keyboard(session_data)
        contacts = session_data.get("contacts", [])
        for contact in contacts:
            if contact.get("telegram_id"):
                try:
                    import asyncio as _asyncio
                    from core.bot_api import notify_telegram_contact
                    _asyncio.run(notify_telegram_contact(contact["telegram_id"], text, kb))
                except Exception:
                    pass

    import asyncio as asyncio_mod
    await asyncio_mod.get_event_loop().run_in_executor(None, _run)


def _checklist_header(lang: str) -> str:
    return {"ru": "Отметь что не так — нажми на пункт. Когда готова — Готово.",
            "en": "Tap what's wrong. When done — press Done.",
            "tr": "Yanlış olanı işaretle. Hazır olunca — Tamam."}[lang]


def _checklist_kb(session_id: int, problems: set, lang: str):
    """problems = set of item keys the user marked as NOT okay."""
    builder = InlineKeyboardBuilder()
    builder.button(text=BLOCK_TITLES[1][lang], callback_data="sc:noop")
    for item in STATUS_CHECKS:
        mark = "❌" if item["key"] in problems else "✅"
        builder.button(text=f"{mark} {item[lang]}", callback_data=f"sc:tog:{session_id}:{item['key']}")
    done_label = {"ru": "✔️ Готово", "en": "✔️ Done", "tr": "✔️ Tamam"}[lang]
    builder.button(text=done_label, callback_data=f"sc:submit:{session_id}")
    builder.adjust(1)
    return builder.as_markup()


def action_kb(session_id: int, lang: str):
    builder = InlineKeyboardBuilder()
    acts = ACTIONS[lang]
    builder.button(text=acts["call_friend"], callback_data=f"sc:action:{session_id}:call_friend")
    builder.button(text=acts["full_check"],  callback_data=f"sc:full:{session_id}")
    builder.button(text=acts["note_and_go"], callback_data=f"sc:action:{session_id}:note_and_go")
    builder.button(text=acts["sos"],         callback_data=f"sc:sos:{session_id}")
    builder.adjust(1)
    return builder.as_markup()



def _get_redis():
    from core.tasks import celery_app
    return celery_app.backend.client


def _redis_key(user_id: int, session_id: int) -> str:
    return f"sc:problems:{user_id}:{session_id}"


def _get_problems(user_id: int, session_id: int) -> set:
    redis = _get_redis()
    raw = redis.smembers(_redis_key(user_id, session_id))
    return {(v.decode() if isinstance(v, bytes) else v) for v in raw}


def _toggle_problem(user_id: int, session_id: int, key: str):
    redis = _get_redis()
    rk = _redis_key(user_id, session_id)
    if redis.sismember(rk, key):
        redis.srem(rk, key)
    else:
        redis.sadd(rk, key)
    redis.expire(rk, 86400)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

@router.callback_query(lambda c: c.data and c.data.startswith("sc:ok:"))
async def sc_ok(callback: CallbackQuery, db: AsyncSession, lang: str):
    session_id = int(callback.data.split(":")[2])

    await _ack_ping(db, session_id)
    from core.tasks import ping_user
    ping_user.apply_async(
        (session_id, callback.from_user.id),
        countdown=settings.ping_interval_minutes * 60,
    )

    text = RESULT_MESSAGES["safe"][lang].format(interval=settings.ping_interval_minutes)
    await callback.message.edit_text(text, reply_markup=action_kb(session_id, lang))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("sc:concern:"))
async def sc_concern(callback: CallbackQuery, lang: str):
    session_id = int(callback.data.split(":")[2])
    await callback.message.edit_text(
        CONCERN_QUESTION[lang],
        reply_markup=action_kb(session_id, lang),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("sc:full:"))
async def sc_full(callback: CallbackQuery, lang: str):
    session_id = int(callback.data.split(":")[2])
    problems = _get_problems(callback.from_user.id, session_id)
    await callback.message.edit_text(
        _checklist_header(lang),
        reply_markup=_checklist_kb(session_id, problems, lang),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("sc:tog:"))
async def sc_toggle(callback: CallbackQuery, lang: str):
    parts = callback.data.split(":")
    session_id = int(parts[2])
    key = parts[3]
    _toggle_problem(callback.from_user.id, session_id, key)
    problems = _get_problems(callback.from_user.id, session_id)
    await callback.message.edit_text(
        _checklist_header(lang),
        reply_markup=_checklist_kb(session_id, problems, lang),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("sc:submit:"))
async def sc_submit(callback: CallbackQuery, db: AsyncSession, lang: str):
    session_id = int(callback.data.split(":")[2])
    problems = _get_problems(callback.from_user.id, session_id)
    red_flags = len(problems)
    if red_flags == 0:
        await _ack_ping(db, session_id)
        from core.tasks import ping_user
        ping_user.apply_async(
            (session_id, callback.from_user.id),
            countdown=settings.ping_interval_minutes * 60,
        )
        text = RESULT_MESSAGES["safe"][lang].format(interval=settings.ping_interval_minutes)
        await callback.message.edit_text(text, reply_markup=action_kb(session_id, lang))
    elif red_flags <= 2:
        text = RESULT_MESSAGES["concern"][lang].format(count=red_flags)
        await callback.message.edit_text(text, reply_markup=action_kb(session_id, lang))
        await _notify_contacts_soft(db, callback.from_user.id, session_id, lang)
    else:
        text = RESULT_MESSAGES["danger"][lang].format(count=red_flags)
        await callback.message.edit_text(text, reply_markup=action_kb(session_id, lang))
        await _notify_contacts_soft(db, callback.from_user.id, session_id, lang)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("sc:sos:"))
async def sc_sos(callback: CallbackQuery, db: AsyncSession, lang: str):
    session_id = int(callback.data.split(":")[2])
    from bot.handlers.newdate import trigger_sos
    await trigger_sos(callback, db, lang)


@router.callback_query(lambda c: c.data and c.data.startswith("sc:action:"))
async def sc_action(callback: CallbackQuery, db: AsyncSession, lang: str, state: FSMContext):
    parts = callback.data.split(":")
    session_id = int(parts[2])
    action = parts[3]

    if action == "call_friend":
        result = await db.execute(
            select(TrustedContact)
            .where(TrustedContact.user_id == callback.from_user.id)
            .order_by(TrustedContact.priority)
        )
        contacts = result.scalars().all()
        if contacts:
            parts = []
            for c in contacts:
                channels = []
                if c.phone:
                    channels.append(f"📱 {c.phone.replace(' ', '')}")
                if c.telegram_username:
                    channels.append(f'💬 <a href="https://t.me/{c.telegram_username}">@{c.telegram_username}</a>')
                elif c.telegram_id:
                    channels.append(f'💬 <a href="tg://user?id={c.telegram_id}">Telegram</a>')
                if channels:
                    parts.append(f"<b>{c.name}</b>\n" + "\n".join(channels))
            header = {"ru": "Свяжись с подругой:", "en": "Contact your people:", "tr": "Bağlantı kur:"}[lang]
            contacts_text = header + "\n\n" + "\n\n".join(parts) if parts else {
                "ru": "У контактов нет способов для связи.",
                "en": "No contact methods available.",
                "tr": "İletişim yolu yok.",
            }[lang]
            await callback.message.answer(contacts_text, reply_markup=active_session_kb(lang, session_id), disable_web_page_preview=True)
        else:
            no_contact = {
                "ru": "У тебя нет сохранённых контактов. Добавь через /contacts.",
                "en": "You have no saved contacts. Add one via /contacts.",
                "tr": "Kayıtlı kişin yok. /contacts ile ekle.",
            }[lang]
            await callback.message.answer(no_contact, reply_markup=active_session_kb(lang, session_id))

    elif action == "note_and_go":
        ask = {
            "ru": "✍️ Напиши что именно беспокоит — я запишу и продолжу следить:",
            "en": "✍️ Write what's bothering you — I'll note it and keep watching:",
            "tr": "✍️ Seni neyin rahatsız ettiğini yaz — not alacağım ve izlemeye devam edeceğim:",
        }[lang]
        await callback.message.answer(ask)
        await state.set_state(NoteFlow.waiting_note)
        await state.update_data(note_session_id=session_id, note_user_id=callback.from_user.id)

    await callback.answer()


@router.callback_query(F.data == "sc:noop")
async def sc_noop(callback: CallbackQuery):
    await callback.answer()


@router.message(Command("status"))
async def cmd_status(message: Message, db: AsyncSession, lang: str):
    result = await db.execute(
        select(DateSession)
        .where(DateSession.user_id == message.from_user.id)
        .where(DateSession.status == SessionStatus.ACTIVE)
        .order_by(DateSession.started_at.desc())
    )
    session = result.scalars().first()
    if not session:
        no_session = {
            "ru": "Нет активного свидания.",
            "en": "No active date session.",
            "tr": "Aktif randevu yok.",
        }[lang]
        await message.answer(no_session)
        return

    await message.answer(
        SHORT_QUESTIONS[lang],
        reply_markup=short_ping_kb(session.id, lang),
    )


@router.message(NoteFlow.waiting_note, F.text, F.text.func(lambda t: not t.startswith("/") or t.strip().lower() == "/skip"))
async def note_received(message: Message, state: FSMContext, db: AsyncSession, lang: str):
    data = await state.get_data()
    session_id = data.get("note_session_id")
    note_text = message.text or ""
    await state.clear()

    if session_id:
        session_obj = await db.get(DateSession, session_id)
        if session_obj:
            session_obj.notes = ((session_obj.notes or "") + f"\n{note_text}").strip()
            session_obj.ping_generation += 1  # disarm pending L1 escalation
            try:
                await db.commit()
            except Exception:
                await db.rollback()

    confirmed = {
        "ru": f"📝 Записала: «{note_text}»\n\nПродолжаю следить. Следующая проверка через {settings.ping_interval_minutes} минут.",
        "en": f"📝 Noted: «{note_text}»\n\nStill watching. Next check-in in {settings.ping_interval_minutes} minutes.",
        "tr": f"📝 Not aldım: «{note_text}»\n\nİzlemeye devam ediyorum. Sonraki kontrol {settings.ping_interval_minutes} dakika sonra.",
    }[lang]
    kb = active_session_kb(lang, session_id) if session_id else None
    await message.answer(confirmed, reply_markup=kb)

    if session_id:
        from core.tasks import ping_user
        ping_user.apply_async(
            (session_id, message.from_user.id),
            countdown=settings.ping_interval_minutes * 60,
        )
