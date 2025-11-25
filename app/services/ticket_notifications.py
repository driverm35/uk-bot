from __future__ import annotations

from app.logger import logger
from app.services.email_service import send_email
from config.settings import ENGINEER_EMAIL


async def send_ticket_email_notification(
    ticket_id: int,
    user_name: str,
    user_phone: str,
    address: str,
    text: str,
    created_at: str,
) -> bool:
    """
    Отправка email уведомления инженеру о новой заявке.
    
    Args:
        ticket_id: Номер заявки
        user_name: Имя заявителя
        user_phone: Телефон заявителя
        address: Адрес
        text: Текст заявки
        created_at: Дата создания
        
    Returns:
        True если отправка успешна
    """
    if not ENGINEER_EMAIL:
        logger.warning("ENGINEER_EMAIL not configured, skipping email notification")
        return False

    subject = f"Новая заявка №{ticket_id}"
    
    body = f"""Поступила новая заявка №{ticket_id}

Заявитель: {user_name}
Телефон: {user_phone}
Адрес: {address}
Дата создания: {created_at}

Текст заявки:
{text}

---
Это автоматическое уведомление от системы учёта заявок.
"""

    success = await send_email(
        to=ENGINEER_EMAIL,
        subject=subject,
        body=body
    )
    
    if success:
        logger.info(f"Email notification sent to engineer for ticket #{ticket_id}")
    else:
        logger.error(f"Failed to send email notification for ticket #{ticket_id}")
        
    return success