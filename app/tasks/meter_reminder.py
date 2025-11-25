# app/tasks/meter_reminder.py
from __future__ import annotations

import asyncio
import calendar
from datetime import datetime

import pytz
from aiogram import Bot

import app.user.keyboards.user_kb as kb
from app.logger import logger
from config.settings import (
    IRKUTSK_TZ_NAME,
    METER_REMIND_HOUR,
    METER_REMIND_MINUTE,
    METER_REMIND_START_DAY,
)
from database.requests import list_users_missing_month_meters

IRKUTSK_TZ = pytz.timezone(IRKUTSK_TZ_NAME)

MONTHS_RU = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
]


def _last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _dt_irkt(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    """Создаёт локальное время Иркутска."""
    naive = datetime(
        year, month,
        min(day, _last_day_of_month(year, month)),
        hour, minute, 0
    )
    return IRKUTSK_TZ.localize(naive)


def _next_run_dt(now_irkt: datetime) -> datetime:
    """
    Расписание: один раз в месяц, 24 числа, в заданное время.

    Если сейчас до 24-го числа (или раньше нужного времени 24-го) —
    шлём напоминание в этот месяц.

    Если уже после времени напоминания 24-го — переносим на 24-е
    число следующего месяца.
    """
    y, m, d = now_irkt.year, now_irkt.month, now_irkt.day

    # Напоминание в этом месяце — 24-е число
    run_this_month = _dt_irkt(
        y,
        m,
        METER_REMIND_START_DAY,
        METER_REMIND_HOUR,
        METER_REMIND_MINUTE,
    )

    if now_irkt < run_this_month:
        # Ещё не дошли до 24-го (или до времени) — шлём в этом месяце
        return run_this_month

    # Иначе — следующий месяц, 24-е число
    if m == 12:
        y += 1
        m = 1
    else:
        m += 1

    return _dt_irkt(
        y,
        m,
        METER_REMIND_START_DAY,
        METER_REMIND_HOUR,
        METER_REMIND_MINUTE,
    )



async def _sleep_until(dt_irkt: datetime) -> None:
    """Ожидание до указанного времени с периодической проверкой."""
    while True:
        now = datetime.utcnow().replace(tzinfo=pytz.utc).astimezone(IRKUTSK_TZ)
        sec = (dt_irkt - now).total_seconds()
        if sec <= 0:
            return
        await asyncio.sleep(min(sec, 60))


async def _send_reminders(bot: Bot) -> None:
    """Отправка напоминаний о холодной воде."""
    users = await list_users_missing_month_meters()
    if not users:
        logger.info("[meter_reminder] Все пользователи передали показания — рассылка пропущена.")
        return

    any_row = users[0]
    month, year = any_row["month"], any_row["year"]
    month_name = MONTHS_RU[month] if 1 <= month <= 12 else ""

    sent_count = 0
    for user in users:
        tg_id = user["telegram_id"]
        cold_ok = user["cold_exists"]

        if cold_ok:
            continue

        text = (
            f"💧 Напоминание за {month_name} {year}.\n\n"
            f"У вас не переданы показания холодной воды.\n"
            f"Пожалуйста, передайте показания в боте."
        )

        try:
            await bot.send_message(
                chat_id=tg_id,
                text=text,
                disable_notification=True,
                reply_markup=kb.type_meter_menu()
            )
            sent_count += 1
            await asyncio.sleep(0.03)
        except Exception as e:
            logger.error(f"[meter_reminder] Не удалось отправить напоминание {tg_id}: {e}")

    logger.info(f"[meter_reminder] Отправлено {sent_count} напоминаний о холодной воде.")


async def meter_reminder_loop(bot: Bot) -> None:
    """Основной цикл задачи напоминаний."""
    logger.info("[meter_reminder] Фоновая задача запущена")

    while True:
        try:
            now_irkt = datetime.utcnow().replace(tzinfo=pytz.utc).astimezone(IRKUTSK_TZ)
            nxt = _next_run_dt(now_irkt)
            logger.info(f"[meter_reminder] Следующий запуск: {nxt.isoformat()}")

            await _sleep_until(nxt)
            await _send_reminders(bot)

            # Пауза, чтобы не сработать повторно в ту же минуту
            await asyncio.sleep(60)

        except asyncio.CancelledError:
            logger.info("[meter_reminder] Задача отменена")
            raise
        except Exception as e:
            logger.exception(f"[meter_reminder] Ошибка цикла: {e}")
            await asyncio.sleep(60)