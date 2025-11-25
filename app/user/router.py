# app/user/router.py
from aiogram import Router
from app.user.middlewares.check_subscription import SubscriptionMiddleware

user_router = Router(name="user_router")
user_router.message.middleware(SubscriptionMiddleware())
user_router.callback_query.middleware(SubscriptionMiddleware())
