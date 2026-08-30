from typing import Any, Awaitable, Callable
from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, Update


class FsmResetOnCommandMiddleware(BaseMiddleware):
    """Clear FSM state when user sends any command, so a stale state
    (e.g. AddContact.email) can't swallow an unrelated command like /newdate."""

    async def __call__(
        self,
        handler: Callable[[Update, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        message: Message | None = getattr(event, "message", None)
        if message and message.text and message.text.startswith("/") and message.text.strip().lower() != "/skip":
            fsm: FSMContext | None = data.get("state")
            if fsm:
                current = await fsm.get_state()
                if current:
                    await fsm.clear()
        return await handler(event, data)
