from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, date
import csv
import json
import tempfile
import os
from pathlib import Path

from app.admin.filters import AdminFilter
import app.admin.keyboards.admin_kb as kb
from app.admin.keyboards.admin_kb import AdminCb
from app.message_utils import replace_or_send_message
from app.logger import logger
from database.requests import get_all_meter_readings_by_type_and_period

get_meter_router = Router(name="get_meter_router")
get_meter_router.message.filter(AdminFilter())
get_meter_router.callback_query.filter(AdminFilter())


class ExportStates(StatesGroup):
    select_type = State()
    select_period = State()
    select_month = State()
    select_format = State()


MONTHS = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
          "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]

TYPE_NAMES = {
    "hot": "🔥 Горячая вода",
    "cold": "❄️ Холодная вода"
}


def month_selection_keyboard(meter_type: str, year: int = None):
    """Меню выбора месяца"""
    if year is None:
        year = datetime.now().year

    buttons = []
    for month_num in range(1, 13):
        buttons.append([
            InlineKeyboardButton(
                text=MONTHS[month_num],
                callback_data=AdminCb(a="export_month", type=meter_type, month=month_num, year=year).pack()
            )
        ])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data=AdminCb(a="export_back_to_period", type=meter_type).pack())])

    kb_builder = InlineKeyboardMarkup(inline_keyboard=buttons)
    return kb_builder


def format_selection_keyboard(meter_type: str, period: str, month: int = None, year: int = None):
    """Меню выбора формата файла"""
    kb_builder = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 CSV", callback_data=AdminCb(
            a="export_format", type=meter_type, period=period, month=month or 0, year=year or 0, format="csv"
        ).pack())],
        [InlineKeyboardButton(text="📊 Excel (XLSX)", callback_data=AdminCb(
            a="export_format", type=meter_type, period=period, month=month or 0, year=year or 0, format="xlsx"
        ).pack())],
        [InlineKeyboardButton(text="📋 JSON", callback_data=AdminCb(
            a="export_format", type=meter_type, period=period, month=month or 0, year=year or 0, format="json"
        ).pack())],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=AdminCb(a="export_back_to_period", type=meter_type).pack())]
    ])
    return kb_builder


@get_meter_router.callback_query(AdminCb.filter(F.a == "admin_export_meters"))
async def export_meters_start(callback: CallbackQuery, state: FSMContext):
    """Начало экспорта показаний"""
    logger.info(f"Admin {callback.from_user.id} started meter export")
    await state.clear()
    await state.set_state(ExportStates.select_type)

    await replace_or_send_message(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        text="📊 <b>Выгрузка показаний счётчиков</b>\n\nВыберите тип счётчика:",
        reply_markup=kb.export_menu_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@get_meter_router.callback_query(AdminCb.filter(F.a == "export_type"))
async def export_select_type(callback: CallbackQuery, callback_data: AdminCb, state: FSMContext):
    """Выбор типа счётчика"""
    meter_type = callback_data.type
    logger.info(f"Admin {callback.from_user.id} selected meter type: {meter_type}")

    await state.update_data(meter_type=meter_type)
    await state.set_state(ExportStates.select_period)

    await replace_or_send_message(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        text=f"📊 <b>Выгрузка показаний: {TYPE_NAMES[meter_type]}</b>\n\nВыберите период:",
        reply_markup=kb.period_menu_keyboard(meter_type),
        parse_mode="HTML"
    )
    await callback.answer()


@get_meter_router.callback_query(AdminCb.filter(F.a == "export_period"))
async def export_select_period(callback: CallbackQuery, callback_data: AdminCb, state: FSMContext):
    """Выбор периода"""
    meter_type = callback_data.type
    period = callback_data.period
    logger.info(f"Admin {callback.from_user.id} selected period: {period} for {meter_type}")

    await state.update_data(period=period)

    if period == "select_month":
        # Переход к выбору месяца
        await state.set_state(ExportStates.select_month)
        current_year = datetime.now().year

        await replace_or_send_message(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            text=f"📊 <b>Выгрузка показаний: {TYPE_NAMES[meter_type]}</b>\n\nВыберите месяц ({current_year}):",
            reply_markup=month_selection_keyboard(meter_type, current_year),
            parse_mode="HTML"
        )
    else:
        # Переход к выбору формата
        await state.set_state(ExportStates.select_format)

        period_text = {
            "current_month": "Текущий месяц",
            "year": "Весь год",
            "all": "Все данные"
        }.get(period, period)

        await replace_or_send_message(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            text=f"📊 <b>Выгрузка показаний: {TYPE_NAMES[meter_type]}</b>\n"
                 f"Период: <b>{period_text}</b>\n\nВыберите формат файла:",
            reply_markup=format_selection_keyboard(meter_type, period),
            parse_mode="HTML"
        )

    await callback.answer()


@get_meter_router.callback_query(AdminCb.filter(F.a == "export_month"))
async def export_select_month(callback: CallbackQuery, callback_data: AdminCb, state: FSMContext):
    """Выбор конкретного месяца"""
    meter_type = callback_data.type
    month = callback_data.month
    year = callback_data.year

    logger.info(f"Admin {callback.from_user.id} selected month: {month}/{year} for {meter_type}")

    await state.update_data(month=month, year=year)
    await state.set_state(ExportStates.select_format)

    await replace_or_send_message(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        text=f"📊 <b>Выгрузка показаний: {TYPE_NAMES[meter_type]}</b>\n"
             f"Период: <b>{MONTHS[month]} {year}</b>\n\nВыберите формат файла:",
        reply_markup=format_selection_keyboard(meter_type, "select_month", month, year),
        parse_mode="HTML"
    )
    await callback.answer()


@get_meter_router.callback_query(AdminCb.filter(F.a == "export_format"))
async def export_generate_file(callback: CallbackQuery, callback_data: AdminCb, state: FSMContext):
    """Генерация и отправка файла"""
    meter_type = callback_data.type
    period = callback_data.period
    file_format = callback_data.format
    month = callback_data.month if callback_data.month != 0 else None
    year = callback_data.year if callback_data.year != 0 else None

    logger.info(f"Admin {callback.from_user.id} generating export: type={meter_type}, period={period}, format={file_format}")

    # Показываем процесс
    await callback.message.edit_text(
        "⏳ Формирую файл, подождите...",
        parse_mode="HTML"
    )

    try:
        # Получаем данные из БД
        data = await get_all_meter_readings_by_type_and_period(
            meter_type=meter_type,
            period=period,
            month=month,
            year=year
        )

        if not data:
            logger.warning(f"No data found for export: type={meter_type}, period={period}")
            await callback.message.edit_text(
                "📭 Нет данных для выгрузки за выбранный период.",
                reply_markup=kb.export_menu_keyboard()
            )
            await state.clear()
            await callback.answer()
            return

        logger.info(f"Found {len(data)} records for export")

        # Генерируем файл
        file_path = None
        filename = f"meters_{meter_type}_{period}"

        if month and year:
            filename = f"meters_{meter_type}_{year}_{month:02d}"
        elif year:
            filename = f"meters_{meter_type}_{year}"

        if file_format == "csv":
            file_path = await generate_csv(data, filename)
        elif file_format == "xlsx":
            file_path = await generate_xlsx(data, filename)
        elif file_format == "json":
            file_path = await generate_json(data, filename)

        if not file_path:
            raise Exception("Failed to generate file")

        # Отправляем файл
        document = FSInputFile(file_path)
        await callback.message.answer_document(
            document=document,
            caption=f"📊 Показания счётчика: {TYPE_NAMES[meter_type]}\n"
                   f"Записей: {len(data)}"
        )

        logger.info(f"Export file sent successfully: {file_path}")

        # Удаляем временный файл
        try:
            os.unlink(file_path)
        except Exception as e:
            logger.warning(f"Failed to delete temp file {file_path}: {e}")

        # Возвращаемся в меню
        await callback.message.edit_text(
            "✅ Файл успешно сформирован!",
            reply_markup=kb.export_menu_keyboard()
        )

    except Exception as e:
        logger.error(f"Error generating export file: {e}", exc_info=True)
        await callback.message.edit_text(
            f"❌ Ошибка при формировании файла: {e}",
            reply_markup=kb.export_menu_keyboard()
        )

    await state.clear()
    await callback.answer()


@get_meter_router.callback_query(AdminCb.filter(F.a == "export_back_to_type"))
async def export_back_to_type(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору типа"""
    logger.info(f"Admin {callback.from_user.id} returned to type selection")
    await state.set_state(ExportStates.select_type)

    await replace_or_send_message(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        text="📊 <b>Выгрузка показаний счётчиков</b>\n\nВыберите тип счётчика:",
        reply_markup=kb.export_menu_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@get_meter_router.callback_query(AdminCb.filter(F.a == "export_back_to_period"))
async def export_back_to_period(callback: CallbackQuery, callback_data: AdminCb, state: FSMContext):
    """Возврат к выбору периода"""
    meter_type = callback_data.type
    logger.info(f"Admin {callback.from_user.id} returned to period selection for {meter_type}")

    await state.set_state(ExportStates.select_period)

    await replace_or_send_message(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        text=f"📊 <b>Выгрузка показаний: {TYPE_NAMES[meter_type]}</b>\n\nВыберите период:",
        reply_markup=kb.period_menu_keyboard(meter_type),
        parse_mode="HTML"
    )
    await callback.answer()


# Функции генерации файлов

async def generate_csv(data: list, filename: str) -> str:
    """Генерация CSV файла"""
    # Создаём временный файл в системной временной директории
    temp_dir = tempfile.gettempdir()
    filepath = os.path.join(temp_dir, f"{filename}.csv")

    logger.info(f"Creating CSV file: {filepath}")

    with open(filepath, 'w', newline='', encoding='utf-8-sig') as csvfile:
        writer = csv.writer(csvfile, delimiter=';')

        # Заголовки
        writer.writerow(['ID', 'Пользователь', 'Адрес', 'Телефон', 'Показания (м³)', 'Дата', 'Создано'])

        # Данные
        for row in data:
            address = f"{row.get('street', '')}, д. {row.get('house', '')}"
            if row.get('apartment'):
                address += f", кв. {row['apartment']}"

            writer.writerow([
                row.get('id', ''),
                row.get('name', ''),
                address,
                row.get('phone', ''),
                row.get('value', ''),
                row.get('reading_date', ''),
                row.get('created_at', '')
            ])

    return filepath


async def generate_xlsx(data: list, filename: str) -> str:
    """Генерация Excel файла"""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment
    except ImportError:
        logger.error("openpyxl not installed, falling back to CSV")
        return await generate_csv(data, filename)

    temp_dir = tempfile.gettempdir()
    filepath = os.path.join(temp_dir, f"{filename}.xlsx")

    logger.info(f"Creating XLSX file: {filepath}")

    wb = Workbook()
    ws = wb.active
    ws.title = "Показания"

    # Заголовки
    headers = ['ID', 'Пользователь', 'Адрес', 'Телефон', 'Показания (м³)', 'Дата', 'Создано']
    ws.append(headers)

    # Стиль заголовков
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal='center')

    # Данные
    for row in data:
        address = f"{row.get('street', '')}, д. {row.get('house', '')}"
        if row.get('apartment'):
            address += f", кв. {row['apartment']}"

        ws.append([
            row.get('id', ''),
            row.get('name', ''),
            address,
            row.get('phone', ''),
            row.get('value', ''),
            str(row.get('reading_date', '')),
            str(row.get('created_at', ''))
        ])

    # Автоширина столбцов
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(cell.value)
            except:  # noqa: E722
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width

    wb.save(filepath)
    return filepath


async def generate_json(data: list, filename: str) -> str:
    """Генерация JSON файла"""
    temp_dir = tempfile.gettempdir()
    filepath = os.path.join(temp_dir, f"{filename}.json")

    logger.info(f"Creating JSON file: {filepath}")

    # Преобразуем даты в строки для JSON
    json_data = []
    for row in data:
        json_row = dict(row)
        for key, value in json_row.items():
            if isinstance(value, (datetime, date)):
                json_row[key] = value.isoformat()
        json_data.append(json_row)

    with open(filepath, 'w', encoding='utf-8') as jsonfile:
        json.dump(json_data, jsonfile, ensure_ascii=False, indent=2)

    return filepath