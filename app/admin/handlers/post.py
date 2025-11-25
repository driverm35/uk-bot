from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.admin.filters import AdminFilter
import app.admin.keyboards.admin_kb as kb
from app.admin.keyboards.admin_kb import AdminCb
from config.settings import GROUP_ID
from app.logger import logger

from app.helpers import clear_chat_history, save_msg, ask_and_track

post_router = Router(name="post_router")
post_router.message.filter(AdminFilter())
post_router.callback_query.filter(AdminFilter())

class PostCreation(StatesGroup):
    waiting_for_post = State()
    q_button = State()
    get_text_for_button = State()
    get_url_for_button = State()
    confirm = State()


@post_router.callback_query(AdminCb.filter(F.a == "admin_create_post"))
async def create_post(callback: CallbackQuery, state: FSMContext):
    """Начало создания поста"""
    await clear_chat_history(callback.bot, callback.message.chat.id, state)
    await ask_and_track(
        callback,
        state,
        "📝 Отправь пост для публикации:",
        next_state=PostCreation.waiting_for_post
    )
    await callback.answer()


@post_router.message(StateFilter(PostCreation.waiting_for_post))
async def receive_post(message: Message, state: FSMContext):
    """Получение поста от админа"""
    # Сохраняем данные о сообщении
    await state.update_data(
        message_id=message.message_id,
        chat_id=message.chat.id
    )
    await save_msg(message, state)
    await ask_and_track(
        message,
        state,
        "Ок, запомнил сообщение для поста!\n\nДобавить кнопку?",
        next_state=PostCreation.q_button,
        reply_markup=kb.post_add_button_choice()
    )


@post_router.callback_query(StateFilter(PostCreation.q_button), F.data == "post:add_button")
async def add_button_choice(callback: CallbackQuery, state: FSMContext):
    """Выбор: добавить кнопку"""
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await ask_and_track(
        callback,
        state,
        "Отправь текст для кнопки:",
        next_state=PostCreation.get_text_for_button
    )
    await callback.answer()


@post_router.callback_query(StateFilter(PostCreation.q_button), F.data == "post:no_button")
async def no_button_choice(callback: CallbackQuery, state: FSMContext):
    """Выбор: без кнопки"""
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    st = await state.get_data()

    # Показываем предпросмотр без кнопки
    await confirm_post(
        origin=callback.message,
        message_id=st["message_id"],
        chat_id=st["chat_id"],
        reply_markup=None,
        state=state
    )
    await callback.answer()


@post_router.message(StateFilter(PostCreation.get_text_for_button))
async def get_text_for_button(message: Message, state: FSMContext):
    """Получение текста для кнопки"""
    await state.update_data(text_button=message.text.strip())
    await save_msg(message, state)
    await ask_and_track(
        message,
        state,
        "Отправь ссылку для кнопки:",
        next_state=PostCreation.get_url_for_button
    )


@post_router.message(StateFilter(PostCreation.get_url_for_button))
async def get_url_for_button(message: Message, state: FSMContext):
    """Получение URL для кнопки"""
    data = await state.get_data()
    text_button = data.get("text_button")
    url_button = message.text.strip()
    await save_msg(message, state)

    if not (url_button.startswith("http://") or url_button.startswith("https://")):
        await ask_and_track(message, state, "❗ Ссылка должна начинаться с http:// или https://. Попробуйте ещё раз:")
        return

    # Сохраняем данные кнопки (НЕ объект клавиатуры)
    await state.update_data(
        button_text=text_button,
        button_url=url_button
    )

    # Создаём клавиатуру для предпросмотра
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text_button, url=url_button)]
    ])

    message_id = data.get("message_id")
    chat_id = data.get("chat_id")

    await confirm_post(
        origin=message,
        message_id=message_id,
        chat_id=chat_id,
        reply_markup=keyboard,
        state=state
    )


async def confirm_post(
    origin: Message | CallbackQuery,
    message_id: int,
    chat_id: int,
    reply_markup: InlineKeyboardMarkup | None,
    state: FSMContext
):
    """Показ предпросмотра и запрос подтверждения"""
    target_chat_id = origin.message.chat.id if isinstance(origin, CallbackQuery) else origin.chat.id
    bot = origin.bot

    # Показываем предпросмотр
    try:
        preview = await bot.copy_message(
            chat_id=target_chat_id,
            from_chat_id=chat_id,
            message_id=message_id,
            reply_markup=reply_markup
        )
        await save_msg(preview, state)
    except Exception as e:
        logger.error(f"Error copying preview: {e}")

    # Отправляем сообщение с подтверждением
    confirmation_msg = await bot.send_message(
        chat_id=target_chat_id,
        text="Подтвердите публикацию:",
        reply_markup=kb.post_confirm_keyboard()
    )
    await save_msg(confirmation_msg, state)

    # Переходим в состояние подтверждения
    await state.set_state(PostCreation.confirm)


@post_router.callback_query(
    StateFilter(PostCreation.confirm),
    AdminCb.filter(F.a == "post_confirm")
)
async def handle_confirm(callback: CallbackQuery, state: FSMContext, callback_data: AdminCb):
    """Подтверждение публикации"""
    logger.info("Post confirmation triggered")

    data = await state.get_data()
    message_id = data.get("message_id")
    chat_id = data.get("chat_id")
    button_text = data.get("button_text")
    button_url = data.get("button_url")

    if not message_id or not chat_id:
        await clear_chat_history(callback.bot, callback.message.chat.id, state)
        await callback.message.answer(
            "⚠️ Нет данных для публикации. Начните заново: 📢 «Создать пост».",
            reply_markup=kb.admin_main_menu()
        )
        await state.clear()
        await callback.answer()
        return

    # Воссоздаём клавиатуру если она была
    reply_markup = None
    if button_text and button_url:
        reply_markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=button_text, url=button_url)]
        ])

    try:
        await callback.bot.copy_message(
            chat_id=GROUP_ID,
            from_chat_id=chat_id,
            message_id=message_id,
            reply_markup=reply_markup
        )

        # ПОТОМ очищаем историю
        await clear_chat_history(callback.bot, callback.message.chat.id, state)

        # Отправляем новое сообщение с результатом
        await callback.message.answer(
            "✅ Пост успешно опубликован!",
            reply_markup=kb.admin_main_menu()
        )

    except Exception as e:
        logger.error(f"Error publishing post: {e}")

        # Даже при ошибке очищаем историю
        await clear_chat_history(callback.bot, callback.message.chat.id, state)

        await callback.message.answer(
            f"❌ Ошибка при публикации: {e}",
            reply_markup=kb.admin_main_menu()
        )

    await callback.answer()


@post_router.callback_query(
    StateFilter(PostCreation.confirm),
    AdminCb.filter(F.a == "post_cancel")
)
async def handle_cancel(callback: CallbackQuery, state: FSMContext, callback_data: AdminCb):
    """Отмена публикации"""
    logger.info("Post cancellation triggered")

    # Очищаем историю
    await clear_chat_history(callback.bot, callback.message.chat.id, state)

    # Отправляем новое сообщение с результатом
    await callback.message.answer(
        "🚫 Публикация отменена",
        reply_markup=kb.admin_main_menu()
    )

    await callback.answer()