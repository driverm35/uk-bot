# app/user/handlers/ticket.py
import asyncio
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.enums import ContentType
from aiogram.exceptions import TelegramBadRequest

from app.message_utils import replace_or_send_message
import app.user.keyboards.user_kb as kb
from app.user.keyboards.user_kb import cb
from app.admin.keyboards.admin_kb import admin_open_button, status_panel_kb
from app.helpers import clear_chat_history, save_msg
from app.user.utils.states import TicketStates, AttachmentType
from app.services.ticket_notifications import send_ticket_email_notification
from database.requests import (
    create_ticket, cancel_ticket, get_ticket_by_id, get_user_by_tg,
    add_ticket_attachment, set_ticket_thread, list_user_tickets, count_user_tickets,
    get_user_ticket_full, get_ticket_thread_info
)
from database.models import TicketStatus
from app.user.keyboards.user_kb import _status_from_val
from config.settings import NOTIFICATION_CHANNEL_ID
from app.admin.acl import get_admin_ids
from app.logger import logger

ticket_router = Router(name="ticket_router")

def _status_emoji(s: TicketStatus) -> str:
    return {
        TicketStatus.OPEN: "🟢",
        TicketStatus.WORK: "🟡",
        TicketStatus.CANCELLED: "🟣",
    }.get(s, "⚪")

async def _rename_topic(bot: Bot, chat_id: int, thread_id: int, ticket_id: int, status: TicketStatus):
    """Переименовывает топик с новым статусом."""
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


async def delete_service_message(bot, chat_id: int, state: FSMContext, key: str) -> None:
    """Удаляет служебное сообщение по ключу из state."""
    data = await state.get_data()
    msg_id = data.get(key)
    if msg_id:
        try:
            await bot.delete_message(chat_id, msg_id)
        except Exception:
            pass
        await state.update_data(**{key: None})


async def send_service_message(
    bot, chat_id: int, state: FSMContext, key: str, text: str, reply_markup
) -> Message:
    """Удаляет старое служебное сообщение и отправляет новое."""
    await delete_service_message(bot, chat_id, state, key)
    msg = await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode="HTML"
    )
    await state.update_data(**{key: msg.message_id})
    await save_msg(msg, state)
    return msg


async def send_album_completion_message(bot, chat_id: int, state: FSMContext, album_count: int, total_count: int):
    """Отправляет сообщение после завершения получения альбома."""
    await asyncio.sleep(0.8)  # Ждём, пока все файлы альбома придут

    # Проверяем, что задача всё ещё актуальна
    data = await state.get_data()
    current_task_id = data.get("album_task_id")
    this_task_id = id(asyncio.current_task())

    if current_task_id != this_task_id:
        # Задача была отменена или заменена новой
        return

    text = f"✅ Принят альбом из {album_count} файлов. Всего прикреплено: {total_count}"
    await send_service_message(
        bot, chat_id, state, "service_msg_id",
        text, kb.ticket_attachments_controls()
    )
    await state.update_data(album_task_id=None)


@ticket_router.callback_query(cb.filter(F.a == "ticket_menu"))
async def ticket_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    logger.info(f"User {call.from_user.id} opened ticket menu")

    text = "👷 Меню заявок"
    rm = kb.ticket_menu_no_active()

    await replace_or_send_message(
        bot=call.bot,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        reply_markup=rm,
        parse_mode="HTML"
    )
    await call.answer()


# Новая заявка
@ticket_router.callback_query(cb.filter(F.a == "ticket_create"))
async def ticket_create_start(call: CallbackQuery, state: FSMContext):
    logger.info(f"User {call.from_user.id} started creating ticket")

    await state.set_state(TicketStates.waiting_text)
    await state.update_data(
        attachments=[],
        handled_msg_ids=[],
        album={"id": None, "count": 0},
        service_msg_id=None,
        album_task_id=None
    )

    text = (
        "📝 Опишите проблему максимально конкретно:\n"
        "• адрес/подъезд/этаж/дверь (если актуально)\n"
        "• что случилось, что уже пробовали\n"
        "• когда заметили\n\n"
        "Отправьте текст одним сообщением."
    )

    sent = await replace_or_send_message(
        bot=call.bot,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        reply_markup=kb.ticket_cancel_creation(),
        parse_mode="HTML"
    )
    await save_msg(sent, state)
    await call.answer()


@ticket_router.message(TicketStates.waiting_text, F.text.len() >= 5)
async def ticket_text_captured(msg: Message, state: FSMContext):
    logger.info(f"User {msg.from_user.id} entered ticket text: {msg.text[:50]}...")

    await save_msg(msg, state)
    await state.update_data(
        text=msg.text.strip(),
        attachments=[],  # Сбрасываем вложения при новом тексте
        handled_msg_ids=[],
        album={"id": None, "count": 0},
        album_task_id=None
    )
    await state.set_state(TicketStates.attachments)

    text = (
        "📝 Текст принят.\n\n"
        "📎 Теперь прикрепите фото/видео/документы/аудио/голосовые (можно несколько).\n"
        "Когда закончите — нажмите «Готово» или «Отмена»."
    )
    await send_service_message(
        msg.bot, msg.chat.id, state, "service_msg_id",
        text, kb.ticket_attachments_controls()
    )


@ticket_router.message(TicketStates.waiting_text)
async def ticket_text_invalid(msg: Message, state: FSMContext):
    logger.warning(f"User {msg.from_user.id} entered too short ticket text")

    try:
        await msg.delete()
    except Exception:
        pass

    await send_service_message(
        msg.bot, msg.chat.id, state, "service_msg_id",
        "❗ Текст заявки слишком короткий.\nПожалуйста, опишите проблему подробнее (минимум 5 символов).",
        kb.ticket_cancel_creation()
    )


@ticket_router.callback_query(cb.filter(F.a == "ticket_edit"), TicketStates.preview)
async def ticket_edit(call: CallbackQuery, state: FSMContext):
    logger.info(f"User {call.from_user.id} editing ticket text")

    await state.set_state(TicketStates.waiting_text)

    await replace_or_send_message(
        bot=call.bot,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="✍️ Отправьте новый текст заявки одним сообщением.",
        reply_markup=kb.ticket_cancel_creation(),
        parse_mode="HTML"
    )
    await call.answer()


@ticket_router.callback_query(cb.filter(F.a == "ticket_abort"))
async def ticket_abort(call: CallbackQuery, state: FSMContext):
    logger.info(f"User {call.from_user.id} aborted ticket creation")

    # Удаляем только служебные сообщения, оставляем историю
    data = await state.get_data()
    service_msg_id = data.get("service_msg_id")
    if service_msg_id:
        try:
            await call.bot.delete_message(call.message.chat.id, service_msg_id)
        except Exception:
            pass

    await state.clear()

    await replace_or_send_message(
        bot=call.bot,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="❌ Создание заявки отменено.",
        reply_markup=kb.ticket_menu_no_active()
    )
    await call.answer()


@ticket_router.message(
    TicketStates.attachments,
    F.content_type.in_({
        ContentType.PHOTO, ContentType.VIDEO, ContentType.DOCUMENT,
        ContentType.AUDIO, ContentType.VOICE
    })
)
async def ticket_collect_attachments(msg: Message, state: FSMContext):
    data = await state.get_data()

    # Защита от дублей
    handled = set(data.get("handled_msg_ids", []))
    if msg.message_id in handled:
        return
    handled.add(msg.message_id)
    if len(handled) > 100:
        handled = set(list(handled)[-100:])

    attachments = data.get("attachments", [])
    album = data.get("album", {"id": None, "count": 0})
    gid = msg.media_group_id

    # Определяем тип вложения
    attachment = None
    if msg.photo:
        f = msg.photo[-1]
        attachment = {
            "type": AttachmentType.PHOTO,
            "file_id": f.file_id,
            "file_unique_id": f.file_unique_id,
            "caption": msg.caption
        }
    elif msg.video:
        attachment = {
            "type": AttachmentType.VIDEO,
            "file_id": msg.video.file_id,
            "file_unique_id": msg.video.file_unique_id,
            "caption": msg.caption
        }
    elif msg.document:
        attachment = {
            "type": AttachmentType.DOCUMENT,
            "file_id": msg.document.file_id,
            "file_unique_id": msg.document.file_unique_id,
            "caption": msg.caption
        }
    elif msg.audio:
        attachment = {
            "type": AttachmentType.AUDIO,
            "file_id": msg.audio.file_id,
            "file_unique_id": msg.audio.file_unique_id,
            "caption": msg.caption
        }
    elif msg.voice:
        attachment = {
            "type": AttachmentType.VOICE,
            "file_id": msg.voice.file_id,
            "file_unique_id": msg.voice.file_unique_id,
            "caption": None
        }

    if attachment:
        attachments.append(attachment)
        await save_msg(msg, state)

    # Обработка альбомов
    if gid:
        # Это файл из альбома
        if album["id"] != gid:
            # Новый альбом - если был старый, завершаем его
            if album["id"] and album["count"] > 0:
                # Отправляем сообщение о завершении предыдущего альбома
                old_count = album["count"]
                text = f"✅ Принят альбом из {old_count} файлов. Всего прикреплено: {len(attachments) - 1}"
                await send_service_message(
                    msg.bot, msg.chat.id, state, "service_msg_id",
                    text, kb.ticket_attachments_controls()
                )

            album = {"id": gid, "count": 1}
        else:
            # Продолжение текущего альбома
            album["count"] += 1

        await state.update_data(
            attachments=attachments,
            handled_msg_ids=list(handled),
            album=album
        )

        # Создаём задачу для отправки сообщения после завершения альбома
        # Каждый новый файл отменяет предыдущую задачу и создаёт новую
        task = asyncio.create_task(
            send_album_completion_message(
                msg.bot, msg.chat.id, state, album["count"], len(attachments)
            )
        )
        await state.update_data(album_task_id=id(task))

    else:
        # Одиночный файл
        # Если был незавершённый альбом, завершаем его
        if album["id"] and album["count"] > 0:
            old_count = album["count"]
            text = f"✅ Принят альбом из {old_count} файлов."
            await send_service_message(
                msg.bot, msg.chat.id, state, "service_msg_id",
                text, kb.ticket_attachments_controls()
            )

        album = {"id": None, "count": 0}
        await state.update_data(
            attachments=attachments,
            handled_msg_ids=list(handled),
            album=album,
            album_task_id=None
        )

        # Отправляем сообщение сразу для одиночного файла
        text = f"✅ Вложение принято. Всего прикреплено: {len(attachments)}"
        await send_service_message(
            msg.bot, msg.chat.id, state, "service_msg_id",
            text, kb.ticket_attachments_controls()
        )


@ticket_router.callback_query(cb.filter(F.a == "ticket_attachments_done"), TicketStates.attachments)
async def ticket_attachments_done(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()

    # Если есть незавершённый альбом, ждём его завершения
    album = data.get("album", {"id": None, "count": 0})
    if album.get("id") and album.get("count", 0) > 0:
        await asyncio.sleep(1)  # Даём время на завершение альбома
        data = await state.get_data()  # Обновляем data после ожидания

    await state.set_state(TicketStates.preview)

    profile = await get_user_by_tg(call.from_user.id)
    address = ""
    if profile:
        address = f"{profile['street']}, д. {profile['house']}"
        if profile.get('apartment'):
            address += f", кв. {profile['apartment']}"

    count = len(data.get("attachments", []))

    # Более понятный текст для случая без вложений
    attachments_text = f"{count} шт." if count > 0 else "нет"

    text = (
        "👷 <b>Предпросмотр заявки</b>\n\n"
        f"👤 <b>Заявитель:</b> {profile['name'] if profile else '—'}\n"
        f"🏠 <b>Адрес:</b> {address or '—'}\n"
        f"🗒 <b>Текст:</b>\n{data.get('text', '—')}\n\n"
        f"📎 <b>Вложения:</b> {attachments_text}\n\n"
        "Всё верно?"
    )

    # Сначала отправляем/редактируем сообщение предпросмотра
    sent = await replace_or_send_message(
        bot=call.bot,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        reply_markup=kb.ticket_preview_controls(),
        parse_mode="HTML"
    )
    await save_msg(sent, state)

    # Только после этого удаляем старое служебное сообщение (если оно другое)
    service_msg_id = data.get("service_msg_id")
    if service_msg_id and service_msg_id != call.message.message_id:
        try:
            await call.bot.delete_message(call.message.chat.id, service_msg_id)
        except Exception:
            pass

    await state.update_data(service_msg_id=None)
    await call.answer()


@ticket_router.callback_query(cb.filter(F.a == "ticket_confirm"), TicketStates.preview)
async def ticket_confirm(call: CallbackQuery, state: FSMContext):
    logger.info(f"User {call.from_user.id} confirming ticket creation")

    data = await state.get_data()
    text_body = data.get("text", "").strip()

    if not text_body:
        await call.answer("Пустой текст", show_alert=True)
        return

    # Создаём заявку
    ticket = await create_ticket(call.from_user.id, text_body)

    # Профиль/адрес
    profile = await get_user_by_tg(call.from_user.id)
    address = ""
    if profile:
        address = f"{profile['street']}, д. {profile['house']}"
        if profile.get('apartment'):
            address += f", кв. {profile['apartment']}"

    status_emoji = TicketStatus.emoji(ticket.status)
    
    # Форматируем дату для всех нужд
    created_at_str = ticket.created_at.strftime('%d.%m.%Y %H:%M') if ticket.created_at else '—'
    
    # Email уведомление инженеру (асинхронно, не блокируем основной поток)
    email_sent = await send_ticket_email_notification(
        ticket_id=ticket.id,
        user_name=profile['name'] if profile else '—',
        user_phone=profile['phone'] if profile and profile.get('phone') else '—',
        address=address or '—',
        text=ticket.text,
        created_at=created_at_str
    )
    
    if email_sent:
        logger.info(f"Email notification sent successfully for ticket #{ticket.id}")
    # Если не отправлено - уже залогировано в send_ticket_email_notification
    
    # Текст для уведомления в Telegram (форум)
    notify_text = (
        f"<b>Новая заявка №{ticket.id}</b>\n\n"
        f"<blockquote><b>Заявитель:</b> {profile['name'] if profile else '—'}"
        f"{' (@' + profile['username'] + ')' if profile and profile.get('username') else ''}\n"
        f"<b>Телефон:</b> {profile['phone'] if profile and profile.get('phone') else '—'}\n"
        f"<b>Адрес:</b> {address or '—'}\n"
        f"<b>Создано:</b> {created_at_str}\n"
        f"</blockquote>\n\n"
        f"<b>Текст:</b>\n<blockquote>{ticket.text}</blockquote>\n\n"
        f"Установить статус:\nОткрыта: /open\nВ работе: /work\nЗавершена: /done"
    )
    
    # Текст для админов в ЛС
    admin_notify_text = (
        f"<b>Новая заявка №{ticket.id}</b>\n\n"
        f"<blockquote><b>Заявитель:</b> {profile['name'] if profile else '—'}"
        f"{' (@' + profile['username'] + ')' if profile and profile.get('username') else ''}\n"
        f"<b>Телефон:</b> {profile['phone'] if profile and profile.get('phone') else '—'}\n"
        f"<b>Адрес:</b> {address or '—'}\n"
        f"<b>Создано:</b> {created_at_str}\n"
        f"</blockquote>\n"
        f"<b>Текст:</b>\n<blockquote>{ticket.text}</blockquote>\n\n"
    )

    # Форум-топик
    group_chat_id, thread_id = None, None
    if NOTIFICATION_CHANNEL_ID:
        try:
            topic_title = f"{status_emoji} Заявка №{ticket.id}"
            topic = await call.bot.create_forum_topic(
                chat_id=NOTIFICATION_CHANNEL_ID,
                name=topic_title
            )
            group_chat_id, thread_id = NOTIFICATION_CHANNEL_ID, topic.message_thread_id
            await set_ticket_thread(ticket.id, group_chat_id, thread_id)
            await call.bot.send_message(
                chat_id=group_chat_id,
                message_thread_id=thread_id,
                text=notify_text,
                parse_mode="HTML",
                reply_markup=status_panel_kb(ticket.id)
            )
            logger.info(f"Forum topic created for ticket #{ticket.id}")
        except Exception as e:
            logger.error(f"Failed to create forum topic for ticket #{ticket.id}: {e}")

    # Вложения
    attachments = data.get("attachments", [])
    if attachments:
        logger.info(f"Processing {len(attachments)} attachments for ticket #{ticket.id}")
        
    for a in attachments:
        try:
            await add_ticket_attachment(
                ticket_id=ticket.id,
                file_id=a["file_id"],
                file_unique_id=a.get("file_unique_id"),
                atype=a["type"],
                caption=a.get("caption")
            )

            # Отправляем вложение в топик, если он создан
            if group_chat_id and thread_id:
                send_kwargs = {
                    "chat_id": group_chat_id,
                    "message_thread_id": thread_id,
                    "caption": a.get("caption")
                }
                
                if a["type"] == AttachmentType.PHOTO:
                    await call.bot.send_photo(photo=a["file_id"], **send_kwargs)
                elif a["type"] == AttachmentType.VIDEO:
                    await call.bot.send_video(video=a["file_id"], **send_kwargs)
                elif a["type"] == AttachmentType.DOCUMENT:
                    await call.bot.send_document(document=a["file_id"], **send_kwargs)
                elif a["type"] == AttachmentType.AUDIO:
                    await call.bot.send_audio(audio=a["file_id"], **send_kwargs)
                elif a["type"] == AttachmentType.VOICE:
                    await call.bot.send_voice(
                        voice=a["file_id"],
                        chat_id=group_chat_id,
                        message_thread_id=thread_id
                    )
                    
        except Exception as e:
            logger.error(f"Failed to process attachment for ticket #{ticket.id}: {e}")

    # Уведомления админам в ЛС
    admin_ids = get_admin_ids()
    if admin_ids:
        logger.info(f"Sending notifications to {len(admin_ids)} admins")
        
    for admin_id in admin_ids:
        try:
            await call.bot.send_message(
                admin_id,
                admin_notify_text,
                parse_mode="HTML",
                reply_markup=admin_open_button(call.from_user.id)
            )
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")

    # Очистка и ответ пользователю
    await clear_chat_history(call.bot, call.message.chat.id, state)
    await state.clear()

    await call.message.answer(
        f"✅ Заявка №{ticket.id} создана.",
        reply_markup=kb.ticket_menu_with_active(ticket.id),
        parse_mode="HTML"
    )
    await call.answer("Отправлено ✅")




@ticket_router.callback_query(cb.filter(F.a == "ticket_open_active"))
async def ticket_open_active(call: CallbackQuery, callback_data: cb):
    tid = int(callback_data.id)
    t = await get_ticket_by_id(tid)

    if not t or t["status"] not in [TicketStatus.OPEN, TicketStatus.WORK]:
        await replace_or_send_message(
            bot=call.bot,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Заявка не найдена или уже не активна.",
            reply_markup=kb.ticket_back_to_menu(),
            parse_mode="HTML"
        )
        await call.answer()
        return

    profile = await get_user_by_tg(call.from_user.id)
    address = ""
    if profile:
        address = f"{profile['street']}, д. {profile['house']}"
        if profile.get('apartment'):
            address += f", кв. {profile['apartment']}"

    text = (
        f"📂 <b>Активная заявка №{t['id']}</b>\n\n"
        f"<b>Статус:</b> {t.get('status_label', TicketStatus.label(t['status']))}\n"
        f"<b>Адрес:</b> {address or '—'}\n"
        f"<b>Создано:</b> {t['created_at'].strftime('%d.%m.%Y %H:%M') if t['created_at'] else '—'}\n\n"
        f"<b>Текст:</b>\n{t['text']}"
    )

    await replace_or_send_message(
        bot=call.bot,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        reply_markup=kb.ticket_active_controls(t['id']),
        parse_mode="HTML"
    )
    await call.answer()


@ticket_router.callback_query(cb.filter(F.a == "ticket_cancel_active"))
async def ticket_cancel_active(call: CallbackQuery, callback_data: cb):
    tid = int(callback_data.id)

    ok = await cancel_ticket(call.from_user.id, tid)
    if not ok:
        await replace_or_send_message(
            bot=call.bot,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="❌ Не удалось отменить заявку. Возможно, она уже не активна.",
            reply_markup=kb.ticket_back_to_menu(),
            parse_mode="HTML"
        )
        await call.answer()
        return

    # --- уведомления ---
    notify_text = f"🚫 <b>Заявка №{tid} отменена пользователем.</b>"

    # 1) Пишем именно в ТОПИК, если он привязан
    try:
        ti = await get_ticket_thread_info(tid)  # (group_chat_id, thread_id) | None
        if ti:
            gchat, thread = ti
            # Сообщение в ветке
            await call.bot.send_message(
                chat_id=gchat,
                message_thread_id=thread,
                text=notify_text,
                parse_mode="HTML"
            )
            # Переименуем и закроем топик
            await _rename_topic(call.bot, gchat, thread, tid, TicketStatus.CANCELLED)
            try:
                await call.bot.close_forum_topic(chat_id=gchat, message_thread_id=thread)
            except Exception:
                pass
        else:
            # если ветка не привязана — отправим хотя бы в корень (как было)
            if NOTIFICATION_CHANNEL_ID:
                await call.bot.send_message(NOTIFICATION_CHANNEL_ID, notify_text, parse_mode="HTML")
    except Exception:
        # не завалим пользовательский поток, просто проигнорируем
        pass

    # 2) Уведомление админам в ЛС (как было)
    admin_ids = get_admin_ids()
    for admin_id in admin_ids:
        try:
            await call.bot.send_message(
                admin_id,
                notify_text,
                parse_mode="HTML",
                reply_markup=admin_open_button(call.from_user.id)
            )
        except Exception:
            pass

    # 3) Ответ пользователю
    await replace_or_send_message(
        bot=call.bot,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"✅ Заявка №{tid} отменена.",
        reply_markup=kb.ticket_menu_no_active(),
        parse_mode="HTML"
    )
    await call.answer("Отменено ✅")



@ticket_router.callback_query(cb.filter(F.a == "ticket_add_attachments"), TicketStates.preview)
async def ticket_add_attachments(call: CallbackQuery, state: FSMContext):
    await state.set_state(TicketStates.attachments)

    data = await state.get_data()
    await state.update_data(
        attachments=data.get("attachments", []),
        album={"id": None, "count": 0},
        album_task_id=None
    )

    count = len(data.get("attachments", []))
    text = (
        f"📎 Текущее количество вложений: {count}\n\n"
        "Пришлите дополнительные фото/видео/документы/аудио/голосовые.\n"
        "Когда закончите — нажмите «Готово»."
    )

    sent = await replace_or_send_message(
        bot=call.bot,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        reply_markup=kb.ticket_attachments_controls(),
        parse_mode="HTML"
    )
    await save_msg(sent, state)
    await state.update_data(service_msg_id=sent.message_id)
    await call.answer()

# =========================
#     ИСТОРИЯ ПОЛЬЗОВАТЕЛЯ
# =========================

@ticket_router.callback_query(cb.filter(F.a == "ticket_history"))
async def user_history_entry(call: CallbackQuery, state: FSMContext):
    text = "📚 История заявок\nВыберите фильтр:"
    await replace_or_send_message(
        bot=call.bot,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        reply_markup=kb.ticket_history_filter_menu(),
        parse_mode="HTML",
    )
    await call.answer()

@ticket_router.callback_query(cb.filter(F.a == "uh_menu"))
async def user_history_menu(call: CallbackQuery, state: FSMContext):
    text = "📚 История заявок\nВыберите фильтр:"
    await replace_or_send_message(
        bot=call.bot,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        reply_markup=kb.ticket_history_filter_menu(),
        parse_mode="HTML",
    )
    await call.answer()

@ticket_router.callback_query(cb.filter(F.a == "uh_list"))
async def user_history_list(call: CallbackQuery, callback_data: cb, state: FSMContext):
    status = _status_from_val(callback_data.status) if callback_data.status and callback_data.status != "0" else TicketStatus.OPEN
    page = int(callback_data.page or 1)
    per_page = 5

    items = await list_user_tickets(call.from_user.id, status=status, page=page, per_page=per_page)
    total = await count_user_tickets(call.from_user.id, status=status)

    text = (
        f"📋 Ваши заявки: «{TicketStatus.label(status)}»\nВыберите заявку ниже:"
        if items else
        f"📭 Заявок со статусом «{TicketStatus.label(status)}» не найдено."
    )

    await replace_or_send_message(
        bot=call.bot,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        reply_markup=kb.ticket_history_list_menu(items, status, page, total, per_page),
        parse_mode="HTML",
    )
    await call.answer()

@ticket_router.callback_query(cb.filter(F.a == "uh_open"))
async def user_history_open(call: CallbackQuery, callback_data: cb, state: FSMContext):
    tid = int(callback_data.id)
    t = await get_user_ticket_full(call.from_user.id, tid)
    if not t:
        await call.answer("Заявка не найдена", show_alert=True)
        return

    text = (
        f"📂 <b>Заявка №{t['id']}</b>\n"
        f"Статус: <b>{TicketStatus.label(t['status'])}</b>\n"
        f"Адрес: {t['address'] or '—'}\n"
        f"Создано: {t['created_at'].strftime('%d.%m.%Y %H:%M') if t['created_at'] else '—'}\n"
        f"Обновлено: {t['updated_at'].strftime('%d.%m.%Y %H:%M') if t['updated_at'] else '—'}\n\n"
        f"🗒 <b>Текст:</b>\n{t['text']}"
    )
    await replace_or_send_message(
        bot=call.bot,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text,
        reply_markup=kb.ticket_history_detail_actions(t['id'], t['status']),
        parse_mode="HTML",
    )
    await call.answer()

@ticket_router.callback_query(cb.filter(F.a == "uh_back"))
async def user_history_back(call: CallbackQuery, callback_data: cb, state: FSMContext):
    # возвращаемся к списку для того же статуса, страница 1
    fake = cb(a="uh_list", id=0, status=callback_data.status, page=1)
    await user_history_list(call, fake, state)

@ticket_router.callback_query(cb.filter(F.a == "uh_cancel"))
async def user_history_cancel(call: CallbackQuery, callback_data: cb, state: FSMContext):
    tid = int(callback_data.id)
    ok = await cancel_ticket(call.from_user.id, tid)
    if not ok:
        await call.answer("Не удалось отменить. Возможно, уже закрыта.", show_alert=True)
        return

    await call.answer("Заявка отменена ✅")
    # После отмены вернёмся к списку выбранного статуса
    fake = cb(a="uh_list", id=0, status=callback_data.status, page=1)
    await user_history_list(call, fake, state)