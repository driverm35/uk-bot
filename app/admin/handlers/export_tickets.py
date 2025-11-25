# app/admin/handlers/export_tickets.py
from __future__ import annotations

import csv
import json
import os
import tempfile
from datetime import date, datetime

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.admin.filters import AdminFilter
from app.admin.keyboards.admin_kb import AdminCb
import app.admin.keyboards.admin_kb as kb
from app.message_utils import replace_or_send_message
from app.logger import logger
from app.helpers import save_msg
from database.export_queries import get_tickets_for_export

export_tickets_router = Router(name="export_tickets_router")
export_tickets_router.message.filter(AdminFilter())
export_tickets_router.callback_query.filter(AdminFilter())


class ExportTicketsStates(StatesGroup):
    select_period = State()
    select_month = State()
    enter_custom_dates = State()
    select_format = State()


MONTHS = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
]

PERIOD_LABELS = {
    "today": "Сегодня",
    "week": "Текущая неделя",
    "month": "Текущий месяц",
    "all": "Все данные",
    "select_month": "Выбранный месяц",
    "custom": "Произвольный период",
}


@export_tickets_router.callback_query(AdminCb.filter(F.a == "admin_export_tickets"))
async def export_tickets_start(callback: CallbackQuery, state: FSMContext):
    """Начало экспорта заявок."""
    logger.info(f"Admin {callback.from_user.id} started tickets export")
    await state.clear()
    await state.set_state(ExportTicketsStates.select_period)

    await replace_or_send_message(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        text="📊 <b>Выгрузка заявок</b>\n\nВыберите период:",
        reply_markup=kb.tickets_export_period_menu(),
        parse_mode="HTML"
    )
    await callback.answer()


@export_tickets_router.callback_query(AdminCb.filter(F.a == "tex_period"))
async def export_select_period(callback: CallbackQuery, callback_data: AdminCb, state: FSMContext):
    """Выбор периода для экспорта."""
    period = callback_data.period
    logger.info(f"Admin {callback.from_user.id} selected period: {period}")

    await state.update_data(period=period)

    if period == "select_month":
        # Переход к выбору месяца
        await state.set_state(ExportTicketsStates.select_month)
        current_year = datetime.now().year

        await replace_or_send_message(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            text=f"📊 <b>Выгрузка заявок</b>\n\nВыберите месяц ({current_year}):",
            reply_markup=kb.tickets_export_month_menu(current_year),
            parse_mode="HTML"
        )
    elif period == "custom":
        # Запрос произвольного периода
        await state.set_state(ExportTicketsStates.enter_custom_dates)

        sent = await replace_or_send_message(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            text=(
                "📊 <b>Выгрузка заявок</b>\n\n"
                "Введите период в формате:\n"
                "<code>ДД.ММ.ГГ-ДД.ММ.ГГ</code>\n\n"
                "Например: <code>01.01.25-31.01.25</code>"
            ),
            reply_markup=kb.tickets_export_back_menu(),
            parse_mode="HTML"
        )
        await save_msg(sent, state)
    else:
        # Переход к выбору формата
        await state.set_state(ExportTicketsStates.select_format)

        await replace_or_send_message(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            text=(
                f"📊 <b>Выгрузка заявок</b>\n"
                f"Период: <b>{PERIOD_LABELS.get(period, period)}</b>\n\n"
                f"Выберите формат файла:"
            ),
            reply_markup=kb.tickets_export_format_menu(),
            parse_mode="HTML"
        )

    await callback.answer()


@export_tickets_router.callback_query(AdminCb.filter(F.a == "tex_month"))
async def export_select_month(callback: CallbackQuery, callback_data: AdminCb, state: FSMContext):
    """Выбор конкретного месяца."""
    month = callback_data.month
    year = callback_data.year
    logger.info(f"Admin {callback.from_user.id} selected month: {month}/{year}")

    await state.update_data(month=month, year=year)
    await state.set_state(ExportTicketsStates.select_format)

    await replace_or_send_message(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        text=(
            f"📊 <b>Выгрузка заявок</b>\n"
            f"Период: <b>{MONTHS[month]} {year}</b>\n\n"
            f"Выберите формат файла:"
        ),
        reply_markup=kb.tickets_export_format_menu(),
        parse_mode="HTML"
    )
    await callback.answer()


@export_tickets_router.message(ExportTicketsStates.enter_custom_dates)
async def export_custom_dates(message: Message, state: FSMContext):
    """Обработка ввода произвольного периода."""
    text = message.text.strip()
    await save_msg(message, state)

    try:
        parts = text.split("-")
        if len(parts) != 2:
            raise ValueError("Неверный формат")

        date_from = datetime.strptime(parts[0].strip(), "%d.%m.%y").date()
        date_to = datetime.strptime(parts[1].strip(), "%d.%m.%y").date()

        if date_from > date_to:
            date_from, date_to = date_to, date_from

        await state.update_data(date_from=date_from.isoformat(), date_to=date_to.isoformat())
        await state.set_state(ExportTicketsStates.select_format)

        await message.answer(
            f"📊 <b>Выгрузка заявок</b>\n"
            f"Период: <b>{date_from.strftime('%d.%m.%Y')} - {date_to.strftime('%d.%m.%Y')}</b>\n\n"
            f"Выберите формат файла:",
            reply_markup=kb.tickets_export_format_menu(),
            parse_mode="HTML"
        )

    except ValueError:
        await message.answer(
            "❌ Неверный формат даты.\n\n"
            "Используйте формат: <code>ДД.ММ.ГГ-ДД.ММ.ГГ</code>\n"
            "Например: <code>01.01.25-31.01.25</code>",
            reply_markup=kb.tickets_export_back_menu(),
            parse_mode="HTML"
        )


@export_tickets_router.callback_query(AdminCb.filter(F.a == "tex_format"))
async def export_generate_file(callback: CallbackQuery, callback_data: AdminCb, state: FSMContext):
    """Генерация и отправка файла экспорта."""
    file_format = callback_data.format
    data = await state.get_data()

    period = data.get("period", "all")
    month = data.get("month")
    year = data.get("year")
    date_from_str = data.get("date_from")
    date_to_str = data.get("date_to")

    # Конвертируем даты
    date_from = date.fromisoformat(date_from_str) if date_from_str else None
    date_to = date.fromisoformat(date_to_str) if date_to_str else None

    logger.info(f"Admin {callback.from_user.id} generating tickets export: format={file_format}")

    # Показываем процесс
    await callback.message.edit_text(
        "⏳ Формирую файл, подождите...",
        parse_mode="HTML"
    )

    try:
        # Получаем данные
        tickets = await get_tickets_for_export(
            period=period,
            month=month,
            year=year,
            date_from=date_from,
            date_to=date_to
        )

        if not tickets:
            await callback.message.edit_text(
                "📭 Нет заявок за выбранный период.",
                reply_markup=kb.tickets_export_period_menu()
            )
            await state.clear()
            await callback.answer()
            return

        # Генерируем файл
        filename = f"tickets_{period}"
        if month and year:
            filename = f"tickets_{year}_{month:02d}"
        elif date_from and date_to:
            filename = f"tickets_{date_from.strftime('%d%m%y')}_{date_to.strftime('%d%m%y')}"

        if file_format == "csv":
            file_path = await _generate_tickets_csv(tickets, filename)
        else:
            file_path = await _generate_tickets_xlsx(tickets, filename)

        if not file_path:
            raise Exception("Не удалось создать файл")

        # Отправляем файл
        document = FSInputFile(file_path)
        await callback.message.answer_document(
            document=document,
            caption=f"📊 Выгрузка заявок\nЗаписей: {len(tickets)}"
        )

        logger.info(f"Tickets export sent: {file_path}")

        # Удаляем временный файл
        try:
            os.unlink(file_path)
        except Exception as e:
            logger.warning(f"Failed to delete temp file {file_path}: {e}")

        # Возвращаемся в меню
        await callback.message.edit_text(
            "✅ Файл успешно сформирован!",
            reply_markup=kb.tickets_export_period_menu()
        )

    except Exception as e:
        logger.error(f"Error generating tickets export: {e}", exc_info=True)
        await callback.message.edit_text(
            f"❌ Ошибка при формировании файла: {e}",
            reply_markup=kb.tickets_export_period_menu()
        )

    await state.clear()
    await callback.answer()


@export_tickets_router.callback_query(AdminCb.filter(F.a == "tex_back"))
async def export_back(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору периода."""
    await state.set_state(ExportTicketsStates.select_period)

    await replace_or_send_message(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        text="📊 <b>Выгрузка заявок</b>\n\nВыберите период:",
        reply_markup=kb.tickets_export_period_menu(),
        parse_mode="HTML"
    )
    await callback.answer()


async def _generate_tickets_csv(tickets: list[dict], filename: str) -> str:
    """Генерация CSV файла с заявками."""
    temp_dir = tempfile.gettempdir()
    filepath = os.path.join(temp_dir, f"{filename}.csv")

    with open(filepath, 'w', newline='', encoding='utf-8-sig') as csvfile:
        writer = csv.writer(csvfile, delimiter=';')

        # Заголовки
        writer.writerow([
            'Дата', 'Номер заявки', 'Адрес', 'Телефон', 'Вид работ', 'Статус'
        ])

        # Данные
        for ticket in tickets:
            created = ticket['created_at'].strftime('%d.%m.%Y %H:%M') if ticket['created_at'] else ''
            writer.writerow([
                created,
                ticket['id'],
                ticket['address'],
                ticket['phone'],
                ticket['text'][:100] + '...' if len(ticket['text']) > 100 else ticket['text'],
                ticket['status']
            ])

    return filepath


async def _generate_tickets_xlsx(tickets: list[dict], filename: str) -> str:
    """Генерация Excel файла с заявками."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment
    except ImportError:
        logger.error("openpyxl not installed, falling back to CSV")
        return await _generate_tickets_csv(tickets, filename)

    temp_dir = tempfile.gettempdir()
    filepath = os.path.join(temp_dir, f"{filename}.xlsx")

    wb = Workbook()
    ws = wb.active
    ws.title = "Заявки"

    # Заголовки
    headers = ['Дата', 'Номер заявки', 'Адрес', 'Телефон', 'Вид работ', 'Статус']
    ws.append(headers)

    # Стиль заголовков
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal='center')

    # Данные
    for ticket in tickets:
        created = ticket['created_at'].strftime('%d.%m.%Y %H:%M') if ticket['created_at'] else ''
        ws.append([
            created,
            ticket['id'],
            ticket['address'],
            ticket['phone'],
            ticket['text'],
            ticket['status']
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