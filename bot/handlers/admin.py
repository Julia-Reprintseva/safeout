from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.config import settings
from core.models import User

router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id == settings.admin_id


@router.message(Command("gift"))
async def cmd_gift(message: Message, db: AsyncSession):
    """Admin only: /gift <user_id> — grant premium to a user."""
    if not _is_admin(message.from_user.id):
        return

    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.answer("Использование: /gift <user_id>\n\nUser ID можно узнать через @userinfobot")
        return

    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("❌ Неверный user_id — должно быть число.")
        return

    user = await db.get(User, target_id)
    if not user:
        await message.answer(f"❌ Пользователь {target_id} не найден. Они должны хотя бы раз написать боту.")
        return

    user.is_premium = True
    await db.commit()

    await message.answer(f"✅ Пользователю {target_id} ({user.first_name or '—'}) выдан Premium.")

    # Notify the user
    try:
        await message.bot.send_message(
            chat_id=target_id,
            text="🎁 Тебе подарили SafeOut Premium! Теперь можешь создавать неограниченное количество свиданий.",
        )
    except Exception:
        await message.answer("(Не удалось уведомить пользователя — возможно, они не начали диалог с ботом)")


@router.message(Command("revoke"))
async def cmd_revoke(message: Message, db: AsyncSession):
    """Admin only: /revoke <user_id> — remove premium."""
    if not _is_admin(message.from_user.id):
        return

    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.answer("Использование: /revoke <user_id>")
        return

    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("❌ Неверный user_id.")
        return

    user = await db.get(User, target_id)
    if not user:
        await message.answer(f"❌ Пользователь {target_id} не найден.")
        return

    user.is_premium = False
    await db.commit()
    await message.answer(f"✅ Premium у {target_id} ({user.first_name or '—'}) отозван.")


@router.message(Command("users"))
async def cmd_users(message: Message, db: AsyncSession):
    """Admin only: show all users and their premium status."""
    if not _is_admin(message.from_user.id):
        return

    result = await db.execute(select(User).order_by(User.id))
    users = result.scalars().all()

    if not users:
        await message.answer("Пользователей пока нет.")
        return

    lines = []
    for u in users:
        status = "👑 Premium" if u.is_premium else f"🆓 {u.sessions_used}/{settings.free_sessions_limit}"
        lines.append(f"{u.id} — {u.first_name or '—'} {status}")

    await message.answer("\n".join(lines))
