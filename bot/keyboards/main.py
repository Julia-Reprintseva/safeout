from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.middlewares.i18n import t


def skip_kb(lang: str) -> InlineKeyboardMarkup:
    label = {"ru": "Пропустить →", "en": "Skip →", "tr": "Atla →"}.get(lang, "Пропустить →")
    builder = InlineKeyboardBuilder()
    builder.button(text=label, callback_data="step:skip")
    return builder.as_markup()


def language_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🇷🇺 Русский", callback_data="lang:ru")
    builder.button(text="🇬🇧 English", callback_data="lang:en")
    builder.button(text="🇹🇷 Türkçe", callback_data="lang:tr")
    builder.adjust(3)
    return builder.as_markup()


def ping_kb(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("ping_ok_btn", lang), callback_data="ping:ok")
    builder.button(text=t("ping_sos_btn", lang), callback_data="ping:sos")
    builder.adjust(1)
    return builder.as_markup()


def start_date_kb(lang: str, session_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("start_date_btn", lang), callback_data=f"session:start:{session_id}")
    builder.adjust(1)
    return builder.as_markup()


def active_session_kb(lang: str, session_id: int) -> InlineKeyboardMarkup:
    concern_label = {"ru": "⚠️ Что-то не так", "en": "⚠️ Something's off", "tr": "⚠️ Bir şeyler yanlış"}.get(lang, "⚠️ Что-то не так")
    builder = InlineKeyboardBuilder()
    builder.button(text=t("end_session_btn", lang), callback_data=f"session:end:{session_id}")
    builder.button(text=concern_label,              callback_data=f"sc:concern:{session_id}")
    builder.button(text="🆘 SOS",                  callback_data=f"session:sos:{session_id}")
    builder.adjust(1)
    return builder.as_markup()


def files_done_kb(lang: str, session_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("files_done", lang), callback_data=f"files:done:{session_id}")
    builder.adjust(1)
    return builder.as_markup()


def contacts_kb(lang: str, contacts: list) -> InlineKeyboardMarkup:
    edit_label = {"ru": "✏️ Изменить", "en": "✏️ Edit", "tr": "✏️ Düzenle"}.get(lang, "✏️ Изменить")
    builder = InlineKeyboardBuilder()
    for c in contacts:
        if c.telegram_username:
            builder.button(text=f"💬 {c.name}", url=f"https://t.me/{c.telegram_username}")
    builder.button(text=t("add_contact_btn", lang), callback_data="contact:add")
    if contacts:
        builder.button(text=edit_label, callback_data="contact:edit_mode")
    builder.adjust(1)
    return builder.as_markup()


def contacts_edit_kb(lang: str, contacts: list) -> InlineKeyboardMarkup:
    done_label = {"ru": "← Готово", "en": "← Done", "tr": "← Tamam"}.get(lang, "← Готово")
    builder = InlineKeyboardBuilder()
    for c in contacts:
        builder.button(text=f"— {c.name}", callback_data=f"contact:delete:{c.id}")
    builder.button(text=done_label, callback_data="contact:view_mode")
    builder.adjust(1)
    return builder.as_markup()
