"""Ping message texts and keyboard — shared between bot and Celery worker."""
from aiogram.utils.keyboard import InlineKeyboardBuilder

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
