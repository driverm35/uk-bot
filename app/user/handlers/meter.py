from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from datetime import date
from typing import Dict, Any

from app.message_utils import replace_or_send_message
import app.user.keyboards.user_kb as kb
from app.user.keyboards.user_kb import cb
from app.user.utils.states import MeterStates
from config.settings import METER_CHAT_ID, METER_HOT_WATER_TOPIC_ID
from database.requests import (
    get_meter_history_by_month,
    save_meter_reading,
    get_user_by_tg,
    get_user_meters_count_for_month,
)
from app.logger import logger
from app.helpers import clear_chat_history, save_msg

meter_router = Router(name="meter_router")

MONTHS = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
          "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]

MAX_METERS = 3  # Максимум 3 счётчика ГВС


@meter_router.callback_query(cb.filter(F.a == "meter_menu"))
async def meter_menu(call: CallbackQuery, state: FSMContext):
    """Главное меню показаний - сразу показываем меню ГВС"""
    await state.clear()
    
    month_num = date.today().month
    month_name = MONTHS[month_num]
    year = date.today().year

    # Проверяем, сколько показаний уже подано за текущий месяц
    submitted_count = await get_user_meters_count_for_month(
        call.from_user.id, 
        month_num, 
        year
    )

    text = (
        f"🔥 <b>Показания горячей воды</b>\n\n"
        f"Период: {month_name} {year}\n\n"
    )

    if submitted_count >= MAX_METERS:
        text += (
            f"✅ Все показания переданы ({submitted_count}/{MAX_METERS})\n\n"
            f"Вы можете просмотреть историю показаний."
        )
    else:
        text += (
            f"📊 Передано: {submitted_count}/{MAX_METERS} счётчиков\n\n"
            f"Выберите действие:"
        )

    await replace_or_send_message(
        bot=call.bot,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        reply_markup=kb.meter_main_menu(month_num, month_name, year, submitted_count),
        parse_mode="HTML",
    )
    await call.answer()


@meter_router.callback_query(cb.filter(F.a == "meter_select_number"))
async def select_meter_number(call: CallbackQuery, callback_data: cb, state: FSMContext):
    """Выбор номера счётчика"""
    month_num = callback_data.month
    year = callback_data.year
    month_name = MONTHS[month_num]

    # Получаем уже переданные счётчики
    submitted_count = await get_user_meters_count_for_month(
        call.from_user.id,
        month_num,
        year
    )

    if submitted_count >= MAX_METERS:
        await call.answer("Все показания уже переданы", show_alert=True)
        return

    text = (
        f"🔥 <b>Передача показаний ГВС</b>\n"
        f"Период: {month_name} {year}\n\n"
        f"Выберите номер счётчика:"
    )

    await replace_or_send_message(
        bot=call.bot,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        reply_markup=kb.meter_number_menu(month_num, year),
        parse_mode="HTML",
    )
    await call.answer()


@meter_router.callback_query(cb.filter(F.a == "meter_new"))
async def start_meter_input(call: CallbackQuery, callback_data: cb, state: FSMContext):
    """Начало ввода показаний для выбранного счётчика"""
    meter_number = callback_data.id  # Номер счётчика (1, 2, 3)
    month_num = callback_data.month
    year = callback_data.year
    month_name = MONTHS[month_num]

    # Проверяем, не были ли уже переданы показания для этого счётчика
    history = await get_meter_history_by_month(
        call.from_user.id,
        "hot",
        month_num,
        year
    )
    
    # Проверяем, есть ли уже показания для этого номера счётчика
    for item in history:
        if item.get('meter_number') == meter_number:
            await call.answer(
                f"Показания для счётчика №{meter_number} уже переданы",
                show_alert=True
            )
            return

    await state.update_data(
        meter_number=meter_number,
        month=month_num,
        year=year,
        month_name=month_name
    )
    await state.set_state(MeterStates.waiting_reading)

    text = (
        f"🔥 <b>Передача показаний ГВС</b>\n"
        f"Счётчик: <b>№{meter_number}</b>\n"
        f"Период: {month_name} {year}\n\n"
        f"Введите показания счётчика (например: 123.45 или 123):"
    )

    sent = await replace_or_send_message(
        bot=call.bot,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        reply_markup=kb.cancel_input(),
        parse_mode="HTML",
    )
    await save_msg(sent, state)
    await call.answer()


@meter_router.message(MeterStates.waiting_reading)
async def process_reading_input(message: Message, state: FSMContext):
    """Обработка введённых показаний"""
    reading = message.text.strip()

    try:
        reading_value = float(reading.replace(',', '.'))
        if reading_value < 0 or reading_value > 9999999:
            try:
                await message.delete()
            except Exception:
                pass

            warn = await message.answer(
                "❌ Неверный формат!\n\n"
                "Показания должны быть числом от 0 до 9999999.\n"
                "Примеры: 123456, 123456.45\n\n"
                "Попробуйте ещё раз:",
                reply_markup=kb.cancel_input()
            )
            await save_msg(warn, state)
            return

        reading_formatted = f"{reading_value:.2f}".rstrip('0').rstrip('.')

    except ValueError:
        try:
            await message.delete()
        except Exception:
            pass

        warn = await message.answer(
            "❌ Неверный формат!\n\n"
            "Показания должны быть числом.\n"
            "Примеры: 123456, 123456.45\n\n"
            "Попробуйте ещё раз:",
            reply_markup=kb.cancel_input()
        )
        await save_msg(warn, state)
        return

    await save_msg(message, state)

    data = await state.get_data()
    meter_number = data['meter_number']
    month_name = data['month_name']
    year = data['year']

    user_info = await get_user_by_tg(message.from_user.id)

    if not user_info:
        await message.answer(
            "❌ Ошибка: данные пользователя не найдены.\n"
            "Пожалуйста, сначала заполните профиль."
        )
        await state.clear()
        return

    await state.update_data(
        reading=reading_formatted,
        user_info=user_info
    )
    await state.set_state(MeterStates.preview)

    address = f"{user_info['street']}, д. {user_info['house']}"
    if user_info['apartment']:
        address += f", кв. {user_info['apartment']}"

    text = (
        f"<b>Предпросмотр показаний</b>\n\n"
        f"<b>Пользователь:</b> {user_info['name']}\n"
        f"<b>Адрес:</b> {address}\n"
        f"<b>Период:</b> {month_name} {year}\n"
        f"<b>Счётчик ГВС:</b> №{meter_number}\n"
        f"<b>Показания:</b> {reading_formatted} м³\n\n"
        f"Всё верно?"
    )

    preview = await message.answer(
        text,
        reply_markup=kb.confirm_reading(),
        parse_mode="HTML"
    )
    await save_msg(preview, state)


@meter_router.callback_query(cb.filter(F.a == "edit_reading"), MeterStates.preview)
async def edit_reading(call: CallbackQuery, state: FSMContext):
    """Редактирование показаний"""
    await state.set_state(MeterStates.waiting_reading)

    data = await state.get_data()
    meter_number = data['meter_number']
    month_name = data['month_name']
    year = data['year']

    text = (
        f"🔥 <b>Передача показаний ГВС</b>\n"
        f"Счётчик: <b>№{meter_number}</b>\n"
        f"📅 Период: {month_name} {year}\n\n"
        f"Введите показания счётчика (например: 123.45 или 123):"
    )

    await call.message.edit_text(
        text,
        reply_markup=kb.cancel_input(),
        parse_mode="HTML"
    )
    await call.answer()


@meter_router.callback_query(cb.filter(F.a == "confirm_reading"), MeterStates.preview)
async def confirm_reading(call: CallbackQuery, state: FSMContext):
    """Подтверждение и сохранение показаний"""
    data = await state.get_data()

    meter_number = data['meter_number']
    month = data['month']
    year = data['year']
    reading = data['reading']
    user_info = data['user_info']

    from calendar import monthrange
    last_day = monthrange(year, month)[1]
    today = date.today()

    if today.year == year and today.month == month:
        reading_date = today
    else:
        reading_date = date(year, month, last_day)

    success = await save_meter_reading(
        call.from_user.id,
        "hot",
        reading,
        reading_date,
        meter_number=meter_number
    )

    if not success:
        await clear_chat_history(call.bot, call.message.chat.id, state)

        await call.message.answer(
            "❌ Ошибка при сохранении показаний.\nПопробуйте позже.",
            reply_markup=kb.back_to_main()
        )
        await state.clear()
        await call.answer()
        return

    # Отправляем в топик группы
    await send_to_group_topic(
        call.bot,
        user_info,
        meter_number,
        reading,
        reading_date
    )

    # Проверяем, сколько счётчиков осталось подать
    submitted_count = await get_user_meters_count_for_month(
        call.from_user.id,
        month,
        year
    )

    remaining = MAX_METERS - submitted_count
    
    text = (
        f"✅ <b>Показания успешно приняты!</b>\n\n"
        f"🔥 Счётчик ГВС №{meter_number}\n"
        f"Показания: <b>{reading}</b> м³\n"
        f"Дата: {reading_date.strftime('%d.%m.%Y')}\n\n"
    )
    
    if remaining > 0:
        text += f"💡 Можете передать ещё {remaining} счётчик(а/ов)\n\nСпасибо!"
    else:
        text += "🎉 Все показания переданы!\n\nСпасибо!"

    await clear_chat_history(call.bot, call.message.chat.id, state)

    await call.message.answer(
        text,
        reply_markup=kb.back_to_main(),
        parse_mode="HTML"
    )

    await state.clear()
    await call.answer("✅ Данные сохранены!")


@meter_router.callback_query(cb.filter(F.a == "cancel_input"))
async def cancel_input(call: CallbackQuery, state: FSMContext):
    """Отмена ввода"""
    await clear_chat_history(call.bot, call.message.chat.id, state)
    await state.clear()

    await call.message.answer(
        "❌ Ввод показаний отменён.",
        reply_markup=kb.back_to_main(),
        parse_mode="HTML"
    )
    await call.answer()


async def send_to_group_topic(
    bot,
    user_info: Dict[str, Any],
    meter_number: int,
    reading: str,
    reading_date: date
):
    """Отправка показаний в топик группы"""

    address = f"{user_info['street']}, д. {user_info['house']}"
    if user_info['apartment']:
        address += f", кв. {user_info['apartment']}"

    notification_text = (
        f"📊 <b>Новые показания ГВС</b>\n\n"
        f"👤 <b>Пользователь:</b> {user_info['name']}\n"
        f"🏠 <b>Адрес:</b> {address}\n"
        f"🔥 <b>Счётчик:</b> №{meter_number}\n"
        f"📅 <b>Дата:</b> {reading_date.strftime('%d.%m.%Y')}\n"
        f"📊 <b>Показания:</b> {reading} м³"
    )

    logger.info(f"Sending to topic: topic_id={METER_HOT_WATER_TOPIC_ID}, chat_id={METER_CHAT_ID}")

    if not METER_HOT_WATER_TOPIC_ID:
        logger.error("METER_HOT_WATER_TOPIC_ID not configured")
        return

    try:
        sent_message = await bot.send_message(
            chat_id=METER_CHAT_ID,
            message_thread_id=METER_HOT_WATER_TOPIC_ID,
            text=notification_text,
            parse_mode="HTML"
        )
        logger.info(f"Показания отправлены в топик (message_id={sent_message.message_id})")
    except Exception as e:
        logger.error(f"Ошибка отправки в топик: {e}", exc_info=True)


@meter_router.callback_query(cb.filter(F.a == "meter_history"))
async def meter_history_menu(call: CallbackQuery, state: FSMContext):
    """Меню истории показаний"""
    await state.clear()

    text = "📜 История показаний ГВС\n\nВыберите месяц:"

    await replace_or_send_message(
        bot=call.bot,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        reply_markup=kb.meter_history(),
        parse_mode="HTML",
    )
    await call.answer()


@meter_router.callback_query(cb.filter(F.a == "history_month"))
async def show_month_history(call: CallbackQuery, callback_data: cb):
    """Показать историю за месяц"""
    month_num = callback_data.month
    year = callback_data.year
    month_name = MONTHS[month_num]

    text = f"📊 Показания ГВС за {month_name} {year}\n\n"

    history = await get_meter_history_by_month(
        call.from_user.id,
        "hot",
        month_num,
        year
    )
    
    if history:
        # Группируем по номеру счётчика
        meters = {}
        for item in history:
            meter_num = item.get('meter_number', 1)
            if meter_num not in meters:
                meters[meter_num] = []
            meters[meter_num].append(item)
        
        # Выводим по счётчикам
        for meter_num in sorted(meters.keys()):
            text += f"🔥 <b>Счётчик №{meter_num}:</b>\n"
            for item in meters[meter_num]:
                text += f"  • {item['date']}: <b>{item['value']}</b> м³\n"
                if item.get('created_at'):
                    text += f"    <i>Внесено: {item['created_at']}</i>\n"
            text += "\n"
    else:
        text += "📭 Нет данных за этот период."

    await replace_or_send_message(
        bot=call.bot,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        reply_markup=kb.back_to_meter_menu(),
        parse_mode="HTML",
    )
    await call.answer()


@meter_router.callback_query(cb.filter(F.a == "back_to_meter"))
async def back_to_meter_menu(call: CallbackQuery, state: FSMContext):
    """Возврат в главное меню показаний"""
    await meter_menu(call, state)