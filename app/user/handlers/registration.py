from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

import app.user.keyboards.user_kb as kb
from app.message_utils import replace_or_send_message

from app.user.keyboards.user_kb import cb
from app.user.utils.states import RegStates
from app.user.utils.profile import build_profile_text
from app.helpers import clear_chat_history, save_msg, ask_and_track
from app.user.utils.validators import (
    is_valid_phone,
    is_valid_street,
    is_valid_house,
    is_valid_apartment
)
from database.requests import update_user_profile

reg_router = Router(name="reg_router")

@reg_router.callback_query(cb.filter(F.a == "fill_profile"))
async def start_registration(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(RegStates.name)
    sent = await replace_or_send_message(
        bot=call.bot,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="✍️ Введите ваше <b>имя/фамилию</b>:",
        parse_mode="HTML",
    )
    await save_msg(sent, state)
    await call.answer()


@reg_router.message(RegStates.name, F.text.len() >= 1)
async def reg_name(msg: Message, state: FSMContext):
    await state.update_data(name=msg.text.strip())
    await save_msg(msg, state)

    # Переходим к запросу телефона
    sent = await msg.answer(
        "📱 Отправьте ваш <b>номер телефона</b>:\n"
        "• Нажмите кнопку ниже для автоматической отправки\n"
        "• Или введите вручную в формате: <code>+79991234567</code>",
        reply_markup=kb.phone_keyboard(),
        parse_mode="HTML"
    )
    await save_msg(sent, state)
    await state.set_state(RegStates.phone)


# Обработка телефона через кнопку (contact)
@reg_router.message(RegStates.phone, F.contact)
async def reg_phone_contact(msg: Message, state: FSMContext):
    phone = msg.contact.phone_number
    # Нормализуем формат
    if not phone.startswith('+'):
        phone = '+' + phone

    await state.update_data(phone=phone)
    await save_msg(msg, state)

    # Убираем клавиатуру с кнопкой
    sent = await msg.answer(
        "🏙️ Введите <b>улицу</b>:\nНапример: <b>ул. Ленина</b>",
        parse_mode="HTML",
        reply_markup=kb.remove_keyboard()
    )
    await save_msg(sent, state)
    await state.set_state(RegStates.street)


# Обработка телефона текстом
@reg_router.message(RegStates.phone, F.text.func(is_valid_phone))
async def reg_phone_text_valid(msg: Message, state: FSMContext):
    phone = msg.text.strip()

    # Нормализуем формат: оставляем только цифры и добавляем +
    import re
    digits = re.sub(r'\D', '', phone)
    phone = '+' + digits

    await state.update_data(phone=phone)
    await save_msg(msg, state)

    sent = await msg.answer(
        "🏙️ Введите <b>улицу</b>:\nНапример: <b>ул. Ленина</b>",
        parse_mode="HTML",
        reply_markup=kb.remove_keyboard()
    )
    await save_msg(sent, state)
    await state.set_state(RegStates.street)


# Невалидный телефон
@reg_router.message(RegStates.phone)
async def reg_phone_invalid(msg: Message, state: FSMContext):
    try:
        await msg.delete()  # Удаляем невалидный ввод
    except Exception:
        pass

    warn = await msg.answer(
        "❗ Неверный формат телефона.\n"
        "Введите 11 цифр, например: <code>+79991234567</code> или <code>89991234567</code>\n"
        "Или нажмите кнопку ниже для автоматической отправки.",
        parse_mode="HTML",
        reply_markup=kb.phone_keyboard()
    )
    await save_msg(warn, state)


@reg_router.message(RegStates.street, ~F.from_user.is_bot, F.text.func(is_valid_street))
async def reg_street_valid(msg: Message, state: FSMContext):
    await state.update_data(street=msg.text.strip())
    await save_msg(msg, state)
    await ask_and_track(msg, state, "🏠 Укажите <b>дом</b>:\nНапример: <i>12</i>", RegStates.house)


# Невалидная улица
@reg_router.message(RegStates.street)
async def reg_street_invalid(msg: Message, state: FSMContext):
    try:
        await msg.delete()  # Удаляем невалидный ввод
    except Exception:
        pass
    warn = await msg.answer(
        "❗ Пожалуйста, введите корректное название улицы.\n"
        "Например: <code>ул. Ленина</code>",
        parse_mode="HTML",
    )
    await save_msg(warn, state)


@reg_router.message(RegStates.house, ~F.from_user.is_bot, F.text.func(is_valid_house))
async def reg_house_valid(msg: Message, state: FSMContext):
    await state.update_data(house=msg.text.strip())
    await save_msg(msg, state)
    await ask_and_track(msg, state, "🚪 Укажите <b>квартиру</b> (если нет — «-»):", RegStates.apartment)


@reg_router.message(RegStates.house)
async def reg_house_invalid(msg: Message, state: FSMContext):
    try:
        await msg.delete()  # Удаляем невалидный ввод
    except Exception:
        pass
    warn = await msg.answer(
        "❗ Пожалуйста, укажите <b>дом</b> без слов «д.», «дом», «кв.».\n"
        "Примеры: <code>12</code>, <code>12б</code>, <code>12-1</code>, <code>12/3</code>",
        parse_mode="HTML",
    )
    await save_msg(warn, state)


@reg_router.message(RegStates.apartment, ~F.from_user.is_bot, F.text.func(is_valid_apartment))
async def reg_apartment_valid(msg: Message, state: FSMContext):
    data = await state.get_data()
    name = data.get("name", "").strip()
    phone = data.get("phone", "").strip()
    street = data.get("street", "").strip()
    house = data.get("house", "").strip()
    apartment_raw = msg.text.strip()
    await save_msg(msg, state)

    await update_user_profile(
        telegram_id=msg.from_user.id,
        name=name,
        phone=phone,
        street=street,
        house=house,
        apartment=None if apartment_raw in {"-", "—"} else apartment_raw,
        status="active",
    )

    sent_ok = await msg.answer("✅ Данные сохранены.")
    await save_msg(sent_ok, state)

    # Полная очистка цепочки вопросов/ответов
    await clear_chat_history(msg.bot, msg.chat.id, state)

    # Итоговый профиль + меню
    text = "👤 Личный кабинет\n\n"
    text += await build_profile_text(msg.from_user.id)
    await msg.answer(text, reply_markup=kb.main_menu(), parse_mode="HTML")


@reg_router.message(RegStates.apartment)
async def reg_apartment_invalid(msg: Message, state: FSMContext):
    try:
        await msg.delete()  # Удаляем невалидный ввод
    except Exception:
        pass
    warn = await msg.answer(
        "❗ Для <b>квартиры</b> введите только число (например, <code>33</code>) "
        "или <code>-</code>, если квартиры нет.",
        parse_mode="HTML",
    )
    await save_msg(warn, state)