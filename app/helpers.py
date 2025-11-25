from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from app.message_utils import replace_or_send_message


async def clear_chat_history(bot, chat_id: int, state: FSMContext):
    """Удаляет все сообщения, сохранённые в состоянии"""
    data = await state.get_data()
    msg_ids: list[int] = data.get("msg_ids", [])
    for mid in msg_ids:
        try:
            await bot.delete_message(chat_id, mid)
        except Exception:
            pass
    await state.clear()

async def save_msg(msg: Message, state: FSMContext):
    """Сохраняем ID сообщений для последующего удаления"""
    data = await state.get_data()
    msg_ids = data.get("msg_ids", [])
    msg_ids.append(msg.message_id)
    await state.update_data(msg_ids=msg_ids)

async def ask_and_track(msg_or_call, state: FSMContext, text: str, next_state=None, **kwargs):
    if isinstance(msg_or_call, CallbackQuery):
        sent = await replace_or_send_message(
            bot=msg_or_call.bot,
            chat_id=msg_or_call.message.chat.id,
            message_id=msg_or_call.message.message_id,
            text=text,
            parse_mode="HTML",
            **kwargs
        )
    else:
        sent = await msg_or_call.answer(text, parse_mode="HTML", **kwargs)

    await save_msg(sent, state)
    if next_state:
        await state.set_state(next_state)
    return sent