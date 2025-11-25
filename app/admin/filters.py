# app/admin/filters.py
from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery
from app.admin.acl import is_admin

class AdminFilter(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        return is_admin(event.from_user.id)
