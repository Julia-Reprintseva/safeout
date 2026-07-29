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
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.models import DateSession, SessionStatus, TrustedContact
from core.config import settings

router = Router()


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
    # Block 1 — Reality matches promises
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
    # Block 2 — Your feelings right now
    {
        "key": "feel_comfortable",
        "block": 2,
        "ru": "Ты чувствуешь себя комфортно",
        "en": "You feel comfortable",
        "tr": "Kendini rahat hissediyorsun",
        "red_flag": True,
    },
    {
        "key": "can_leave",
        "block": 2,
        "ru": "Ты можешь свободно уйти когда захочешь",
        "en": "You can leave freely whenever you want",
        "tr": "İstediğinde serbestçe ayrılabilirsin",
        "red_flag": True,
    },
    {
        "key": "no_anxiety",
        "block": 2,
        "ru": "Тебя ничего не беспокоит и не тревожит",
        "en": "Nothing feels off or worrying",
        "tr": "Seni rahatsız eden veya endişelendiren bir şey yok",
        "red_flag": False,
    },
    {
        "key": "conscious",
        "block": 2,
        "ru": "Ты в сознании и понимаешь что происходит",
        "en": "You are conscious and aware of what's happening",
        "tr": "Bilinçlisin ve ne olduğunun farkındasın",
        "red_flag": True,
    },
    {
        "key": "know_location",
        "block": 2,
        "ru": "Ты знаешь где находишься",
        "en": "You know where you are",
        "tr": "Nerede olduğunu biliyorsun",
        "red_flag": True,
    },
    # Block 3 — His behaviour
    {
        "key": "respects_boundaries",
        "block": 3,
        "ru": "Он уважает твои границы",
        "en": "He respects your boundaries",
        "tr": "Sınırlarına saygı gösteriyor",
        "red_flag": True,
    },
    {
        "key": "no_pressure_substances",
        "block": 3,
        "ru": "Он не настаивает на алкоголе или других веществах",
        "en": "He's not pushing alcohol or other substances",
        "tr": "Alkol veya başka madde kullanımı için baskı yapmıyor",
        "red_flag": True,
    },
    {
        "key": "phone_safe",
        "block": 3,
        "ru": "Он не забирал твой телефон или документы",
        "en": "He hasn't taken your phone or documents",
        "tr": "Telefonunu veya belgelerini almadı",
        "red_flag": True,
    },
    {
        "key": "no_threats",
        "block": 3,
        "ru": "Он не угрожал тебе и не запугивал",
        "en": "He hasn't threatened or intimidated you",
        "tr": "Seni tehdit etmedi veya korkutmadı",
        "red_flag": True,
    },
    {
        "key": "not_isolated",
        "block": 3,
        "ru": "Он не пытается изолировать тебя от людей",
        "en": "He's not trying to isolate you from other people",
        "tr": "Seni insanlardan izole etmeye çalışmıyor",
        "red_flag": True,
    },
]

BLOCK_TITLES = {
    1: {"ru": "📍 Реальность совпадает с обещанным",  "en": "📍 Reality matches promises",    "tr": "📍 Gerçeklik söylenenlere uyuyor"},
    2: {"ru": "💛 Твои ощущения прямо сейчас",        "en": "💛 How you feel right now",        "tr": "💛 Şu an nasıl hissediyorsun"},
    3: {"ru": "🔍 Его поведение",                     "en": "🔍 His behaviour",                 "tr": "🔍 Onun davranışı"},
}

SHORT_QUESTIONS = {
    "ru": (
        "👋 Быстрая проверка — ответь честно:\n\n"
        "1. Всё идёт как планировали — место, маршрут, человек?\n"
        "2. Ты чувствуешь себя комфортно и можешь уйти когда захочешь?\n"
        "3. Его поведение тебя не настораживает?"
    ),
    "en": (
        "👋 Quick check-in — answer honestly:\n\n"
        "1. Everything going as planned — place, route, person?\n"
        "2. You feel comfortable and free to leave anytime?\n"
        "3. Nothing about his behaviour worries you?"
    ),
    "tr": (
        "👋 Hızlı kontrol — dürüstçe cevapla:\n\n"
        "1. Her şey planlandığı gibi mi gidiyor — yer, güzergah, kişi?\n"
        "2. Rahat hissediyor ve istediğinde ayrılabilir misin?\n"
        "3. Davranışında seni tedirgin eden bir şey yok mu?"
    ),
}

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


def short_ping_kb(session_id: int, lang: str):
    builder = InlineKeyboardBuilder()
    labels = {
        "ru": ("✅ Всё хорошо", "⚠️ Есть проблема", "🆘 SOS"),
        "en": ("✅ I'm okay",   "⚠️ Something's off", "🆘 SOS"),
        "tr": ("✅ İyiyim",     "⚠️ Bir sorun var",    "🆘 SOS"),
    }[lang]
    builder.button(text=labels[0], callback_data=f"sc:ok:{session_id}")
    builder.button(text=labels[1], callback_data=f"sc:concern:{session_id}")
    builder.button(text=labels[2], callback_data=f"sc:sos:{session_id}")
    builder.adjust(1)
    return builder.as_markup()


def full_checklist_kb(session_id: int, answers: dict, lang: str):
    """Yes/No buttons for each check item."""
    builder = InlineKeyboardBuilder()
    yes_label = {"ru": "✅ Да", "en": "✅ Yes", "tr": "✅ Evet"}[lang]
    no_label  = {"ru": "❌ Нет", "en": "❌ No",  "tr": "❌ Hayır"}[lang]

    current_block = 0
    for item in STATUS_CHECKS:
        key = item["key"]
        ans = answers.get(key)
        y = f"✅ {item[lang][:35]}" if ans is True else yes_label
        n = f"❌ {item[lang][:35]}" if ans is False else no_label
        builder.button(text=f"{'→ ' if ans is None else ''}{item[lang][:40]}", callback_data="sc:noop")
        builder.button(text=y, callback_data=f"sc:ans:{session_id}:{key}:yes")
        builder.button(text=n, callback_data=f"sc:ans:{session_id}:{key}:no")

    done_label = {"ru": "Готово — показать результат", "en": "Done — show result", "tr": "Tamam — sonucu göster"}[lang]
    builder.button(text=done_label, callback_data=f"sc:result:{session_id}")
    builder.adjust(1, 2, 2)  # label row / yes+no row / ...
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


def _count_red_flags(answers: dict) -> int:
    count = 0
    for item in STATUS_CHECKS:
        if item["red_flag"] and answers.get(item["key"]) is False:
            count += 1
    return count


def _get_redis():
    from core.tasks import celery_app
    return celery_app.backend.client


def _get_answers(user_id: int, session_id: int) -> dict:
    redis = _get_redis()
    raw = redis.hgetall(f"sc:{user_id}:{session_id}")
    return {
        (k.decode() if isinstance(k, bytes) else k): (v == b"yes" or v == "yes")
        for k, v in raw.items()
    }


def _set_answer(user_id: int, session_id: int, key: str, value: bool):
    redis = _get_redis()
    redis_key = f"sc:{user_id}:{session_id}"
    redis.hset(redis_key, key, "yes" if value else "no")
    redis.expire(redis_key, 86400)


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
    await callback.message.edit_text(text)
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
    answers = _get_answers(callback.from_user.id, session_id)

    header = {
        "ru": "📋 <b>Чек-лист — сейчас на свидании</b>\n\nОтветь честно на каждый вопрос:\n",
        "en": "📋 <b>Checklist — during the date</b>\n\nAnswer honestly:\n",
        "tr": "📋 <b>Kontrol listesi — randevu sırasında</b>\n\nDürüstçe cevapla:\n",
    }[lang]

    lines = [header]
    current_block = 0
    for item in STATUS_CHECKS:
        if item["block"] != current_block:
            current_block = item["block"]
            lines.append(f"\n<b>{BLOCK_TITLES[current_block][lang]}</b>")
        ans = answers.get(item["key"])
        icon = "✅" if ans is True else ("❌" if ans is False else "⬜️")
        lines.append(f"{icon} {item[lang]}")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=full_checklist_kb(session_id, answers, lang),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("sc:ans:"))
async def sc_answer(callback: CallbackQuery, lang: str):
    parts = callback.data.split(":")
    session_id = int(parts[2])
    key = parts[3]
    value = parts[4] == "yes"

    _set_answer(callback.from_user.id, session_id, key, value)

    answers = _get_answers(callback.from_user.id, session_id)
    lines = []
    current_block = 0
    for item in STATUS_CHECKS:
        if item["block"] != current_block:
            current_block = item["block"]
            lines.append(f"\n<b>{BLOCK_TITLES[current_block][lang]}</b>")
        ans = answers.get(item["key"])
        icon = "✅" if ans is True else ("❌" if ans is False else "⬜️")
        lines.append(f"{icon} {item[lang]}")

    header = {
        "ru": "📋 <b>Чек-лист — сейчас на свидании</b>\n",
        "en": "📋 <b>Checklist — during the date</b>\n",
        "tr": "📋 <b>Kontrol listesi — randevu sırasında</b>\n",
    }[lang]

    await callback.message.edit_text(
        header + "\n".join(lines),
        reply_markup=full_checklist_kb(session_id, answers, lang),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("sc:result:"))
async def sc_result(callback: CallbackQuery, db: AsyncSession, lang: str):
    session_id = int(callback.data.split(":")[2])
    answers = _get_answers(callback.from_user.id, session_id)
    red_flags = _count_red_flags(answers)

    if red_flags == 0:
        await _ack_ping(db, session_id)
        from core.tasks import ping_user
        ping_user.apply_async(
            (session_id, callback.from_user.id),
            countdown=settings.ping_interval_minutes * 60,
        )
        text = RESULT_MESSAGES["safe"][lang].format(interval=settings.ping_interval_minutes)
        await callback.message.edit_text(text)
    elif red_flags <= 2:
        text = RESULT_MESSAGES["concern"][lang].format(count=red_flags)
        await callback.message.edit_text(text, reply_markup=action_kb(session_id, lang))
    else:
        text = RESULT_MESSAGES["danger"][lang].format(count=red_flags)
        await callback.message.edit_text(text, reply_markup=action_kb(session_id, lang))

    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("sc:sos:"))
async def sc_sos(callback: CallbackQuery, db: AsyncSession, lang: str):
    session_id = int(callback.data.split(":")[2])
    from bot.handlers.newdate import trigger_sos
    await trigger_sos(callback, db, lang)


@router.callback_query(lambda c: c.data and c.data.startswith("sc:action:"))
async def sc_action(callback: CallbackQuery, db: AsyncSession, lang: str):
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
            c = contacts[0]
            channels = []
            if c.phone:
                channels.append(f"📱 {c.phone}")
            if c.telegram_id:
                channels.append(f"Telegram: @{c.telegram_id}")
            contacts_text = {
                "ru": f"Свяжись с <b>{c.name}</b>:\n" + "\n".join(channels),
                "en": f"Contact <b>{c.name}</b>:\n" + "\n".join(channels),
                "tr": f"<b>{c.name}</b> ile iletişime geç:\n" + "\n".join(channels),
            }[lang]
            await callback.message.answer(contacts_text)
        else:
            no_contact = {
                "ru": "У тебя нет сохранённых контактов. Добавь через /contacts.",
                "en": "You have no saved contacts. Add one via /contacts.",
                "tr": "Kayıtlı kişin yok. /contacts ile ekle.",
            }[lang]
            await callback.message.answer(no_contact)

    elif action == "note_and_go":
        noted = {
            "ru": "📝 Зафиксировано. Я продолжаю следить. Следующая проверка через {interval} минут.",
            "en": "📝 Noted. I'm still watching. Next check-in in {interval} minutes.",
            "tr": "📝 Not alındı. İzlemeye devam ediyorum. Sonraki kontrol {interval} dakika sonra.",
        }[lang].format(interval=settings.ping_interval_minutes)
        await callback.message.answer(noted)
        await _ack_ping(db, session_id)
        from core.tasks import ping_user
        ping_user.apply_async(
            (session_id, callback.from_user.id),
            countdown=settings.ping_interval_minutes * 60,
        )

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
