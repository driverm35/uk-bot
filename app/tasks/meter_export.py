# app/tasks/meter_export.py
from __future__ import annotations

import asyncio
import csv
import os
import tempfile
from datetime import date, datetime
from pathlib import Path

import pytz

from app.logger import logger
from app.services.email_service import send_email
from config.settings import (
    ACCOUNTANT_EMAIL,
    IRKUTSK_TZ_NAME,
    METER_EXPORT_DAY,
    METER_EXPORT_HOUR,
    METER_EXPORT_MINUTE,
)
from database.export_queries import get_cold_water_readings_for_export

IRKUTSK_TZ = pytz.timezone(IRKUTSK_TZ_NAME)

MONTHS_RU = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
]


def _dt_irkt(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    """Создаёт локальное время Иркутска."""
    from calendar import monthrange
    last_day = monthrange(year, month)[1]
    naive = datetime(year, month, min(day, last_day), hour, minute, 0)
    return IRKUTSK_TZ.localize(naive)


def _next_export_dt(now_irkt: datetime) -> datetime:
    """
    Вычисляет следующую дату экспорта.
    Экспорт происходит METER_EXPORT_DAY числа каждого месяца.
    """
    y, m, d = now_irkt.year, now_irkt.month, now_irkt.day

    # Время экспорта в этом месяце
    export_dt = _dt_irkt(y, m, METER_EXPORT_DAY, METER_EXPORT_HOUR, METER_EXPORT_MINUTE)

    if now_irkt < export_dt:
        # Ещё не наступило — возвращаем эту дату
        return export_dt

    # Уже прошло — переходим на следующий месяц
    if m == 12:
        return _dt_irkt(y + 1, 1, METER_EXPORT_DAY, METER_EXPORT_HOUR, METER_EXPORT_MINUTE)
    return _dt_irkt(y, m + 1, METER_EXPORT_DAY, METER_EXPORT_HOUR, METER_EXPORT_MINUTE)


async def _sleep_until(dt_irkt: datetime) -> None:
    """Ожидание до указанного времени."""
    while True:
        now = datetime.utcnow().replace(tzinfo=pytz.utc).astimezone(IRKUTSK_TZ)
        sec = (dt_irkt - now).total_seconds()
        if sec <= 0:
            return
        await asyncio.sleep(min(sec, 60))


async def _generate_cold_water_csv(readings: list[dict], filename: str) -> Path:
    """Генерация CSV файла с показаниями холодной воды."""
    temp_dir = tempfile.gettempdir()
    filepath = Path(temp_dir) / f"{filename}.csv"

    with open(filepath, 'w', newline='', encoding='utf-8-sig') as csvfile:
        writer = csv.writer(csvfile, delimiter=';')

        # Заголовки
        writer.writerow([
            'ФИО', 'Адрес', 'Телефон', 'Показания (м³)', 'Дата показания', 'Дата внесения'
        ])

        # Данные
        for reading in readings:
            reading_date = reading['reading_date'].strftime('%d.%m.%Y') if reading['reading_date'] else ''
            created_at = reading['created_at'].strftime('%d.%m.%Y %H:%M') if reading['created_at'] else ''

            writer.writerow([
                reading['user_name'],
                reading['address'],
                reading['phone'],
                reading['value'],
                reading_date,
                created_at
            ])

    return filepath


async def _generate_cold_water_xlsx(readings: list[dict], filename: str) -> Path:
    """Генерация Excel файла с показаниями холодной воды."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment
    except ImportError:
        logger.error("openpyxl not installed, falling back to CSV")
        return await _generate_cold_water_csv(readings, filename)

    temp_dir = tempfile.gettempdir()
    filepath = Path(temp_dir) / f"{filename}.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = "Холодная вода"

    # Заголовки
    headers = ['ФИО', 'Адрес', 'Телефон', 'Показания (м³)', 'Дата показания', 'Дата внесения']
    ws.append(headers)

    # Стиль заголовков
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal='center')

    # Данные
    for reading in readings:
        reading_date = reading['reading_date'].strftime('%d.%m.%Y') if reading['reading_date'] else ''
        created_at = reading['created_at'].strftime('%d.%m.%Y %H:%M') if reading['created_at'] else ''

        ws.append([
            reading['user_name'],
            reading['address'],
            reading['phone'],
            reading['value'],
            reading_date,
            created_at
        ])

    # Автоширина столбцов
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width

    wb.save(filepath)
    return filepath


async def _send_meter_export() -> None:
    """Формирует и отправляет отчёт на почту бухгалтера."""
    today = date.today()
    month = today.month
    year = today.year

    # Получаем показания за текущий месяц
    readings = await get_cold_water_readings_for_export(month=month, year=year)

    if not readings:
        logger.info(f"[meter_export] Нет показаний холодной воды за {MONTHS_RU[month]} {year}")
        return

    month_name = MONTHS_RU[month]
    filename = f"cold_water_{year}_{month:02d}"

    # Генерируем файлы
    csv_path = await _generate_cold_water_csv(readings, filename)
    xlsx_path = await _generate_cold_water_xlsx(readings, filename)

    # Формируем письмо
    subject = f"Показания холодной воды за {month_name} {year}"
    body = (
        f"Добрый день!\n\n"
        f"Во вложении показания счётчиков холодной воды за {month_name} {year}.\n"
        f"Всего записей: {len(readings)}\n\n"
        f"С уважением,\n"
        f"Автоматическая система учёта"
    )

    # Отправляем
    success = await send_email(
        to=ACCOUNTANT_EMAIL,
        subject=subject,
        body=body,
        attachments=[xlsx_path, csv_path]
    )

    if success:
        logger.info(f"[meter_export] Отправлено на {ACCOUNTANT_EMAIL}: {len(readings)} записей")
    else:
        logger.error(f"[meter_export] Ошибка отправки на {ACCOUNTANT_EMAIL}")

    # Удаляем временные файлы
    for path in [csv_path, xlsx_path]:
        try:
            os.unlink(path)
        except Exception as e:
            logger.warning(f"Failed to delete temp file {path}: {e}")


async def meter_export_loop() -> None:
    """Основной цикл задачи экспорта показаний."""
    logger.info("[meter_export] Фоновая задача запущена")

    while True:
        try:
            now_irkt = datetime.utcnow().replace(tzinfo=pytz.utc).astimezone(IRKUTSK_TZ)
            nxt = _next_export_dt(now_irkt)
            logger.info(f"[meter_export] Следующий экспорт: {nxt.isoformat()}")

            await _sleep_until(nxt)
            await _send_meter_export()

            # Пауза, чтобы не сработать повторно
            await asyncio.sleep(60)

        except asyncio.CancelledError:
            logger.info("[meter_export] Задача отменена")
            raise
        except Exception as e:
            logger.exception(f"[meter_export] Ошибка цикла: {e}")
            await asyncio.sleep(60)