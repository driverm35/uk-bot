from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from app.logger import logger  # noqa: F401
import app.user.keyboards.user_kb as kb
from app.user.keyboards.user_kb import cb
from app.message_utils import replace_or_send_message
from app.user.utils.profile import build_profile_text
from app.helpers import clear_chat_history, save_msg
from database.requests import (
    get_or_create_user,
    get_ticket_thread_info,
)

start_router = Router(name="start_router")

# ===== FSM для ответа диспетчеру =====
class ReplyToDispatcher(StatesGroup):
    waiting_message = State()  # ждём следующее сообщение пользователя
    # В state.data храним ticket_id, group_chat_id, thread_id

# Команда /start
@start_router.message(CommandStart())
async def command_start_handler(msg: Message) -> None:
    user = await get_or_create_user(
        telegram_id=msg.from_user.id,
        username=msg.from_user.username or "",
        name=msg.from_user.full_name or "",
        status="new"
    )

    if user.status == "new":
        await msg.answer("👋 Добро пожаловать! Пожалуйста, заполните профиль.", reply_markup=kb.new_user())
        return

    text = "👤 Личный кабинет\n\n" + await build_profile_text(msg.from_user.id)
    await msg.answer(text, reply_markup=kb.main_menu(), parse_mode="HTML")

# Личный кабинет
@start_router.callback_query(cb.filter(F.a == "cabinet"))
async def open_cabinet(call: CallbackQuery, state: FSMContext):
    text = "👤 Личный кабинет\n\n" + await build_profile_text(call.from_user.id)
    await replace_or_send_message(
        bot=call.bot,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        reply_markup=kb.main_menu(),
        parse_mode="HTML",
    )
    await call.answer()


# ==== Обработчик нажатия "Ответить диспетчеру" ====
@start_router.callback_query(F.data.startswith("user_reply:"))
async def start_user_reply(call: CallbackQuery, state: FSMContext):
    parts = call.data.split(":")
    if len(parts) != 2 or not parts[1].isdigit():
        await call.answer("Некорректный идентификатор заявки.", show_alert=True)
        return

    ticket_id = int(parts[1])

    # Узнаём топик (куда слать)
    info = await get_ticket_thread_info(ticket_id)
    if not info:
        await call.answer("К этой заявке ещё не привязан чат диспетчера. Попробуйте позже.", show_alert=True)
        return

    group_chat_id, thread_id = info

    await state.set_state(ReplyToDispatcher.waiting_message)
    await state.set_data({"ticket_id": ticket_id, "group_chat_id": group_chat_id, "thread_id": thread_id})

    sent = await replace_or_send_message(
        bot=call.bot,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=(
            f"✍️ Напишите сообщение (фото/документ/голос) — я передам его диспетчеру по заявке №{ticket_id}.\n"
            f"Чтобы отменить — нажмите кнопку 🔙 Назад"
        ),
        reply_markup=kb.ticket_back_to_menu()
    )
    await save_msg(sent, state)
    await call.answer()


# Команда отмены во время ожидания
@start_router.message(F.text == "/cancel")
async def cancel_reply(message: Message, state: FSMContext):
    if await state.get_state() == ReplyToDispatcher.waiting_message:
        await state.clear()
        # Полная очистка цепочки вопросов/ответов
        await clear_chat_history(message.bot, message.chat.id, state)
        await message.answer("❌ Отменено. Сообщение диспетчеру не отправлено.", reply_markup=kb.main_menu())
    else:
        await message.answer("Нет активного ввода.")


# ==== Любое следующее сообщение пользователя: отправка в топик ====
@start_router.message(ReplyToDispatcher.waiting_message)
async def relay_user_message_to_topic(message: Message, state: FSMContext):
    data = await state.get_data()
    ticket_id = data.get("ticket_id")
    group_chat_id = data.get("group_chat_id")
    thread_id = data.get("thread_id")

    if not all([ticket_id, group_chat_id, thread_id]):


        await clear_chat_history(message.bot, message.chat.id, state)
        await message.answer("⚠️ Не удалось отправить.", reply_markup=kb.main_menu())
        await state.clear()
        return

    # Заголовок в топике (контекст)
    try:
        await message.bot.send_message(
            chat_id=group_chat_id,
            text="👤 Сообщение от пользователя:",
            message_thread_id=thread_id,
            parse_mode="HTML",
        )
    except Exception:
        # не фейлимся, попытаемся просто скопировать само сообщение
        pass

    # Копируем исходное сообщение в топик
    try:
        await message.bot.copy_message(
            chat_id=group_chat_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
            message_thread_id=thread_id
        )
        await clear_chat_history(message.bot, message.chat.id, state)
        await message.answer("✅ Отправлено диспетчеру.", reply_markup=kb.back_to_main())

    except Exception as e:
        await message.answer("❌ Не удалось отправить сообщение диспетчеру. Повторите позже.")
        logger.info(f"Ошибка при отправке сообщения диспетчеру: {e}")
        return

    # Сбрасывать состояние после отправки одного сообщения
    await state.clear()
