from typing import Any, Awaitable, Callable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import async_session_factory
from core.models import User


class DbMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with async_session_factory() as session:
            data["db"] = session

            tg_user = data.get("event_from_user")
            if tg_user:
                db_user = await session.get(User, tg_user.id)
                data["db_user"] = db_user

            return await handler(event, data)
