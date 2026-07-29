"""
Smart safety checklist — shown before starting a date session.

Variant C: bot auto-checks what's already filled in the session,
highlights gaps, and blocks starting until critical items are confirmed.
"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.models import DateSession, SessionStatus, TrustedContact, SessionFile
from bot.middlewares.i18n import t as _t

router = Router()

# ---------------------------------------------------------------------------
# Checklist definition
# Each item: (key, block, label_ru, label_en, label_tr, critical, auto_field)
#   auto_field — session attribute to check automatically (None = must be manual)
#   critical   — if True, user CANNOT start date until confirmed
# ---------------------------------------------------------------------------
CHECKLIST: list[dict] = [
    # Block 1 — Info about the person
    {
        "key": "real_name",
        "block": 1,
        "ru": "Ты знаешь его настоящее имя",
        "en": "You know his real name",
        "tr": "Gerçek adını biliyorsun",
        "critical": True,
        "auto_field": "date_name",
    },
    {
        "key": "social_found",
        "block": 1,
        "ru": "Ты нашла его в соцсетях (ВКонтакте, Instagram, LinkedIn)",
        "en": "You found him on social media (VK, Instagram, LinkedIn)",
        "tr": "Sosyal medyada buldun (Instagram, LinkedIn)",
        "critical": True,
        "auto_field": "date_profile_url",
    },
    {
        "key": "voice_video",
        "block": 1,
        "ru": "Вы общались голосом или видео — ты уверена что он живой человек",
        "en": "You talked by voice or video — confirmed he's a real person",
        "tr": "Sesli veya görüntülü konuştunuz — gerçek bir insan olduğundan eminsin",
        "critical": True,
        "auto_field": None,
    },
    {
        "key": "screenshots",
        "block": 1,
        "ru": "Скриншоты переписки сохранены в боте",
        "en": "Chat screenshots saved in the bot",
        "tr": "Sohbet ekran görüntüleri botta kaydedildi",
        "critical": False,
        "auto_field": "has_files",
    },
    {
        "key": "documents",
        "block": 1,
        "ru": "Есть копия его документов (паспорт или водительское удостоверение)",
        "en": "You have a copy of his documents (passport or driver's licence)",
        "tr": "Belgelerinin kopyası var (pasaport veya sürücü belgesi)",
        "critical": False,
        "auto_field": None,
    },
    {
        "key": "car_plate",
        "block": 1,
        "ru": "Ты знаешь номер и марку его машины",
        "en": "You know his car plate and make",
        "tr": "Araç plakasını ve markasını biliyorsun",
        "critical": False,
        "auto_field": "car_plate",
    },
    {
        "key": "his_address",
        "block": 1,
        "ru": "Ты знаешь его домашний адрес",
        "en": "You know his home address",
        "tr": "Ev adresini biliyorsun",
        "critical": False,
        "auto_field": None,
    },
    # Block 2 — Place & route
    {
        "key": "public_place",
        "block": 2,
        "ru": "Первая встреча в публичном месте (не у него дома)",
        "en": "First meeting in a public place (not his home)",
        "tr": "İlk buluşma halka açık bir yerde (evinde değil)",
        "critical": True,
        "auto_field": None,
    },
    {
        "key": "meeting_place_saved",
        "block": 2,
        "ru": "Адрес встречи сохранён в боте",
        "en": "Meeting address saved in the bot",
        "tr": "Buluşma adresi botta kaydedildi",
        "critical": True,
        "auto_field": "meeting_place",
    },
    {
        "key": "destination_saved",
        "block": 2,
        "ru": "Маршрут / куда едете — сохранён",
        "en": "Route / destination saved",
        "tr": "Güzergah / nereye gittiğiniz kaydedildi",
        "critical": False,
        "auto_field": "destination",
    },
    {
        "key": "way_home",
        "block": 2,
        "ru": "Ты знаешь как добраться домой самостоятельно (такси, метро)",
        "en": "You know how to get home on your own (taxi, metro)",
        "tr": "Kendi başına eve nasıl döneceğini biliyorsun (taksi, metro)",
        "critical": True,
        "auto_field": None,
    },
    # Block 3 — Trusted people know
    {
        "key": "someone_knows",
        "block": 3,
        "ru": "Хотя бы один близкий человек знает куда ты идёшь",
        "en": "At least one person close to you knows where you're going",
        "tr": "En az bir yakın kişi nereye gittiğini biliyor",
        "critical": True,
        "auto_field": "has_contacts",
    },
    {
        "key": "return_time_told",
        "block": 3,
        "ru": "Близкие знают примерное время твоего возвращения",
        "en": "Your contacts know your approximate return time",
        "tr": "Yakınların yaklaşık dönüş saatini biliyor",
        "critical": False,
        "auto_field": "expected_return",
    },
    # Block 4 — Phone & connection
    {
        "key": "phone_charged",
        "block": 4,
        "ru": "Телефон заряжен (желательно от 50%)",
        "en": "Phone is charged (ideally 50%+)",
        "tr": "Telefon şarjlı (tercihen %50+)",
        "critical": True,
        "auto_field": None,
    },
    {
        "key": "internet_on",
        "block": 4,
        "ru": "Включён мобильный интернет",
        "en": "Mobile internet is on",
        "tr": "Mobil internet açık",
        "critical": True,
        "auto_field": None,
    },
    {
        "key": "emergency_number",
        "block": 4,
        "ru": "Ты знаешь номер экстренной помощи в этой стране",
        "en": "You know the emergency number in this country",
        "tr": "Bu ülkedeki acil numarayı biliyorsun",
        "critical": False,
        "auto_field": None,
    },
    {
        "key": "taxi_app",
        "block": 4,
        "ru": "Приложение такси установлено и работает",
        "en": "Taxi app is installed and working",
        "tr": "Taksi uygulaması yüklü ve çalışıyor",
        "critical": False,
        "auto_field": None,
    },
    # Block 5 — Emergency plan
    {
        "key": "exit_excuse",
        "block": 5,
        "ru": "Ты придумала причину уйти если почувствуешь дискомфорт",
        "en": "You have a ready excuse to leave if you feel uncomfortable",
        "tr": "Rahatsız hissedersen ayrılmak için bir bahaneniz var",
        "critical": False,
        "auto_field": None,
    },
    {
        "key": "knows_sos",
        "block": 5,
        "ru": "Ты знаешь как отправить SOS одним нажатием в SafeOut",
        "en": "You know how to send SOS in SafeOut with one tap",
        "tr": "SafeOut'ta tek dokunuşla SOS göndermeyi biliyorsun",
        "critical": False,
        "auto_field": None,
    },
    {
        "key": "friend_call",
        "block": 5,
        "ru": "Подруга позвонит тебе в условленное время для проверки",
        "en": "A friend will call you at an agreed time to check in",
        "tr": "Bir arkadaşın kontrol etmek için belirli bir saatte arayacak",
        "critical": False,
        "auto_field": None,
    },
]

BLOCK_TITLES = {
    1: {"ru": "👤 Информация о человеке", "en": "👤 Info about him", "tr": "👤 Hakkında bilgi"},
    2: {"ru": "📍 Место и маршрут",        "en": "📍 Place & route",   "tr": "📍 Yer ve güzergah"},
    3: {"ru": "👥 Близкие в курсе",         "en": "👥 People know",    "tr": "👥 Yakınlar biliyor"},
    4: {"ru": "📱 Телефон и связь",         "en": "📱 Phone & signal", "tr": "📱 Telefon ve bağlantı"},
    5: {"ru": "🚨 Экстренный план",         "en": "🚨 Emergency plan", "tr": "🚨 Acil plan"},
}


async def build_checklist_state(
    session: DateSession | None,
    contacts: list,
    files: list,
    manual_checks: set[str],
) -> dict[str, bool | None]:
    """
    Returns {key: True/False/None} for each checklist item.
    True  = confirmed (auto or manual)
    False = explicitly not done (manual toggle)
    None  = unknown / not checked yet
    """
    state: dict[str, bool | None] = {}

    def auto_check(field: str) -> bool | None:
        if session is None:
            return None
        if field == "has_files":
            return len(files) > 0
        if field == "has_contacts":
            return len(contacts) > 0
        val = getattr(session, field, None)
        return bool(val) if val is not None else None

    for item in CHECKLIST:
        key = item["key"]
        if key in manual_checks:
            state[key] = True
            continue
        af = item["auto_field"]
        if af:
            state[key] = auto_check(af)
        else:
            state[key] = None  # needs manual confirmation

    return state


def render_checklist(state: dict, lang: str) -> tuple[str, bool]:
    """Returns (message_text, all_critical_done)."""
    lines = []
    current_block = 0
    all_critical_done = True

    for item in CHECKLIST:
        if item["block"] != current_block:
            current_block = item["block"]
            lines.append(f"\n<b>{BLOCK_TITLES[current_block][lang]}</b>")

        status = state.get(item["key"])
        label = item[lang]

        if status is True:
            icon = "✅"
        elif status is False:
            icon = "❌"
            if item["critical"]:
                all_critical_done = False
        else:
            icon = "⬜️"
            if item["critical"]:
                all_critical_done = False

        critical_marker = " <b>(!)</b>" if item["critical"] and status is not True else ""
        lines.append(f"{icon} {label}{critical_marker}")

    return "\n".join(lines), all_critical_done


def checklist_kb(session_id: int, state: dict, lang: str, all_critical_done: bool) -> object:
    """Keyboard: toggle buttons for manual items + start button."""
    builder = InlineKeyboardBuilder()

    for item in CHECKLIST:
        if item["auto_field"] is not None:
            continue  # auto-checked, no button needed
        key = item["key"]
        status = state.get(key)
        icon = "✅" if status else "⬜️"
        label = item[lang][:40]
        builder.button(
            text=f"{icon} {label}",
            callback_data=f"cl:toggle:{session_id}:{key}",
        )

    builder.adjust(1)

    if all_critical_done:
        start_text = {
            "ru": "▶️ Всё готово — начать свидание",
            "en": "▶️ All set — start date",
            "tr": "▶️ Hazır — buluşmayı başlat",
        }[lang]
        builder.button(
            text=start_text,
            callback_data=f"session:start:{session_id}",
        )
    else:
        warn_text = {
            "ru": "⚠️ Заполни обязательные пункты (!) чтобы начать",
            "en": "⚠️ Complete required items (!) to start",
            "tr": "⚠️ Başlamak için zorunlu maddeleri (!) tamamla",
        }[lang]
        builder.button(text=warn_text, callback_data="cl:noop")

    builder.adjust(1)
    return builder.as_markup()


async def show_checklist(
    message_or_callback,
    session_id: int,
    db: AsyncSession,
    lang: str,
    manual_checks: set[str] | None = None,
):
    if manual_checks is None:
        manual_checks = set()

    session = await db.get(DateSession, session_id)

    contacts_result = await db.execute(
        select(TrustedContact).where(
            TrustedContact.user_id == (session.user_id if session else 0)
        )
    )
    contacts = contacts_result.scalars().all()

    files_result = await db.execute(
        select(SessionFile).where(SessionFile.session_id == session_id)
    )
    files = files_result.scalars().all()

    state = await build_checklist_state(session, contacts, files, manual_checks)
    text, all_critical_done = render_checklist(state, lang)

    header = {
        "ru": "📋 <b>Чек-лист безопасности SafeOut</b>\n\n✅ Заполнено автоматически   ⬜️ Нажми чтобы отметить   <b>(!)</b> Обязательно\n",
        "en": "📋 <b>SafeOut Safety Checklist</b>\n\n✅ Auto-filled   ⬜️ Tap to confirm   <b>(!)</b> Required\n",
        "tr": "📋 <b>SafeOut Güvenlik Kontrol Listesi</b>\n\n✅ Otomatik dolduruldu   ⬜️ Onaylamak için dokun   <b>(!)</b> Zorunlu\n",
    }[lang]

    full_text = header + text
    kb = checklist_kb(session_id, state, lang, all_critical_done)

    if hasattr(message_or_callback, "message"):
        # it's a CallbackQuery
        await message_or_callback.message.edit_text(full_text, reply_markup=kb)
        await message_or_callback.answer()
    else:
        await message_or_callback.answer(full_text, reply_markup=kb)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

@router.message(Command("checklist"))
async def cmd_checklist(message: Message, db: AsyncSession, lang: str):
    # Find latest pending/active session
    result = await db.execute(
        select(DateSession)
        .where(DateSession.user_id == message.from_user.id)
        .where(DateSession.status.in_([SessionStatus.PENDING, SessionStatus.ACTIVE]))
        .order_by(DateSession.created_at.desc())
    )
    session = result.scalars().first()
    if not session:
        no_session = {
            "ru": "Сначала создай свидание через /newdate",
            "en": "First create a date with /newdate",
            "tr": "Önce /newdate ile bir buluşma oluştur",
        }[lang]
        await message.answer(no_session)
        return
    await show_checklist(message, session.id, db, lang)


@router.callback_query(lambda c: c.data and c.data.startswith("cl:toggle:"))
async def toggle_item(callback: CallbackQuery, db: AsyncSession, lang: str):
    _, _, session_id_str, key = callback.data.split(":", 3)
    session_id = int(session_id_str)

    # Retrieve current manual checks from FSM or re-derive from callback
    # For simplicity we store manual checks in a DB-friendly way:
    # re-read from session and toggle
    from aiogram.fsm.context import FSMContext
    # We pass manual_checks via bot data stored in Redis using a simple key
    from aiogram import Bot
    bot: Bot = callback.bot
    redis_key = f"cl:{callback.from_user.id}:{session_id}"

    # Read current manual checks from Redis
    from core.tasks import celery_app
    redis = celery_app.backend.client  # reuse Celery's Redis connection

    raw = redis.smembers(redis_key)
    manual_checks: set[str] = {v.decode() if isinstance(v, bytes) else v for v in raw}

    if key in manual_checks:
        manual_checks.discard(key)
        redis.srem(redis_key, key)
    else:
        manual_checks.add(key)
        redis.sadd(redis_key, key)
        redis.expire(redis_key, 86400 * 7)  # keep for 7 days

    await show_checklist(callback, session_id, db, lang, manual_checks)


@router.callback_query(F.data == "cl:noop")
async def noop(callback: CallbackQuery, lang: str):
    warn = {
        "ru": "⚠️ Заполни все обязательные пункты (!) чтобы начать свидание",
        "en": "⚠️ Complete all required (!) items to start the date",
        "tr": "⚠️ Buluşmayı başlatmak için tüm zorunlu (!) maddeleri tamamla",
    }[lang]
    await callback.answer(warn, show_alert=True)
