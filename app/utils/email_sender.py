from typing import Optional

from app.logger import logger
from app.services.email_service import send_email
from config.settings import ACCOUNTANT_EMAIL


async def send_meters_email(
    subject: str,
    body: str,
    attachment_path: Optional[str] = None
) -> bool:
    """
    Отправка email с показаниями счётчиков бухгалтеру
    
    Args:
        subject: Тема письма
        body: Текст письма
        attachment_path: Путь к файлу-вложению (опционально)
    
    Returns:
        True если отправка успешна, False в случае ошибки
    """
    if not ACCOUNTANT_EMAIL:
        logger.error("ACCOUNTANT_EMAIL not configured")
        return False

    logger.info(f"Sending meters email to accountant: subject='{subject}'")

    success = await send_email(
        to=ACCOUNTANT_EMAIL,
        subject=subject,
        body=body,
        attachment_path=attachment_path
    )

    if success:
        logger.info("Meters email sent successfully to accountant")
    else:
        logger.error("Failed to send meters email to accountant")

    return success