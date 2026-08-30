"""Admin-only /stats and /ping_now commands."""
from datetime import datetime, timedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.models import User, DateSession, SessionStatus

router = Router()


@router.message(Command("ping_now"))
async def cmd_ping_now(message: Message, db: AsyncSession):
    """Admin: immediately fire a ping for the caller's active session."""
    if not settings.admin_id or message.from_user.id != settings.admin_id:
        return
    result = await db.execute(
        select(DateSession)
        .where(DateSession.user_id == message.from_user.id)
        .where(DateSession.status == SessionStatus.ACTIVE)
        .order_by(DateSession.started_at.desc())
    )
    session = result.scalars().first()
    if not session:
        await message.answer("Нет активного свидания.")
        return
    from core.tasks import ping_user
    ping_user.apply_async((session.id, message.from_user.id), countdown=0)
    await message.answer(f"✅ Пинг поставлен в очередь (session={session.id}). Придёт через несколько секунд.")


@router.message(Command("stats"))
async def cmd_stats(message: Message, db: AsyncSession):
    if not settings.admin_id or message.from_user.id != settings.admin_id:
        return  # silently ignore for non-admins

    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = datetime.utcnow() - timedelta(days=7)

    total_users = (await db.execute(select(func.count()).select_from(User))).scalar()
    total_sessions = (await db.execute(select(func.count()).select_from(DateSession))).scalar()
    active_now = (await db.execute(
        select(func.count()).select_from(DateSession)
        .where(DateSession.status == SessionStatus.ACTIVE)
    )).scalar()
    sessions_today = (await db.execute(
        select(func.count()).select_from(DateSession)
        .where(DateSession.created_at >= today)
    )).scalar()
    sessions_week = (await db.execute(
        select(func.count()).select_from(DateSession)
        .where(DateSession.created_at >= week_ago)
    )).scalar()
    sos_total = (await db.execute(
        select(func.count()).select_from(DateSession)
        .where(DateSession.status == SessionStatus.SOS)
    )).scalar()

    text = (
        f"<b>SafeOut — статистика</b>\n\n"
        f"Пользователей: <b>{total_users}</b>\n"
        f"Свиданий всего: <b>{total_sessions}</b>\n"
        f"Активных сейчас: <b>{active_now}</b>\n"
        f"Сегодня: <b>{sessions_today}</b>\n"
        f"За неделю: <b>{sessions_week}</b>\n"
        f"SOS: <b>{sos_total}</b>\n\n"
        f"<i>{datetime.utcnow().strftime('%d.%m.%Y %H:%M')} UTC</i>"
    )
    await message.answer(text)
