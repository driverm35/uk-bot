from __future__ import annotations

from typing import Callable, Awaitable, Any, Optional, Dict, List, Tuple
from datetime import date, datetime
from functools import wraps

import pytz
from sqlalchemy import select, exists, extract, func, and_, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    async_session,
    Admin,
    User,
    Ticket,
    TicketStatus,
    TicketAttachment,
    AttachmentType,
    MeterReading,
)
from app.logger import logger


# ========= Таймзона =========
IRKUTSK_TZ = pytz.timezone("Asia/Irkutsk")
UTC = pytz.utc


def _to_irkt(dt: Optional[datetime]) -> Optional[datetime]:
    """Перевести datetime из UTC (или naive=UTC) в Asia/Irkutsk."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = UTC.localize(dt)
    return dt.astimezone(IRKUTSK_TZ)


def _irkt_now() -> datetime:
    """Текущее время в Иркутске (aware)."""
    return datetime.now(UTC).astimezone(IRKUTSK_TZ)


def _fmt_irkt(dt: Optional[datetime]) -> Optional[str]:
    """Человекочитаемая строка в Иркутске."""
    loc = _to_irkt(dt)
    return loc.strftime("%d.%m.%Y %H:%M") if loc else None


# ========= Декоратор подключения к БД =========
def connection(func: Callable[..., Awaitable[Any]]):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        async with async_session() as session:
            try:
                result = await func(session, *args, **kwargs)
                await session.commit()
                return result
            except Exception as e:
                await session.rollback()
                logger.exception("DB error in %s: %s", func.__name__, e)
                raise

    return wrapper


# ========= Пользователи =========
@connection
async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: str,
    name: str,
    status: str = "new",
) -> User:
    q = select(User).where(User.telegram_id == telegram_id)
    user: User | None = (await session.execute(q)).scalar_one_or_none()

    if user:
        if username and user.username != username:
            user.username = username
            session.add(user)
        return user

    user = User(
        telegram_id=telegram_id,
        status=status,
        username=username or "",
        name=name or "",
        phone=None,
        street=None,
        house=None,
        apartment=None,
    )
    session.add(user)
    await session.flush()
    return user


@connection
async def update_user_profile(
    session: AsyncSession,
    telegram_id: int,
    status: Optional[str] = "new",
    name: Optional[str] = None,
    phone: Optional[str] = None,
    street: Optional[str] = None,
    house: Optional[str] = None,
    apartment: Optional[str] = None,
) -> User:
    q = select(User).where(User.telegram_id == telegram_id)
    user: Optional[User] = (await session.execute(q)).scalar_one_or_none()
    if not user:
        raise ValueError(f"User {telegram_id} not found")

    if status is not None:
        user.status = status.strip()
    if name is not None:
        user.name = name.strip()
    if phone is not None:
        user.phone = phone.strip()
    if street is not None:
        user.street = street.strip()
    if house is not None:
        user.house = house.strip()
    if apartment is not None:
        user.apartment = apartment.strip() if apartment else None

    session.add(user)
    return user


@connection
async def get_user_by_tg(session: AsyncSession, telegram_id: int) -> Optional[Dict[str, Any]]:
    """Получить информацию о пользователе в виде словаря."""
    q = select(User).where(User.telegram_id == telegram_id)
    user: User | None = (await session.execute(q)).scalar_one_or_none()

    if not user:
        return None

    return {
        "id": user.id,
        "name": user.name,
        "phone": user.phone,
        "street": user.street,
        "house": user.house,
        "apartment": user.apartment,
        "username": user.username,
        "status": user.status,
    }


@connection
async def get_user_row_by_tg(session: AsyncSession, telegram_id: int) -> Optional[User]:
    q = select(User).where(User.telegram_id == telegram_id)
    return (await session.execute(q)).scalar_one_or_none()


# ========= Показания счётчиков (НОВАЯ МОДЕЛЬ MeterReading) =========
@connection
async def get_meter_history_by_month(
    session: AsyncSession,
    telegram_id: int,
    meter_type: str,
    month: int,
    year: int,
) -> List[Dict[str, Any]]:
    """Получить показания счётчика за месяц с номерами счётчиков."""
    user_query = select(User).where(User.telegram_id == telegram_id)
    user: User | None = (await session.execute(user_query)).scalar_one_or_none()

    if not user:
        return []

    meter_query = (
        select(MeterReading)
        .where(
            MeterReading.user_id == user.id,
            MeterReading.meter_type == meter_type,
            extract("month", MeterReading.reading_date) == month,
            extract("year", MeterReading.reading_date) == year,
        )
        .order_by(
            MeterReading.meter_number.asc(),
            MeterReading.reading_date.desc()
        )
    )

    result = await session.execute(meter_query)
    readings = result.scalars().all()

    return [
        {
            "meter_number": reading.meter_number or 1,
            "date": reading.reading_date.strftime("%d.%m.%Y"),
            "value": reading.value,
            "created_at": reading.created_at,
            "created_at_local": _fmt_irkt(reading.created_at),
        }
        for reading in readings
    ]


@connection
async def save_meter_reading(
    session: AsyncSession,
    telegram_id: int,
    meter_type: str,
    value: str,
    reading_date: date,
    meter_number: int = 1,
) -> bool:
    """
    Сохранить показания счётчика с номером.

    ВСЕГДА создаём новую запись, ничего не перезаписываем.

    Args:
        telegram_id: ID пользователя в Telegram
        meter_type: Тип счётчика ('hot')
        value: Значение показаний
        reading_date: Дата показаний
        meter_number: Номер счётчика (1-3)
    """
    user_query = select(User).where(User.telegram_id == telegram_id)
    user: User | None = (await session.execute(user_query)).scalar_one_or_none()

    if not user:
        logger.error(f"User {telegram_id} not found")
        return False

    new_reading = MeterReading(
        user_id=user.id,
        meter_type=meter_type,
        meter_number=meter_number,
        value=value,
        reading_date=reading_date,
        created_at=_irkt_now(),
    )
    session.add(new_reading)
    logger.info(
        f"Saved new meter reading for user {telegram_id}: "
        f"{meter_type} #{meter_number} = {value} ({reading_date})"
    )

    return True



@connection
async def get_user_meters_count_for_month(
    session: AsyncSession,
    telegram_id: int,
    month: int,
    year: int,
) -> int:
    """
    Получить количество переданных счётчиков ГВС за месяц.
    
    Args:
        telegram_id: ID пользователя в Telegram
        month: Месяц (1-12)
        year: Год
        
    Returns:
        Количество уникальных счётчиков
    """
    user = (await session.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
    if not user:
        return 0

    count = await session.scalar(
        select(func.count(distinct(MeterReading.meter_number)))
        .where(
            MeterReading.user_id == user.id,
            MeterReading.meter_type == "hot",
            extract("year", MeterReading.reading_date) == year,
            extract("month", MeterReading.reading_date) == month,
        )
    )
    return count or 0


@connection
async def check_month_meters(
    session: AsyncSession,
    telegram_id: int,
    when: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Возвращает информацию о показаниях ГВС за текущий месяц (Irkutsk TZ).

    Возвращает:
    - period: {month, year}
    - hot: {
        exists: bool,
        value: str | None,              # последнее значение
        date: str | None,               # дата последнего значения
        created_at_local: str | None,   # когда введено (локально)
        readings: List[{
            meter_number: int,
            date: str,
            value: str,
            created_at_local: str | None,
        }]
      }
    """
    user = (await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )).scalar_one_or_none()

    if not user:
        return {
            "period": None,
            "hot": {
                "exists": False,
                "value": None,
                "date": None,
                "created_at_local": None,
                "readings": [],
            },
        }

    now_irkt = (when or datetime.utcnow()).astimezone(IRKUTSK_TZ)
    m, y = now_irkt.month, now_irkt.year

    # Все показания за месяц
    q_all = (
        select(MeterReading)
        .where(
            MeterReading.user_id == user.id,
            MeterReading.meter_type == "hot",
            extract("month", MeterReading.reading_date) == m,
            extract("year", MeterReading.reading_date) == y,
        )
        .order_by(
            MeterReading.meter_number.asc(),
            MeterReading.reading_date.desc(),
            MeterReading.created_at.desc(),
        )
    )
    rows = (await session.execute(q_all)).scalars().all()

    hot_row: Optional[MeterReading] = rows[0] if rows else None

    readings = [
        {
            "meter_number": r.meter_number or 1,
            "date": r.reading_date.strftime("%d.%m.%Y") if r.reading_date else None,
            "value": r.value,
            "created_at_local": _fmt_irkt(r.created_at) if r.created_at else None,
        }
        for r in rows
    ]

    return {
        "period": {"month": m, "year": y},
        "hot": {
            "exists": bool(hot_row),
            "value": hot_row.value if hot_row else None,
            "date": hot_row.reading_date.strftime("%d.%m.%Y") if hot_row and hot_row.reading_date else None,
            "created_at_local": _fmt_irkt(hot_row.created_at) if hot_row else None,
            "readings": readings,
        },
    }



@connection
async def get_all_meter_readings_by_type_and_period(
    session,
    meter_type: str,
    period: str,
    month: int = None,
    year: int = None
) -> list[dict]:
    """
    Получить все показания счётчиков по типу и периоду для экспорта.
    """
    from sqlalchemy import extract, func, cast, Date as SQLDate
    
    # Базовый запрос с приведением типов
    query = select(
        MeterReading.id,
        MeterReading.meter_number,
        MeterReading.value,
        MeterReading.reading_date.label("reading_date"),
        MeterReading.created_at.label("created_at"),
        User.name,
        User.phone,
        User.street,
        User.house,
        User.apartment
    ).join(
        User, MeterReading.user_id == User.id
    ).where(
        MeterReading.meter_type == meter_type
    )

    # Фильтры по периоду
    now = datetime.now()
    
    if period == "current_month":
        query = query.where(
            extract('year', MeterReading.reading_date) == now.year,
            extract('month', MeterReading.reading_date) == now.month
        )
    elif period == "select_month" and month and year:
        query = query.where(
            extract('year', MeterReading.reading_date) == year,
            extract('month', MeterReading.reading_date) == month
        )
    elif period == "year":
        query = query.where(
            extract('year', MeterReading.reading_date) == now.year
        )
    # period == "all" - без фильтра

    # Сортировка
    query = query.order_by(
        MeterReading.reading_date.desc(),
        MeterReading.meter_number.asc()
    )

    result = await session.execute(query)
    rows = result.fetchall()

    # ✅ Преобразуем в словари
    data: list[dict] = []
    for row in rows:
        data.append(dict(row._mapping))

    return data


@connection
async def list_users_missing_month_meters(
    session: AsyncSession,
    when: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """
    Возвращает список пользователей, у которых в ТЕКУЩЕМ месяце
    нет показаний ГВС (минимум 1 счётчик не передан).
    """
    now_irkt = (when or datetime.utcnow()).astimezone(IRKUTSK_TZ)
    m, y = now_irkt.month, now_irkt.year

    u = User

    # Проверяем наличие хотя бы одного показания ГВС
    hot_exists = exists(
        select(MeterReading.id).where(
            MeterReading.user_id == u.id,
            MeterReading.meter_type == "hot",
            extract("month", MeterReading.reading_date) == m,
            extract("year", MeterReading.reading_date) == y,
        )
    )

    # Берём всех активных пользователей без показаний
    q = (
        select(
            u.id,
            u.telegram_id,
            u.name,
            u.username,
            u.status,
            hot_exists.label("hot_exists"),
        )
        .where(u.status != "new")
        .where(~hot_exists)  # Нет показаний ГВС
    )

    rows = (await session.execute(q)).all()
    out: List[Dict[str, Any]] = []
    for r in rows:
        mapp = r._mapping
        out.append(
            {
                "id": mapp["id"],
                "telegram_id": mapp["telegram_id"],
                "name": mapp["name"],
                "username": mapp["username"],
                "status": mapp["status"],
                "hot_exists": bool(mapp["hot_exists"]),
                "cold_exists": False,  # Больше не используется
                "month": m,
                "year": y,
            }
        )
    return out


# ========= Заявки =========
@connection
async def get_active_ticket(session: AsyncSession, telegram_id: int) -> Optional[Ticket]:
    q_user = select(User).where(User.telegram_id == telegram_id)
    user: User | None = (await session.execute(q_user)).scalar_one_or_none()
    if not user:
        return None

    q = (
        select(Ticket)
        .where(
            Ticket.user_id == user.id,
            Ticket.status != TicketStatus.CANCELLED,
        )
        .order_by(Ticket.created_at.desc())
    )
    result = await session.execute(q)
    return result.scalars().first()


@connection
async def create_ticket(session: AsyncSession, telegram_id: int, text: str) -> Ticket:
    q_user = select(User).where(User.telegram_id == telegram_id)
    user: User | None = (await session.execute(q_user)).scalar_one_or_none()
    if not user:
        raise ValueError("User not found")

    ticket = Ticket(
        user_id=user.id,
        text=text.strip(),
        status=TicketStatus.OPEN,
    )
    session.add(ticket)
    await session.flush()
    return ticket


@connection
async def cancel_ticket(session: AsyncSession, telegram_id: int, ticket_id: int) -> bool:
    user = (await session.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
    if not user:
        return False

    q_ticket = select(Ticket).where(
        Ticket.id == ticket_id,
        Ticket.user_id == user.id,
        Ticket.status.in_([TicketStatus.OPEN, TicketStatus.WORK]),
    )
    ticket = (await session.execute(q_ticket)).scalar_one_or_none()
    if not ticket:
        return False

    ticket.status = TicketStatus.CANCELLED
    session.add(ticket)
    return True


@connection
async def get_ticket_by_id(session: AsyncSession, ticket_id: int) -> Optional[Dict[str, Any]]:
    t: Ticket | None = (await session.execute(select(Ticket).where(Ticket.id == ticket_id))).scalar_one_or_none()
    if not t:
        return None

    human_status = getattr(TicketStatus, "label", lambda v: v.name if hasattr(v, "name") else str(v))(t.status)

    return {
        "id": t.id,
        "user_id": t.user_id,
        "text": t.text,
        "status": t.status,
        "status_label": human_status,
        "created_at": t.created_at,
        "created_at_local": _fmt_irkt(t.created_at),
        "updated_at": t.updated_at,
        "updated_at_local": _fmt_irkt(t.updated_at),
    }


_admin_cache: list[int] = []


@connection
async def list_admin_ids(session: AsyncSession) -> list[int]:
    """Получить список всех Telegram ID администраторов (с кешом)."""
    global _admin_cache
    if _admin_cache:
        return _admin_cache

    result = await session.execute(select(Admin.telegram_id))
    _admin_cache = [row[0] for row in result.all()]
    return _admin_cache


@connection
async def list_tickets(
    session: AsyncSession,
    status: TicketStatus,
    page: int = 1,
    per_page: int = 5,
) -> List[Dict[str, Any]]:
    offset = max(0, (page - 1) * per_page)

    q = (
        select(Ticket, User)
        .join(User, User.id == Ticket.user_id)
        .where(Ticket.status == status)
        .order_by(Ticket.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    rows = (await session.execute(q)).all()

    items: List[Dict[str, Any]] = []
    for t, u in rows:
        items.append(
            {
                "id": t.id,
                "text": t.text,
                "status": t.status,
                "created_at": t.created_at,
                "created_at_local": _fmt_irkt(t.created_at),
                "updated_at": t.updated_at,
                "updated_at_local": _fmt_irkt(t.updated_at),
                "user_name": u.name,
                "user_telegram_id": u.telegram_id,
                "username": u.username,
            }
        )
    return items


@connection
async def count_tickets(session: AsyncSession, status: TicketStatus) -> int:
    q = select(func.count()).select_from(Ticket).where(Ticket.status == status)
    return (await session.execute(q)).scalar_one()


@connection
async def get_ticket_full(session: AsyncSession, ticket_id: int) -> Optional[Dict[str, Any]]:
    q = select(Ticket, User).join(User, User.id == Ticket.user_id).where(Ticket.id == ticket_id)
    row = (await session.execute(q)).one_or_none()
    if not row:
        return None
    t, u = row
    return {
        "id": t.id,
        "text": t.text,
        "status": t.status,
        "created_at": t.created_at,
        "created_at_local": _fmt_irkt(t.created_at),
        "updated_at": t.updated_at,
        "updated_at_local": _fmt_irkt(t.updated_at),
        "user_name": u.name,
        "user_telegram_id": u.telegram_id,
        "username": u.username,
        "address": f"{u.street or ''}, д. {u.house or ''}" + (f", кв. {u.apartment}" if u.apartment else ""),
    }


@connection
async def update_ticket_status(
    session: AsyncSession,
    ticket_id: int,
    new_status: TicketStatus,
) -> Optional[Tuple[TicketStatus, TicketStatus, int]]:
    q = select(Ticket).where(Ticket.id == ticket_id)
    t: Ticket | None = (await session.execute(q)).scalar_one_or_none()
    if not t:
        return None
    old = t.status
    t.status = new_status
    session.add(t)
    u: User | None = (await session.execute(select(User).where(User.id == t.user_id))).scalar_one_or_none()
    return (old, new_status, u.telegram_id if u else 0)


@connection
async def count_user_tickets_grouped(session: AsyncSession, telegram_id: int) -> Dict[str, int]:
    """
    Считает количество заявок пользователя по статусам.
    """
    user = (await session.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
    if not user:
        return {"OPEN": 0, "WORK": 0, "CANCELLED": 0, "active": 0, "total": 0}

    q = select(Ticket.status, func.count(Ticket.id)).where(Ticket.user_id == user.id).group_by(Ticket.status)
    rows = (await session.execute(q)).all()

    counters = {"OPEN": 0, "WORK": 0, "CANCELLED": 0}
    for status, cnt in rows:
        key = getattr(status, "name", str(status))
        if key in counters:
            counters[key] = cnt

    active = counters["OPEN"] + counters["WORK"]
    total = counters["OPEN"] + counters["WORK"] + counters["CANCELLED"]

    counters["active"] = active
    counters["total"] = total
    return counters


@connection
async def set_ticket_thread(session: AsyncSession, ticket_id: int, group_chat_id: int, thread_id: int) -> None:
    t: Ticket | None = (await session.execute(select(Ticket).where(Ticket.id == ticket_id))).scalar_one_or_none()
    if not t:
        return
    t.group_chat_id = group_chat_id
    t.thread_id = thread_id
    session.add(t)


@connection
async def add_ticket_attachment(
    session: AsyncSession,
    ticket_id: int,
    file_id: str,
    file_unique_id: str | None,
    atype: AttachmentType,
    caption: str | None,
) -> None:
    session.add(
        TicketAttachment(
            ticket_id=ticket_id,
            file_id=file_id,
            file_unique_id=file_unique_id,
            type=atype,
            caption=caption,
        )
    )


@connection
async def get_ticket_attachments(session: AsyncSession, ticket_id: int) -> list[TicketAttachment]:
    q = select(TicketAttachment).where(TicketAttachment.ticket_id == ticket_id).order_by(TicketAttachment.created_at.asc())
    res = await session.execute(q)
    return list(res.scalars().all())


@connection
async def get_ticket_by_thread(session: AsyncSession, chat_id: int, thread_id: int) -> dict | None:
    stmt = (
        select(
            Ticket.id,
            Ticket.status,
            Ticket.group_chat_id,
            Ticket.thread_id,
            Ticket.created_at,
            Ticket.text,
            User.telegram_id.label("user_tg_id"),
        )
        .join(User, User.id == Ticket.user_id, isouter=True)
        .where(Ticket.group_chat_id == chat_id, Ticket.thread_id == thread_id)
        .limit(1)
    )
    row = (await session.execute(stmt)).one_or_none()
    if not row:
        return None

    r = row._mapping
    return {
        "id": r["id"],
        "status": r["status"],
        "group_chat_id": r["group_chat_id"],
        "thread_id": r["thread_id"],
        "created_at": r["created_at"],
        "created_at_local": _fmt_irkt(r["created_at"]),
        "text": r["text"],
        "user_tg_id": r["user_tg_id"],
    }


@connection
async def set_ticket_status(
    session: AsyncSession,
    ticket_id: int,
    new_status: TicketStatus,
) -> tuple[TicketStatus, TicketStatus, int] | None:
    row = (
        await session.execute(
            select(Ticket, User.telegram_id)
            .join(User, User.id == Ticket.user_id, isouter=True)
            .where(Ticket.id == ticket_id)
            .limit(1)
        )
    ).one_or_none()

    if not row:
        return None

    t, author_tg = row
    old = t.status
    t.status = new_status
    session.add(t)

    return (old, new_status, author_tg or 0)


@connection
async def list_user_tickets(
    session: AsyncSession,
    telegram_id: int,
    status: TicketStatus,
    page: int = 1,
    per_page: int = 5,
) -> List[Dict[str, Any]]:
    offset = max(0, (page - 1) * per_page)

    u = (await session.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
    if not u:
        return []

    q = (
        select(Ticket)
        .where(Ticket.user_id == u.id, Ticket.status == status)
        .order_by(Ticket.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    rows = (await session.execute(q)).scalars().all()

    items: List[Dict[str, Any]] = []
    for t in rows:
        items.append(
            {
                "id": t.id,
                "text": t.text,
                "status": t.status,
                "created_at": t.created_at,
                "created_at_local": _fmt_irkt(t.created_at),
                "updated_at": t.updated_at,
                "updated_at_local": _fmt_irkt(t.updated_at),
            }
        )
    return items


@connection
async def count_user_tickets(session: AsyncSession, telegram_id: int, status: TicketStatus) -> int:
    u = (await session.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
    if not u:
        return 0
    q = select(func.count()).select_from(Ticket).where(Ticket.user_id == u.id, Ticket.status == status)
    return (await session.execute(q)).scalar_one()


@connection
async def get_user_ticket_full(
    session: AsyncSession,
    telegram_id: int,
    ticket_id: int,
) -> Optional[Dict[str, Any]]:
    """Карточка заявки только для владельца."""
    row = (
        await session.execute(
            select(Ticket, User)
            .join(User, User.id == Ticket.user_id)
            .where(Ticket.id == ticket_id, User.telegram_id == telegram_id)
        )
    ).one_or_none()
    if not row:
        return None
    t, u = row
    return {
        "id": t.id,
        "text": t.text,
        "status": t.status,
        "created_at": t.created_at,
        "created_at_local": _fmt_irkt(t.created_at),
        "updated_at": t.updated_at,
        "updated_at_local": _fmt_irkt(t.updated_at),
        "user_name": u.name,
        "user_telegram_id": u.telegram_id,
        "username": u.username,
        "address": f"{u.street or ''}, д. {u.house or ''}" + (f", кв. {u.apartment}" if u.apartment else ""),
    }


@connection
async def get_ticket_thread_info(session: AsyncSession, ticket_id: int) -> Optional[Tuple[int, int]]:
    """Вернёт (group_chat_id, message_thread_id) для заявки."""
    t: Ticket | None = (
        await session.execute(select(Ticket.group_chat_id, Ticket.thread_id).where(Ticket.id == ticket_id))
    ).one_or_none()
    if not t:
        return None
    group_chat_id, thread_id = t
    if group_chat_id is None or thread_id is None:
        return None
    return int(group_chat_id), int(thread_id)