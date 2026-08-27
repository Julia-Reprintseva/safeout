import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from core.config import settings
from core.database import engine
from core.models import Base
from bot.middlewares.db import DbMiddleware
from bot.middlewares.i18n import I18nMiddleware
from bot.handlers import start, contacts, newdate, checklist, status_check, clear

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot):
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("SafeOut bot started")


async def main():
    # Create tables (use Alembic in production)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Safe migration: add consent_given if missing
        await conn.execute(
            __import__("sqlalchemy").text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS consent_given BOOLEAN NOT NULL DEFAULT FALSE"
            )
        )

    storage = RedisStorage.from_url(settings.redis_url)
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=storage)

    # Middlewares (order matters: DB first, then i18n which needs db_user)
    dp.update.middleware(DbMiddleware())
    dp.update.middleware(I18nMiddleware())

    dp.include_router(start.router)
    dp.include_router(contacts.router)
    dp.include_router(newdate.router)
    dp.include_router(checklist.router)
    dp.include_router(status_check.router)
    dp.include_router(clear.router)

    dp.startup.register(on_startup)

    # Temporary: log every raw update type to diagnose loop
    @dp.update.outer_middleware()
    async def log_update(handler, event, data):
        upd = event.update if hasattr(event, "update") else event
        kind = upd.event_type if hasattr(upd, "event_type") else type(upd).__name__
        cb_data = None
        if hasattr(upd, "callback_query") and upd.callback_query:
            cb_data = upd.callback_query.data
        logger.info("RAW UPDATE type=%s cb_data=%s", kind, cb_data)
        return await handler(event, data)

    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
