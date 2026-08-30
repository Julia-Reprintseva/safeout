"""Catch-all handler for messages outside any active FSM state."""
from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state
from aiogram.filters import StateFilter
from aiogram.types import Message

from bot.middlewares.i18n import t

router = Router()


@router.message(StateFilter(default_state))
async def unknown_message(message: Message, lang: str):
    """User sent something unexpected — remind them what the bot can do."""
    if message.text and message.text.startswith("/"):
        return  # unknown command — let Telegram handle "unknown command" or just ignore
    await message.answer(t("fallback_hint", lang))
