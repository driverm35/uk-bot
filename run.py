# run.py
from app.logger import logger

import asyncio
from contextlib import suppress
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config.settings import BOT_TOKEN
from app.admin import admin_router
from app.user import user_router
from app.group.ticket_forum import forum_router
from app.tasks.meter_reminder import meter_reminder_loop
from app.tasks.meter_export import meter_export_loop
from database.models import Base, engine
from database.requests import list_admin_ids
from app.admin.acl import set_admin_ids
from app.admin.refresh import refresh_admin_cache_periodically


async def create_tables():
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Таблицы в БД успешно созданы")
    except Exception as e:
        logger.error(f"Ошибка при создании таблиц: {e}")


async def main():
    await create_tables()

    # Первоначальная загрузка кеша админов
    ids = await list_admin_ids()
    set_admin_ids(ids)
    logger.info(f"Администраторы загружены: {ids}")

    # Запускаем периодический рефреш (каждые 12 часов)
    refresh_task = asyncio.create_task(refresh_admin_cache_periodically(12))

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    
    dp.include_router(admin_router)
    dp.include_router(user_router)
    dp.include_router(forum_router)

    # Фоновые задачи
    meter_task = asyncio.create_task(meter_reminder_loop(bot))
    export_task = asyncio.create_task(meter_export_loop())

    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        for task in (refresh_task, meter_task, export_task):
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")