from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import (
    BigInteger, Boolean, DateTime, ForeignKey, Integer,
    String, Text, Enum, func
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Language(str, PyEnum):
    RU = "ru"
    EN = "en"
    TR = "tr"


class SessionStatus(str, PyEnum):
    PENDING = "pending"      # создана, ещё не запущена
    ACTIVE = "active"        # свидание идёт
    SAFE = "safe"            # пользователь вернулся безопасно
    ALERT_L1 = "alert_l1"   # тревога — уведомлены контакты
    ALERT_L2 = "alert_l2"   # тревога — уведомлены организации
    SOS = "sos"              # экстренный SOS
    CANCELLED = "cancelled"


class EscalationStatus(str, PyEnum):
    PENDING = "pending"
    SENT = "sent"
    ACKNOWLEDGED = "acknowledged"  # контакт подтвердил получение


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # Telegram user_id
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    language: Mapped[Language] = mapped_column(Enum(Language), default=Language.RU)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    sessions: Mapped[list["DateSession"]] = relationship(back_populates="user")
    contacts: Mapped[list["TrustedContact"]] = relationship(back_populates="user")


class TrustedContact(Base):
    __tablename__ = "trusted_contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(128))
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(256))
    # Just a label for display and manual t.me/<username> links — doesn't by
    # itself let the bot message this contact (see telegram_id below).
    telegram_username: Mapped[str | None] = mapped_column(String(64))
    telegram_id: Mapped[int | None] = mapped_column(BigInteger)  # для Telegram
    # Bots can't message a user who never started a chat with them, so a bare
    # username isn't enough — we send this contact an invite deep-link and
    # fill telegram_id in once they press Start (see bot/handlers/start.py).
    invite_token: Mapped[str | None] = mapped_column(String(64), unique=True)
    priority: Mapped[int] = mapped_column(Integer, default=1)    # порядок эскалации

    user: Mapped["User"] = relationship(back_populates="contacts")


class DateSession(Base):
    __tablename__ = "date_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    status: Mapped[SessionStatus] = mapped_column(Enum(SessionStatus), default=SessionStatus.PENDING)
    # Bumped every time the user acknowledges a ping. Lets a scheduled
    # escalate_l1 task detect it's stale (superseded by a later ping) and
    # no-op instead of firing a false alarm. See core/tasks.py.
    ping_generation: Mapped[int] = mapped_column(Integer, default=0)

    # Данные о свидании
    date_name: Mapped[str | None] = mapped_column(String(256))        # имя/ник человека
    date_profile_url: Mapped[str | None] = mapped_column(Text)        # ссылка на профиль
    meeting_place: Mapped[str | None] = mapped_column(Text)           # место встречи
    destination: Mapped[str | None] = mapped_column(Text)             # куда едут
    car_plate: Mapped[str | None] = mapped_column(String(32))         # номер машины
    car_description: Mapped[str | None] = mapped_column(String(256))  # марка, цвет
    extra_info: Mapped[str | None] = mapped_column(Text)              # любая доп. информация

    # Тайминги
    start_time: Mapped[datetime | None] = mapped_column(DateTime)
    expected_return: Mapped[datetime | None] = mapped_column(DateTime)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)     # реальное время запуска
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Геолокация (последняя известная)
    last_lat: Mapped[float | None]
    last_lon: Mapped[float | None]
    last_location_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Служебное
    alert_token: Mapped[str] = mapped_column(String(64), unique=True)  # токен для веб-страницы
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="sessions")
    files: Mapped[list["SessionFile"]] = relationship(back_populates="session")
    escalations: Mapped[list["Escalation"]] = relationship(back_populates="session")


class FileType(str, PyEnum):
    PHOTO = "photo"
    SCREENSHOT = "screenshot"
    DOCUMENT = "document"
    VOICE = "voice"


class SessionFile(Base):
    __tablename__ = "session_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("date_sessions.id"))
    file_type: Mapped[FileType] = mapped_column(Enum(FileType))
    s3_key: Mapped[str] = mapped_column(String(512))
    original_name: Mapped[str | None] = mapped_column(String(256))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    session: Mapped["DateSession"] = relationship(back_populates="files")


class Escalation(Base):
    __tablename__ = "escalations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("date_sessions.id"))
    contact_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("trusted_contacts.id"))
    level: Mapped[int] = mapped_column(Integer)           # 1=контакты, 2=организации, 3=SOS
    channel: Mapped[str] = mapped_column(String(32))      # sms / email / telegram
    recipient: Mapped[str] = mapped_column(String(256))   # номер/email/id
    status: Mapped[EscalationStatus] = mapped_column(Enum(EscalationStatus), default=EscalationStatus.PENDING)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime)

    session: Mapped["DateSession"] = relationship(back_populates="escalations")
