# app/admin/__init__.py
from aiogram import Router
from app.admin.filters import AdminFilter
from app.admin.handlers.admin import start_router
from app.admin.handlers.post import post_router
from app.admin.handlers.get_meter import get_meter_router
from app.admin.handlers.export_tickets import export_tickets_router
from app.admin.handlers.send_meters_email import send_meters_router

admin_router = Router(name="admin_router")
admin_router.message.filter(AdminFilter())
admin_router.callback_query.filter(AdminFilter())

admin_router.include_router(post_router)
admin_router.include_router(get_meter_router)
admin_router.include_router(start_router)
admin_router.include_router(export_tickets_router)
admin_router.include_router(send_meters_router)

