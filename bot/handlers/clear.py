"""
/clear — wipe all date session data for the current user.
Useful if the phone falls into the wrong hands.
Keeps trusted contacts (those are the user's own friends, not date data).
"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from core.models import DateSession, SessionFile
from bot.middlewares.i18n import t as _t

router = Router()

_TEXTS = {
    "ru": {
        "confirm": (
            "🗑 <b>Удалить данные о свиданиях?</b>\n\n"
            "Будут удалены все сессии и прикреплённые файлы.\n"
            "Доверенные контакты останутся.\n\n"
            "Это действие нельзя отменить."
        ),
        "yes": "🗑 Да, удалить всё",
        "no": "← Отмена",
        "done": "✅ Готово. Все данные о свиданиях удалены.",
        "cancelled": "Отменено.",
    },
    "en": {
        "confirm": (
            "🗑 <b>Delete all date data?</b>\n\n"
            "All sessions and attached files will be deleted.\n"
            "Trusted contacts will remain.\n\n"
            "This cannot be undone."
        ),
        "yes": "🗑 Yes, delete everything",
        "no": "← Cancel",
        "done": "✅ Done. All date data has been deleted.",
        "cancelled": "Cancelled.",
    },
    "tr": {
        "confirm": (
            "🗑 <b>Buluşma verileri silinsin mi?</b>\n\n"
            "Tüm oturumlar ve ekli dosyalar silinecek.\n"
            "Güvenilen kişiler kalacak.\n\n"
            "Bu işlem geri alınamaz."
        ),
        "yes": "🗑 Evet, hepsini sil",
        "no": "← İptal",
        "done": "✅ Tamam. Tüm buluşma verileri silindi.",
        "cancelled": "İptal edildi.",
    },
}


def _t(key: str, lang: str) -> str:
    return _TEXTS.get(lang, _TEXTS["ru"])[key]


@router.message(Command("clear"))
async def cmd_clear(message: Message, lang: str):
    builder = InlineKeyboardBuilder()
    builder.button(text=_t("yes", lang), callback_data="clear:confirm")
    builder.button(text=_t("no", lang), callback_data="clear:cancel")
    builder.adjust(1)
    await message.answer(_t("confirm", lang), reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "clear:confirm")
async def do_clear(callback: CallbackQuery, db: AsyncSession, lang: str):
    user_id = callback.from_user.id

    # Find all sessions for this user
    result = await db.execute(
        select(DateSession).where(DateSession.user_id == user_id)
    )
    sessions = result.scalars().all()
    session_ids = [s.id for s in sessions]

    if session_ids:
        await db.execute(
            delete(SessionFile).where(SessionFile.session_id.in_(session_ids))
        )
        await db.execute(
            delete(DateSession).where(DateSession.user_id == user_id)
        )
        await db.commit()

    await callback.message.edit_text(_t("done", lang))
    await callback.answer()


@router.callback_query(F.data == "clear:cancel")
async def cancel_clear(callback: CallbackQuery, lang: str):
    await callback.message.edit_text(_t("cancelled", lang))
    await callback.answer()
