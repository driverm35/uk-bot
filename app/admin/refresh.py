# app/admin/refresh.py
import asyncio
from contextlib import suppress
from app.logger import logger
from database.requests import list_admin_ids
from app.admin.acl import set_admin_ids

async def refresh_admin_cache_periodically(interval_hours: int = 12):
    """Периодически обновляет кеш admin_ids каждые N часов."""
    seconds = max(1, int(interval_hours * 3600))
    while True:
        try:
            ids = await list_admin_ids()
            set_admin_ids(ids)
            logger.info(f"[admin-cache] обновлено: {ids}")
            await asyncio.sleep(seconds)
        except asyncio.CancelledError:
            # корректное завершение
            logger.info("[admin-cache] остановлен")
            raise
        except Exception as e:
            logger.exception(f"[admin-cache] ошибка обновления: {e}")
            # подождём минуту и попробуем снова
            await asyncio.sleep(60)
