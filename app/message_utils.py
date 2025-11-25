from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramAPIError
from aiogram.types import Message
from app.logger import logger

async def replace_or_send_message(
    bot,
    chat_id: int,
    message_id: int | None,
    text: str,
    reply_markup=None,
    parse_mode: str | None = "HTML",
    disable_web_page_preview: bool = True,
) -> Message | None:
    """
    Безопасно пытаемся отредактировать существующее сообщение,
    при ошибке — отправляем новое. Возвращаем объект Message или None.
    """
    if message_id:
        try:
            return await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview,
            )
        except TelegramBadRequest:
            # невозможно отредактировать (другая разметка, слишком старое, и т.п.)
            pass
        except TelegramForbiddenError:
            logger.warning("Forbidden to edit message in chat_id=%s", chat_id)
        except TelegramAPIError as e:
            logger.error("edit_message_text API error: %s", e)

    try:
        return await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview,
        )
    except TelegramAPIError as e:
        logger.error("send_message API error: %s", e)
        return None
