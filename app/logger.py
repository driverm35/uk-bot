import logging
import sys

# Очистка обработчиков перед настройкой логирования
logging.root.handlers.clear()

# Настраиваем базовый логгер
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    datefmt="%d.%m.%Y %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)]  # Вывод в консоль
)

# Отключаем дублирование логов SQLAlchemy
logging.getLogger("sqlalchemy.engine").propagate = False
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

# Создаём единый формат для всех логгеров
formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    datefmt="%d.%m.%Y %H:%M:%S",
)

# Применяем формат ко всем логгерам
for logger_name in logging.root.manager.loggerDict:
    log = logging.getLogger(logger_name)
    for handler in log.handlers:
        handler.setFormatter(formatter)

# Основной логгер приложения
logger = logging.getLogger("logger")
