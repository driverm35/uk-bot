FROM python:3.13-slim

WORKDIR /app

# Копируем uv из официального образа
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV UV_SYSTEM_PYTHON=1

# Только pyproject.toml — uv сам создаст lockfile внутри
COPY pyproject.toml ./

# Ставим зависимости (создаст .venv и uv.lock внутри контейнера)
RUN uv sync --no-dev --no-install-project

# Копируем остальной код
COPY . .

ENV PYTHONUNBUFFERED=1

CMD ["uv", "run", "run.py"]
