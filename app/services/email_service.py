import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import Optional

from app.logger import logger
from config.settings import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD


async def send_email(
    to: str,
    subject: str,
    body: str,
    attachment_path: Optional[str] = None
) -> bool:
    """
    Универсальная отправка email

    Args:
        to: Email получателя
        subject: Тема письма
        body: Текст письма
        attachment_path: Путь к файлу-вложению (опционально)

    Returns:
        True если отправка успешна, False в случае ошибки
    """
    if not all([SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD]):
        logger.error("SMTP settings not configured")
        return False

    if not to:
        logger.error("Recipient email not provided")
        return False

    try:
        logger.info(f"Preparing email: to='{to}', subject='{subject}'")

        # Создаём сообщение
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = to
        msg['Subject'] = subject

        # Добавляем текст
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        # Добавляем вложение если есть
        if attachment_path:
            if not _attach_file(msg, attachment_path):
                logger.warning(f"Failed to attach file: {attachment_path}")
                # Продолжаем отправку без вложения

        # Отправляем в отдельном потоке
        await asyncio.to_thread(_send_smtp, msg, to)
        logger.info(f"Email sent successfully to {to}")
        return True

    except Exception as e:
        logger.error(f"Error sending email to {to}: {e}", exc_info=True)
        return False


def _attach_file(msg: MIMEMultipart, attachment_path: str) -> bool:
    """
    Прикрепляет файл к сообщению

    Args:
        msg: MIME сообщение
        attachment_path: Путь к файлу

    Returns:
        True если файл успешно прикреплен
    """
    try:
        file_path = Path(attachment_path)
        if not file_path.exists():
            logger.error(f"Attachment not found: {attachment_path}")
            return False

        with open(file_path, 'rb') as f:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(f.read())

        encoders.encode_base64(part)
        part.add_header(
            'Content-Disposition',
            f'attachment; filename="{file_path.name}"'
        )
        msg.attach(part)
        logger.info(f"Attached file: {file_path.name}")
        return True

    except Exception as e:
        logger.error(f"Failed to attach file: {e}")
        return False


def _send_smtp(msg: MIMEMultipart, recipient: str) -> None:
    """
    Синхронная отправка email через SMTP

    Args:
        msg: Подготовленное сообщение
        recipient: Email получателя

    Raises:
        Exception: При ошибке отправки
    """
    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, recipient, msg.as_string())
        server.quit()
        logger.info(f"Email успешно отправлен на {recipient}")
        logger.debug(f"SMTP connection closed successfully for {recipient}")

    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP authentication failed: {e}")
        raise Exception("Ошибка аутентификации SMTP. Проверьте логин и пароль.")
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error: {e}")
        raise Exception(f"Ошибка SMTP: {e}")
    except Exception as e:
        logger.error(f"Email sending error: {e}")
        raise Exception(f"Не удалось отправить email: {e}")