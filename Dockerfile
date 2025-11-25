FROM python:3.13-slim

WORKDIR /app

# Установка uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Включаем системный Python для uv
ENV UV_SYSTEM_PYTHON=1

# Копирование файлов зависимостей
COPY pyproject.toml uv.lock* ./

# Установка зависимостей
RUN uv sync --frozen --no-dev --no-install-project

# Копирование остального кода
COPY . .

# Установка проекта
RUN uv sync --frozen --no-dev

ENV PYTHONUNBUFFERED=1

# Запуск через uv
CMD ["uv", "run", "run.py"]