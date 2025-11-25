# app/user/__init__.py
from app.user.router import user_router  # сам роутер
import app.user.assemble

__all__ = ["user_router"]
