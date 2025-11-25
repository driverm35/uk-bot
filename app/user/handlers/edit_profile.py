import re
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

import app.user.keyboards.user_kb as kb
from app.user.keyboards.user_kb import cb
from app.user.utils.states import EditProfile
from app.user.utils.profile import build_profile_text
from app.message_utils import replace_or_send_message
from database.requests import update_user_profile
from app.helpers import clear_chat_history, save_msg

edit_router = Router(name="edit_router")

@edit_router.callback_query(cb.filter(F.a == "edit_profile"))
async def quick_edit_profile(call: CallbackQuery, state: FSMContext):
    text = "✏️ Редактирование профиля\n\n"
    text += await build_profile_text(call.from_user.id)

    await replace_or_send_message(
        bot=call.bot,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        reply_markup=kb.edit_profile(),
        parse_mode="HTML",
    )
    await call.answer()

@edit_router.callback_query(cb.filter(F.a == "edit_name"))
async def quick_edit_name(call: CallbackQuery, state: FSMContext):
    await clear_chat_history(call.bot, call.message.chat.id, state)
    await state.set_state(EditProfile.new_data)
    await state.update_data(param="name")
    await save_msg(call.message, state)

    sent = await replace_or_send_message(
        bot=call.bot,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="✍️ Введите новое <b>имя</b>:",
        parse_mode="HTML",
    )
    await save_msg(sent, state)
    await call.answer()

@edit_router.callback_query(cb.filter(F.a == "edit_phone"))
async def quick_edit_phone(call: CallbackQuery, state: FSMContext):
    await clear_chat_history(call.bot, call.message.chat.id, state)
    await state.set_state(EditProfile.new_data)
    await state.update_data(param="phone")
    await save_msg(call.message, state)

    sent = await replace_or_send_message(
        bot=call.bot,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="📞 Введите новый <b>номер телефона</b>:",
        parse_mode="HTML",
    )
    await save_msg(sent, state)
    await call.answer()

@edit_router.callback_query(cb.filter(F.a == "edit_street"))
async def quick_edit_street(call: CallbackQuery, state: FSMContext):
    await clear_chat_history(call.bot, call.message.chat.id, state)
    await state.set_state(EditProfile.new_data)
    await state.update_data(param="street")
    await save_msg(call.message, state)

    sent = await replace_or_send_message(
        bot=call.bot,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="🏙️ Введите новую <b>улицу без ул.</b>:\nНапример: <b>Ленина</b>",
        parse_mode="HTML",
    )
    await save_msg(sent, state)
    await call.answer()


@edit_router.callback_query(cb.filter(F.a == "edit_house"))
async def quick_edit_house(call: CallbackQuery, state: FSMContext):
    await clear_chat_history(call.bot, call.message.chat.id, state)
    await state.set_state(EditProfile.new_data)
    await state.update_data(param="house")
    await save_msg(call.message, state)

    sent = await replace_or_send_message(
        bot=call.bot,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="🏠 Введите новый <b>дом</b>:\nНапример: <i>12</i>",
        parse_mode="HTML",
    )
    await save_msg(sent, state)
    await call.answer()


@edit_router.callback_query(cb.filter(F.a == "edit_apartment"))
async def quick_edit_apartment(call: CallbackQuery, state: FSMContext):
    await clear_chat_history(call.bot, call.message.chat.id, state)
    await state.set_state(EditProfile.new_data)
    await state.update_data(param="apartment")
    await save_msg(call.message, state)

    sent = await replace_or_send_message(
        bot=call.bot,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="🚪 Введите новую <b>квартиру</b> (или «-»):",
        parse_mode="HTML",
    )
    await save_msg(sent, state)
    await call.answer()


@edit_router.message(EditProfile.new_data, F.text.len() >= 1)
async def edit_profile(msg: Message, state: FSMContext):
    await save_msg(msg, state)
    data = await state.get_data()
    param = data.get("param", "").strip()
    new_data = msg.text.strip()

    if param == "phone":
        # Нормализуем формат: оставляем только цифры и добавляем +
        digits = re.sub(r'\D', '', new_data)
        new_data = '+' + digits

    await update_user_profile(
        telegram_id=msg.from_user.id,
        **{param: new_data}
    )
    sent = await msg.answer("✅ Данные сохранены")
    await save_msg(sent, state)
    # Удаляем все сообщения опроса
    await clear_chat_history(msg.bot, msg.chat.id, state)

    # Показываем результат
    text = "👤 Личный кабинет\n\n"
    text += await build_profile_text(msg.from_user.id)

    await msg.answer(text, reply_markup=kb.main_menu(), parse_mode="HTML")