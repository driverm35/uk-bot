# database/export_queries.py
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal

from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload

from database.models import Ticket, User, MeterReading, TicketStatus, async_session


async def get_tickets_for_export(
    period: Literal["today", "week", "month", "all", "select_month", "custom"],
    month: int | None = None,
    year: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict]:
    """
    Получение заявок для экспорта с фильтрами по периоду.
    
    Args:
        period: Тип периода фильтрации
        month: Месяц (для select_month)
        year: Год (для select_month)
        date_from: Начальная дата (для custom)
        date_to: Конечная дата (для custom)
        
    Returns:
        Список словарей с данными заявок
    """
    async with async_session() as session:
        query = (
            select(Ticket, User)
            .join(User, Ticket.user_id == User.id)
            .order_by(Ticket.created_at.desc())
        )

        today = date.today()

        # Применяем фильтры по периоду
        if period == "today":
            query = query.where(func.date(Ticket.created_at) == today)

        elif period == "week":
            week_start = today - timedelta(days=today.weekday())
            query = query.where(func.date(Ticket.created_at) >= week_start)

        elif period == "month":
            month_start = today.replace(day=1)
            query = query.where(func.date(Ticket.created_at) >= month_start)

        elif period == "select_month" and month and year:
            query = query.where(
                and_(
                    func.extract("month", Ticket.created_at) == month,
                    func.extract("year", Ticket.created_at) == year
                )
            )

        elif period == "custom" and date_from and date_to:
            query = query.where(
                and_(
                    func.date(Ticket.created_at) >= date_from,
                    func.date(Ticket.created_at) <= date_to
                )
            )

        result = await session.execute(query)
        rows = result.all()

        tickets = []
        for ticket, user in rows:
            # Формируем адрес
            address_parts = []
            if user.street:
                address_parts.append(user.street)
            if user.house:
                address_parts.append(f"д. {user.house}")
            if user.apartment:
                address_parts.append(f"кв. {user.apartment}")
            address = ", ".join(address_parts) if address_parts else "—"

            tickets.append({
                "id": ticket.id,
                "created_at": ticket.created_at,
                "address": address,
                "phone": user.phone or "—",
                "text": ticket.text or "—",
                "status": TicketStatus.label(ticket.status),
                "user_name": user.name or "—",
            })

        return tickets


async def get_cold_water_readings_for_export(
    month: int | None = None,
    year: int | None = None,
) -> list[dict]:
    """
    Получение показаний холодной воды для экспорта.
    
    Args:
        month: Месяц (по умолчанию - текущий)
        year: Год (по умолчанию - текущий)
        
    Returns:
        Список словарей с данными показаний
    """
    if month is None:
        month = date.today().month
    if year is None:
        year = date.today().year

    async with async_session() as session:
        query = (
            select(MeterReading, User)
            .join(User, MeterReading.user_id == User.id)
            .where(
                and_(
                    MeterReading.meter_type == "cold",
                    func.extract("month", MeterReading.reading_date) == month,
                    func.extract("year", MeterReading.reading_date) == year
                )
            )
            .order_by(User.name, MeterReading.reading_date)
        )

        result = await session.execute(query)
        rows = result.all()

        readings = []
        for reading, user in rows:
            # Формируем адрес
            address_parts = []
            if user.street:
                address_parts.append(user.street)
            if user.house:
                address_parts.append(f"д. {user.house}")
            if user.apartment:
                address_parts.append(f"кв. {user.apartment}")
            address = ", ".join(address_parts) if address_parts else "—"

            readings.append({
                "id": reading.id,
                "user_name": user.name or "—",
                "address": address,
                "phone": user.phone or "—",
                "value": reading.value,
                "reading_date": reading.reading_date,
                "created_at": reading.created_at,
            })

        return readings