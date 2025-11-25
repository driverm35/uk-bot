from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime
import asyncio
from pathlib import Path

from app.admin.filters import AdminFilter
import app.admin.keyboards.admin_kb as kb
from app.admin.keyboards.admin_kb import AdminCb
from app.message_utils import replace_or_send_message
from app.logger import logger
from app.admin.handlers.get_meter import generate_xlsx, MONTHS, TYPE_NAMES
from database.requests import get_all_meter_readings_by_type_and_period
from app.services.email_service import send_email
from config.settings import ACCOUNTANT_EMAIL

send_meters_router = Router(name="send_meters_router")
send_meters_router.message.filter(AdminFilter())
send_meters_router.callback_query.filter(AdminFilter())


class EmailStates(StatesGroup):
    select_type = State()
    select_month = State()
    confirm = State()


@send_meters_router.callback_query(AdminCb.filter(F.a == "admin_send_meters_to_mail"))
async def send_meters_to_mail_start(callback: CallbackQuery, state: FSMContext):
    """Начало процесса отправки показаний на email"""
    logger.info(f"Admin {callback.from_user.id} started email sending process")
    await state.clear()
    await state.set_state(EmailStates.select_type)

    await replace_or_send_message(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        text="📧 <b>Отправка показаний на email</b>\n\nВыберите тип счётчика:",
        reply_markup=kb.email_type_menu(),
        parse_mode="HTML"
    )
    await callback.answer()


@send_meters_router.callback_query(AdminCb.filter(F.a == "email_select_type"))
async def email_select_type(callback: CallbackQuery, callback_data: AdminCb, state: FSMContext):
    """Выбор типа счётчика"""
    meter_type = callback_data.type
    logger.info(f"Admin {callback.from_user.id} selected meter type for email: {meter_type}")

    await state.update_data(meter_type=meter_type)
    await state.set_state(EmailStates.select_month)

    current_year = datetime.now().year
    await replace_or_send_message(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        text=f"📧 <b>Отправка показаний: {TYPE_NAMES[meter_type]}</b>\n\nВыберите месяц ({current_year}):",
        reply_markup=kb.email_month_menu(meter_type, current_year),
        parse_mode="HTML"
    )
    await callback.answer()


@send_meters_router.callback_query(AdminCb.filter(F.a == "email_select_month"))
async def email_select_month(callback: CallbackQuery, callback_data: AdminCb, state: FSMContext):
    """Выбор месяца и подтверждение отправки"""
    meter_type = callback_data.type
    month = callback_data.month
    year = callback_data.year

    logger.info(f"Admin {callback.from_user.id} selected month for email: {month}/{year}")

    await state.update_data(month=month, year=year)
    await state.set_state(EmailStates.confirm)

    await replace_or_send_message(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        text=(
            f"📧 <b>Подтверждение отправки</b>\n\n"
            f"Тип: <b>{TYPE_NAMES[meter_type]}</b>\n"
            f"Период: <b>{MONTHS[month]} {year}</b>\n\n"
            f"Отправить файл на email бухгалтера?"
        ),
        reply_markup=kb.email_confirm_menu(meter_type, month, year),
        parse_mode="HTML"
    )
    await callback.answer()


@send_meters_router.callback_query(AdminCb.filter(F.a == "email_send_confirm"))
async def email_send_confirm(callback: CallbackQuery, callback_data: AdminCb, state: FSMContext):
    """Подтверждение и отправка email"""
    meter_type = callback_data.type
    month = callback_data.month
    year = callback_data.year

    logger.info(
        f"Admin {callback.from_user.id} confirmed email sending: "
        f"type={meter_type}, month={month}, year={year}"
    )

    # ⚡️ СНАЧАЛА ОТВЕЧАЕМ НА CALLBACK, ЧТОБЫ НЕ ПОЛУЧИТЬ "query is too old"
    await callback.answer()

    # Показываем процесс в сообщении (это отдельный запрос к Telegram)
    await callback.message.edit_text(
        "⏳ Формирую файл и отправляю email, подождите...",
        parse_mode="HTML"
    )

    try:
        # Получаем данные
        data = await get_all_meter_readings_by_type_and_period(
            meter_type=meter_type,
            period="select_month",
            month=month,
            year=year,
        )

        if not data:
            logger.warning(f"No data for email: type={meter_type}, month={month}/{year}")
            await callback.message.edit_text(
                "📭 Нет данных за выбранный период.",
                reply_markup=kb.email_back_to_menu(),
                parse_mode="HTML",
            )
            await state.clear()
            return

        # Генерируем файл
        filename = f"meters_{meter_type}_{year}_{month:02d}"
        file_path = await generate_xlsx(data, filename)

        # Формируем письмо
        subject = f"Показания счётчиков: {TYPE_NAMES[meter_type]} - {MONTHS[month]} {year}"
        body = (
            f"Показания счётчиков\n\n"
            f"Тип: {TYPE_NAMES[meter_type]}\n"
            f"Период: {MONTHS[month]} {year}\n"
            f"Записей: {len(data)}\n\n"
            f"Отправлено автоматически через Telegram-бота."
        )

        # Отправляем email
        success = await send_email(
            to=ACCOUNTANT_EMAIL,  # или ACCOUNTANT_EMAIL из настроек
            subject=subject,
            body=body,
            attachment_path=file_path,
        )

        # Удаляем временный файл
        try:
            Path(file_path).unlink()
        except Exception as e:
            logger.warning(f"Failed to delete temp file: {e}")

        # Сообщаем результат
        if success:
            await callback.message.edit_text(
                (
                    f"✅ <b>Email успешно отправлен!</b>\n\n"
                    f"Тип: {TYPE_NAMES[meter_type]}\n"
                    f"Период: {MONTHS[month]} {year}\n"
                    f"Записей: {len(data)}"
                ),
                reply_markup=kb.email_back_to_menu(),
                parse_mode="HTML",
            )
        else:
            await callback.message.edit_text(
                "❌ Не удалось отправить email. Проверьте настройки SMTP.",
                reply_markup=kb.email_back_to_menu(),
                parse_mode="HTML",
            )

    except Exception as e:
        logger.error(f"Error in email sending process: {e}", exc_info=True)
        await callback.message.edit_text(
            f"❌ Ошибка: {str(e)}",
            reply_markup=kb.email_back_to_menu(),
            parse_mode="HTML",
        )
    finally:
        await state.clear()


@send_meters_router.callback_query(AdminCb.filter(F.a == "email_cancel"))
async def email_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена отправки email"""
    await state.clear()
    await replace_or_send_message(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        text="❌ Отправка email отменена",
        reply_markup=kb.admin_main_menu(),
        parse_mode="HTML"
    )
    await callback.answer()