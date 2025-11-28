from decouple import config, Csv
from pathlib import Path
from typing import Tuple, Union

IRKUTSK_TZ_NAME = "Asia/Irkutsk"

_raw_channels = config("REQUIRED_CHANNELS", default="", cast=Csv())

def _coerce_channel(s: str) -> Union[str, int, None]:
    s = s.strip()
    if not s:
        return None
    # username-канал
    if s.startswith("@"):
        return s
    # числовой id канала/супергруппы
    try:
        return int(s)
    except ValueError:
        # если забыли @, но это похоже на username — подставим
        if s.replace("_", "").isalnum():
            return f"@{s}"
        return None

def _parse_days_csv(raw: str) -> list[int]:
    out = []
    for p in raw.split(","):
        p = p.strip()
        if p:
            out.append(int(p))
    return out

# Корневая директория проекта
BASE_DIR = Path(__file__).resolve().parent.parent

# Путь к БД (из окружения или по умолчанию)
_db_path_str = config("DATABASE_PATH", default="data/database.db")

# Преобразуем в Path
DATABASE_PATH = Path(_db_path_str)

# Если путь относительный – делаем его относительно BASE_DIR
if not DATABASE_PATH.is_absolute():
    DATABASE_PATH = BASE_DIR / DATABASE_PATH

# Создаём директорию, если её нет
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

# URL для sqlite+aiosqlite
DATABASE_URL = f"sqlite+aiosqlite:///{DATABASE_PATH}"

METER_REMIND_DAYS: list[int] = _parse_days_csv(config("METER_REMIND_DAYS", "25"))

# Время напоминания (по Иркутску)
METER_REMIND_HOUR = int(config("METER_REMIND_HOUR", "20"))  # 20:00
METER_REMIND_MINUTE = int(config("METER_REMIND_MINUTE", "0"))
METER_REMIND_START_DAY = int(config("METER_REMIND_START_DAY", "24"))

REQUIRED_CHANNELS: Tuple[Union[str, int], ...] = tuple(
    ch for ch in (_coerce_channel(x) for x in _raw_channels) if ch is not None
)

# Телеграм Бот
BOT_TOKEN = config('BOT_TOKEN')

DATABASE_URL = f"sqlite+aiosqlite:///{DATABASE_PATH}"

# ID администраторов
GROUP_ID = config('GROUP_ID')

NOTIFICATION_CHANNEL_ID = int(config('NOTIFICATION_CHANNEL_ID'))

METER_CHAT_ID = config('METER_CHAT_ID')
METER_HOT_WATER_TOPIC_ID = config('METER_HOT_WATER_TOPIC_ID')
METER_COLD_WATER_TOPIC_ID = config('METER_COLD_WATER_TOPIC_ID')

# SMTP settings for email
SMTP_HOST = config("SMTP_HOST", default="smtp.mail.ru")
SMTP_PORT = config("SMTP_PORT", cast=int, default=587)
SMTP_USER = config("SMTP_USER", default="")
SMTP_PASSWORD = config("SMTP_PASSWORD", default="")
SMTP_USE_TLS = config("SMTP_USE_TLS", cast=bool, default=False)
EMAIL_FROM = config("EMAIL_FROM", default="")

# Email recipients
ACCOUNTANT_EMAIL = config("ACCOUNTANT_EMAIL", default="734895ld@mail.ru")
ENGINEER_EMAIL = config("ENGINEER_EMAIL", default="uk_ld@bk.ru")

# Meter export settings
METER_EXPORT_DAY = config("METER_EXPORT_DAY", cast=int, default=24)
METER_EXPORT_HOUR = config("METER_EXPORT_HOUR", cast=int, default=10)
METER_EXPORT_MINUTE = config("METER_EXPORT_MINUTE", cast=int, default=0)