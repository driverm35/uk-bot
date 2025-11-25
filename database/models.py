import sqlite3
from enum import Enum
from typing import Optional, List
from sqlalchemy import (
    event, BigInteger, Integer, String, ForeignKey, Date, DateTime, UniqueConstraint, Text
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase, relationship
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.sql import func
from sqlalchemy.engine import Engine
from config.settings import DATABASE_URL

# Движок и сессии
engine = create_async_engine(DATABASE_URL, echo=True, pool_pre_ping=True)
async_session = async_sessionmaker(engine, expire_on_commit=False)

# SQLite: включить внешние ключи
@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

class Base(AsyncAttrs, DeclarativeBase):
    pass

class TicketStatus(str, Enum):
    OPEN = "open"
    WORK = "work"
    CANCELLED = "cancelled"

    @classmethod
    def labels(cls) -> dict[str, str]:
        return {
            cls.OPEN: "Открыта",
            cls.WORK: "В работе",
            cls.CANCELLED: "Завершена",
        }

    @classmethod
    def label(cls, value: str) -> str:
        """Возвращает человекочитаемое название статуса"""
        return cls.labels().get(value, value)

    @classmethod
    def emoji(cls, value: str) -> str:
        return {
            cls.OPEN: "🟢",
            cls.WORK: "🟡",
            cls.CANCELLED: "🟣",
        }.get(value, "⚪")

# --- Админ ---
class Admin(Base):
    __tablename__ = "admins"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    fullname: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)

# --- Пользователь ---
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=True)
    street: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    house: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    apartment: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    tickets: Mapped[List["Ticket"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=lambda: Ticket.created_at.desc(),
    )

    meter_readings: Mapped[List["MeterReading"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MeterReading.reading_date.desc()",
    )

# Заявки
class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[TicketStatus] = mapped_column(
        SAEnum(TicketStatus, name="ticket_status_enum"),
        nullable=False,
        default=TicketStatus.OPEN,
    )

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    group_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    thread_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user: Mapped["User"] = relationship(back_populates="tickets")

    attachments: Mapped[List["TicketAttachment"]] = relationship(
        "TicketAttachment", back_populates="ticket", cascade="all, delete-orphan"
    )

# модель вложений
class AttachmentType(str, Enum):
    photo = "photo"
    video = "video"
    document = "document"
    audio = "audio"
    voice = "voice"

class TicketAttachment(Base):
    __tablename__ = "ticket_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    type: Mapped[AttachmentType] = mapped_column(SAEnum(AttachmentType, name="ticket_attachment_type"), nullable=False)
    file_id: Mapped[str] = mapped_column(String(512), nullable=False)
    file_unique_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="attachments")


class MeterReading(Base):
    __tablename__ = "meter_readings"

    id = mapped_column(Integer, primary_key=True, index=True)
    user_id = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    meter_type = mapped_column(String, nullable=False)  # 'hot' или 'cold'
    meter_number = mapped_column(Integer, default=1)  # Номер счётчика (1, 2, 3)
    value = mapped_column(String, nullable=False)
    reading_date = mapped_column(Date, nullable=False)
    created_at = mapped_column(DateTime(timezone=True), default=func.now())

    user = relationship("User", back_populates="meter_readings")

    def __repr__(self):
        return f"<MeterReading(user={self.user_id}, type={self.meter_type}, meter_number={self.meter_number}, value={self.value})>"