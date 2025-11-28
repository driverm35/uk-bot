from __future__ import annotations

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


class EmailServiceError(Exception):
    """Базовое исключение для сервиса email"""
    pass


class EmailConfigurationError(EmailServiceError):
    """Ошибка конфигурации SMTP"""
    pass


class EmailNetworkError(EmailServiceError):
    """Сетевая ошибка при отправке"""
    pass


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
    # Валидация конфигурации
    if not all([SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD]):
        logger.error("SMTP settings not configured. Check environment variables.")
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
        logger.info(f"✅ Email sent successfully to {to}")
        return True

    except EmailNetworkError as e:
        logger.error(
            f"❌ Network error sending email to {to}: {e}. "
            "Check Docker network configuration and firewall rules."
        )
        return False

    except EmailConfigurationError as e:
        logger.error(f"❌ Configuration error: {e}")
        return False

    except Exception as e:
        logger.error(f"❌ Unexpected error sending email to {to}: {e}", exc_info=True)
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
        EmailNetworkError: При сетевых ошибках
        EmailConfigurationError: При ошибках конфигурации
        Exception: При других ошибках
    """
    try:
        logger.debug(f"Connecting to SMTP server: {SMTP_HOST}:{SMTP_PORT}")

        # Создаём подключение с таймаутом
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)

        logger.debug("Starting TLS encryption")
        server.starttls()

        logger.debug(f"Authenticating as {SMTP_USER}")
        server.login(SMTP_USER, SMTP_PASSWORD)

        logger.debug(f"Sending email to {recipient}")
        server.sendmail(SMTP_USER, recipient, msg.as_string())

        server.quit()
        logger.info(f"✅ SMTP session completed successfully for {recipient}")

    except (OSError, ConnectionError, TimeoutError) as e:
        error_msg = (
            f"Network error connecting to {SMTP_HOST}:{SMTP_PORT}. "
            "Possible causes:\n"
            "1. Docker network isolation - check docker-compose.yml network settings\n"
            "2. Firewall blocking outbound SMTP connections\n"
            "3. SMTP server not accessible from container\n"
            f"Original error: {e}"
        )
        logger.error(error_msg)
        raise EmailNetworkError(error_msg) from e

    except smtplib.SMTPAuthenticationError as e:
        error_msg = f"SMTP authentication failed. Check SMTP_USER and SMTP_PASSWORD. Error: {e}"
        logger.error(error_msg)
        raise EmailConfigurationError(error_msg) from e

    except smtplib.SMTPException as e:
        error_msg = f"SMTP protocol error: {e}"
        logger.error(error_msg)
        raise EmailConfigurationError(error_msg) from e

    except Exception as e:
        logger.error(f"Unexpected error in SMTP send: {e}", exc_info=True)
        raise