from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from app.admin.filters import AdminFilter
import app.admin.keyboards.admin_kb as kb
from app.admin.keyboards.admin_kb import AdminCb
from app.message_utils import replace_or_send_message
from app.admin.acl import is_admin

start_router = Router(name="start_router")
start_router.message.filter(AdminFilter())
start_router.callback_query.filter(AdminFilter())

@start_router.message(CommandStart())
async def command_start_handler(msg: Message) -> None:
    await msg.answer("Панель управления", reply_markup=kb.admin_main_menu())


@start_router.callback_query(AdminCb.filter(F.a == "admin_main_menu"))
async def admin_main_menu(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Доступ только для администраторов", show_alert=True)
        return

    text = "Панель управления"
    await replace_or_send_message(
        bot=call.bot,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        reply_markup=kb.admin_main_menu(),
        parse_mode="HTML",
    )
    await call.answer()

