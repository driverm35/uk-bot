# app/group/ticket_forum.py
from aiogram import Router, F, Bot
from aiogram.enums import ChatType, ContentType
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest

from config.settings import NOTIFICATION_CHANNEL_ID
from database.models import TicketStatus
from database.requests import get_ticket_by_thread, set_ticket_status
from app.admin.acl import is_admin
from app.admin.keyboards.admin_kb import status_panel_kb as _status_panel_kb
from app.user.keyboards.user_kb import reply_to_dispatcher_kb
from app.logger import logger

forum_router = Router(name="forum_router")

# ========== HELPERS ==========

def _status_emoji(s: TicketStatus) -> str:
    return {
        TicketStatus.OPEN: "🟢",
        TicketStatus.WORK: "🟡",
        TicketStatus.CANCELLED: "🟣",
    }.get(s, "⚪")

# Сервисные/системные типы сообщений, которые нельзя отправлять клиенту
_SYSTEM_CONTENT_TYPES: set[ContentType] = {
    ContentType.FORUM_TOPIC_CREATED,
    ContentType.FORUM_TOPIC_EDITED,
    ContentType.FORUM_TOPIC_CLOSED,
    ContentType.FORUM_TOPIC_REOPENED,
    ContentType.GENERAL_FORUM_TOPIC_HIDDEN,
    ContentType.GENERAL_FORUM_TOPIC_UNHIDDEN,
    ContentType.PINNED_MESSAGE,
    ContentType.NEW_CHAT_MEMBERS,
    ContentType.LEFT_CHAT_MEMBER,
    ContentType.VIDEO_CHAT_SCHEDULED,
    ContentType.VIDEO_CHAT_STARTED,
    ContentType.VIDEO_CHAT_ENDED,
    ContentType.VIDEO_CHAT_PARTICIPANTS_INVITED,
    ContentType.MESSAGE_AUTO_DELETE_TIMER_CHANGED,
    ContentType.SUCCESSFUL_PAYMENT,   # на всякий случай
    ContentType.CONTACT,              # обычно служебные в теме не нужны
    ContentType.LOCATION,             # чтобы не сыпать геоданными случайно
    # при желании можно сузить список
}

def _is_system_message(msg: Message) -> bool:
    # 1) системные типы
    if msg.content_type in _SYSTEM_CONTENT_TYPES:
        return True
    # 2) сообщения бота (чтобы не зациклиться и не слать их пользователю)
    if msg.from_user and msg.from_user.is_bot:
        return True
    # 3) технические сообщения/команды без полезного контента
    if msg.text and msg.text.startswith("/"):
        return True
    return False

async def _rename_topic(bot: Bot, chat_id: int, thread_id: int, ticket_id: int, status: TicketStatus):
    try:
        await bot.edit_forum_topic(
            chat_id=chat_id,
            message_thread_id=thread_id,
            name=f"{_status_emoji(status)} Заявка №{ticket_id}",
        )
        logger.info(f"Renamed topic for ticket #{ticket_id} to status {status}")
    except TelegramBadRequest as e:
        logger.error(f"Rename topic failed for ticket #{ticket_id}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error renaming topic for ticket #{ticket_id}: {e}")

async def _close_topic_if_done(bot: Bot, chat_id: int, thread_id: int, status: TicketStatus):
    if status == TicketStatus.CANCELLED:
        try:
            await bot.close_forum_topic(chat_id=chat_id, message_thread_id=thread_id)
            logger.info(f"Closed topic {thread_id}")
        except TelegramBadRequest as e:
            logger.error(f"Close topic failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error closing topic: {e}")

async def _send_to_author(bot: Bot, ticket: dict, src_msg: Message):
    """Отправляет сообщение автору заявки (не пересылаем системные/бота)."""
    author = ticket.get("user_tg_id")
    if not author:
        logger.warning(f"No author found for ticket #{ticket.get('id')}")
        return

    if _is_system_message(src_msg):
        logger.info("Skip system/bot message for user relay")
        return

    try:
        await bot.send_message(
            chat_id=author,
            text=f"📨 Сообщение по вашей заявке №{ticket['id']}:",
            parse_mode="HTML"
        )
        await bot.copy_message(
            chat_id=author,
            from_chat_id=src_msg.chat.id,
            message_id=src_msg.message_id,
            reply_markup=reply_to_dispatcher_kb(ticket['id'])  # кнопка «Ответить диспетчеру»
        )
        logger.info(f"Forwarded message to author {author} for ticket #{ticket['id']}")
    except Exception as e:
        logger.error(f"Failed to forward message to author {author} for ticket #{ticket['id']}: {e}")


# ========== ПАНЕЛЬ СТАТУСОВ ПОД СООБЩЕНИЕМ ==========

@forum_router.message(Command("panel"))
async def send_status_panel(msg: Message):
    """Панель управления статусом — только для админов и только в нужном чате/теме."""
    if NOTIFICATION_CHANNEL_ID and msg.chat.id != NOTIFICATION_CHANNEL_ID:
        return
    if not is_admin(msg.from_user.id):
        return
    thread_id = getattr(msg, "message_thread_id", None)
    if not thread_id:
        await msg.reply("Эта команда работает только внутри топика.")
        return
    ticket = await get_ticket_by_thread(msg.chat.id, thread_id)
    if not ticket:
        await msg.reply("Заявка для этого топика не найдена.")
        return
    await msg.reply(
        f"🔧 Панель управления заявкой №{ticket['id']}",
        reply_markup=_status_panel_kb(ticket['id'])
    )

@forum_router.callback_query(F.data.startswith("tset:"))
async def on_status_panel_click(call: CallbackQuery):
    """
    Обрабатывает нажатия на кнопки панели статусов (tset:{id}:{open|work|done})
    Только админы.
    """
    if NOTIFICATION_CHANNEL_ID and call.message.chat.id != NOTIFICATION_CHANNEL_ID:
        await call.answer("Неверный чат.")
        return
    if not is_admin(call.from_user.id):
        await call.answer("Только для администраторов.", show_alert=True)
        return

    try:
        _, sid, smode = call.data.split(":")
        ticket_id = int(sid)
    except Exception:
        await call.answer("Некорректные данные.", show_alert=True)
        return

    status_map = {
        "open": TicketStatus.OPEN,
        "work": TicketStatus.WORK,
        "done": TicketStatus.CANCELLED,
    }
    new_status = status_map.get(smode)
    if not new_status:
        await call.answer("Неизвестный статус.", show_alert=True)
        return

    thread_id = getattr(call.message, "message_thread_id", None)
    ticket = await get_ticket_by_thread(call.message.chat.id, thread_id) if thread_id else None
    if not ticket or ticket["id"] != ticket_id:
        await call.answer("Заявка не найдена в этом топике.", show_alert=True)
        return

    res = await set_ticket_status(ticket_id, new_status)
    if not res:
        await call.answer("Не удалось изменить статус.", show_alert=True)
        return

    _, final_status, author_tg = res

    # Переименовать/закрыть
    await _rename_topic(call.message.bot, call.message.chat.id, thread_id, ticket_id, final_status)
    await _close_topic_if_done(call.message.bot, call.message.chat.id, thread_id, final_status)

    # Уведомить автора
    try:
        status_messages = {
            TicketStatus.OPEN: "возвращена в работу",
            TicketStatus.WORK: "взята в работу",
            TicketStatus.CANCELLED: "завершена",
        }
        status_text = status_messages.get(final_status, "обновлён")
        await call.message.bot.send_message(
            chat_id=author_tg,
            text=f"ℹ️ Ваша заявка №{ticket_id} {status_text}.\nСтатус: <b>{TicketStatus.label(final_status)}</b>",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to notify author {author_tg}: {e}")

    # Подтверждение в теме + обновление клавиатуры
    await call.message.answer(
        f"🔔 Статус заявки №{ticket_id} изменён на: <b>{TicketStatus.label(final_status)}</b>",
        parse_mode="HTML"
    )
    try:
        await call.message.edit_reply_markup(reply_markup=_status_panel_kb(ticket_id))
        await call.answer()
    except Exception:
        pass


# ========== ГЛАВНЫЙ ГРУППОВОЙ ХЕНДЛЕР ==========

@forum_router.message(F.chat.type.in_({ChatType.SUPERGROUP, ChatType.GROUP}))
async def debug_all_group_messages(msg: Message):
    """Отладочный + рабочий хендлер для сообщений из группы."""
    logger.info(
        f"[GROUP MESSAGE] chat_id={msg.chat.id}, user={msg.from_user.id}, "
        f"is_topic={getattr(msg, 'is_topic_message', False)}, "
        f"thread_id={getattr(msg, 'message_thread_id', None)}, "
        f"content_type={msg.content_type}, "
        f"text={msg.text[:50] if msg.text else 'N/A'}"
    )

    # Только сообщения в топиках нужного чата
    is_topic = getattr(msg, "is_topic_message", False)
    thread_id = getattr(msg, "message_thread_id", None)
    if not is_topic or thread_id is None:
        return
    if NOTIFICATION_CHANNEL_ID and msg.chat.id != NOTIFICATION_CHANNEL_ID:
        return

    # Только администраторы
    if not is_admin(msg.from_user.id):
        return

    # Команды обрабатываются отдельно
    if msg.text and msg.text.startswith('/'):
        cmd_text = msg.text.lower().lstrip("/").split("@")[0].split()[0]
        if cmd_text in {"open", "work", "done"}:
            await handle_status_command(msg, cmd_text)
        elif cmd_text == "panel":
            pass  # отдельный handler
        return

    # Не пересылаем системные/бот-сообщения пользователю
    if _is_system_message(msg):
        logger.debug("Skip system/bot message")
        return

    ticket = await get_ticket_by_thread(msg.chat.id, thread_id)
    if not ticket:
        logger.warning(f"❌ No ticket found for thread {thread_id} in chat {msg.chat.id}")
        return

    await _send_to_author(msg.bot, ticket, msg)


# ==== Совместимость со слэш-командами статусов ====
async def handle_status_command(msg: Message, cmd: str):
    thread_id = msg.message_thread_id
    ticket = await get_ticket_by_thread(msg.chat.id, thread_id)
    if not ticket:
        await msg.reply("⚠️ Заявка для этого топика не найдена.")
        return

    status_map = {
        "open": TicketStatus.OPEN,
        "work": TicketStatus.WORK,
        "done": TicketStatus.CANCELLED,
    }
    target_status = status_map.get(cmd)
    if not target_status:
        await msg.reply("❌ Неизвестная команда.")
        return

    if ticket.get("status") == target_status:
        await msg.reply(f"ℹ️ Заявка уже имеет статус: {TicketStatus.label(target_status)}")
        return

    res = await set_ticket_status(ticket["id"], target_status)
    if not res:
        await msg.reply("❌ Не удалось изменить статус.")
        return

    _, new_status, author_tg = res

    try:
        status_messages = {
            TicketStatus.OPEN: "возвращена в работу",
            TicketStatus.WORK: "взята в работу",
            TicketStatus.CANCELLED: "завершена",
        }
        status_text = status_messages.get(new_status, "обновлён")
        await msg.bot.send_message(
            chat_id=author_tg,
            text=f"ℹ️ Ваша заявка №{ticket['id']} {status_text}.\nСтатус: <b>{TicketStatus.label(new_status)}</b>",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to notify author {author_tg}: {e}")

    await _rename_topic(msg.bot, msg.chat.id, thread_id, ticket["id"], new_status)
    await _close_topic_if_done(msg.bot, msg.chat.id, thread_id, new_status)
    await msg.reply(f"✅ Статус изменён на: <b>{TicketStatus.label(new_status)}</b>", parse_mode="HTML")
