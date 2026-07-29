"""Synchronous DB helpers for Celery tasks.

Celery workers call these via a fresh asyncio.run() per task invocation, but
the async engine (and its asyncpg connection pool) is a single module-level
object shared across the whole worker process. Reusing pooled connections
across different asyncio.run()-created event loops breaks asyncpg, so every
helper here disposes the engine's pool before its event loop closes — the
next call transparently opens a fresh pool on its own loop.
"""
import asyncio
from sqlalchemy import select
from core.database import async_session_factory, engine
from core.models import DateSession, User, TrustedContact


async def _run(coro_factory):
    try:
        return await coro_factory()
    finally:
        await engine.dispose()


def get_session_status(session_id: int) -> str | None:
    async def _get():
        async with async_session_factory() as db:
            session = await db.get(DateSession, session_id)
            return session.status.value if session else None

    return asyncio.run(_run(_get))


def get_escalation_context(session_id: int) -> dict | None:
    """Fresh snapshot needed by escalation tasks: session status,
    ping_generation (to detect stale/superseded escalations), and the full
    session_data payload used to build alert messages. None if the session
    no longer exists.
    """

    async def _get():
        async with async_session_factory() as db:
            session = await db.get(DateSession, session_id)
            if not session:
                return None
            user = await db.get(User, session.user_id)
            result = await db.execute(
                select(TrustedContact).where(TrustedContact.user_id == session.user_id)
            )
            contacts = result.scalars().all()
            return {
                "status": session.status.value,
                "ping_generation": session.ping_generation,
                "session_data": {
                    "session_id": session.id,
                    "alert_token": session.alert_token,
                    "user_name": (user.first_name if user and user.first_name else "пользователь"),
                    "lang": user.language.value if user else "ru",
                    "date_name": session.date_name,
                    "meeting_place": session.meeting_place,
                    "destination": session.destination,
                    "hotel_info": session.hotel_info,
                    "car_plate": session.car_plate,
                    "date_profile_url": session.date_profile_url,
                    "contacts": [
                        {
                            "name": c.name,
                            "phone": c.phone,
                            "email": c.email,
                            "telegram_id": c.telegram_id,
                        }
                        for c in contacts
                    ],
                    "country": "ru",
                },
            }

    return asyncio.run(_run(_get))
