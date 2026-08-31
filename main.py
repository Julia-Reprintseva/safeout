import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from core.config import settings
from core.database import engine
from core.models import Base
from bot.middlewares.db import DbMiddleware
from bot.middlewares.i18n import I18nMiddleware
from bot.middlewares.fsm_reset import FsmResetOnCommandMiddleware
from bot.handlers import start, contacts, newdate, checklist, status_check, clear, stats, fallback, admin

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot):
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_my_commands([
        BotCommand(command="newdate",   description="Создать новое свидание"),
        BotCommand(command="contacts",  description="Доверенные контакты"),
        BotCommand(command="clear",     description="Удалить данные о свиданиях"),
        BotCommand(command="language",  description="Сменить язык"),
        BotCommand(command="tubiki",    description="Моя коллекция тюбиков 🙈"),
        BotCommand(command="help",      description="Помощь"),
    ])
    # Admin-only commands (only visible to admin in their menu)
    if settings.admin_id:
        from aiogram.types import BotCommandScopeChat
        await bot.set_my_commands(
            [
                BotCommand(command="newdate",  description="Создать новое свидание"),
                BotCommand(command="contacts", description="Доверенные контакты"),
                BotCommand(command="clear",    description="Удалить данные о свиданиях"),
                BotCommand(command="language", description="Сменить язык"),
                BotCommand(command="tubiki",   description="Моя коллекция тюбиков 🙈"),
                BotCommand(command="help",     description="Помощь"),
                BotCommand(command="gift",     description="[admin] Выдать Premium"),
                BotCommand(command="revoke",   description="[admin] Отозвать Premium"),
                BotCommand(command="users",    description="[admin] Список пользователей"),
            ],
            scope=BotCommandScopeChat(chat_id=settings.admin_id),
        )
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
        await conn.execute(
            __import__("sqlalchemy").text(
                "ALTER TABLE date_sessions ADD COLUMN IF NOT EXISTS review VARCHAR(16)"
            )
        )
        await conn.execute(
            __import__("sqlalchemy").text(
                "ALTER TABLE date_sessions ADD COLUMN IF NOT EXISTS tubik_name VARCHAR(256)"
            )
        )
        await conn.execute(
            __import__("sqlalchemy").text(
                "ALTER TABLE date_sessions ADD COLUMN IF NOT EXISTS notes TEXT"
            )
        )
        await conn.execute(
            __import__("sqlalchemy").text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_premium BOOLEAN NOT NULL DEFAULT FALSE"
            )
        )
        await conn.execute(
            __import__("sqlalchemy").text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS sessions_used INTEGER NOT NULL DEFAULT 0"
            )
        )
        await conn.execute(__import__("sqlalchemy").text("""
            CREATE TABLE IF NOT EXISTS tubiks (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id),
                name VARCHAR(256) NOT NULL,
                comment TEXT,
                date_session_id INTEGER REFERENCES date_sessions(id) ON DELETE SET NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))

    storage = RedisStorage.from_url(settings.redis_url)
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=storage)

    # Middlewares (order matters: DB first, then i18n which needs db_user)
    dp.update.middleware(DbMiddleware())
    dp.update.middleware(I18nMiddleware())
    dp.update.middleware(FsmResetOnCommandMiddleware())

    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(contacts.router)
    dp.include_router(newdate.router)
    dp.include_router(checklist.router)
    dp.include_router(status_check.router)
    dp.include_router(clear.router)
    dp.include_router(stats.router)
    dp.include_router(fallback.router)  # must be last

    dp.startup.register(on_startup)

    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
