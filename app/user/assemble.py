# app/user/assemble.py
from app.user.router import user_router

from app.user.handlers.edit_profile import edit_router
from app.user.handlers.meter import meter_router
from app.user.handlers.registration import reg_router
from app.user.handlers.ticket import ticket_router
from app.user.handlers.user import start_router
from app.user.middlewares.check_subscription import check_router


# Вклеиваем подроутеры в один общий
user_router.include_router(start_router)
user_router.include_router(edit_router)
user_router.include_router(meter_router)
user_router.include_router(reg_router)
user_router.include_router(ticket_router)
user_router.include_router(check_router)
