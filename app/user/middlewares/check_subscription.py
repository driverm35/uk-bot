from __future__ import annotations

from typing import Callable, Awaitable, Any, Dict, Iterable, Union
from aiogram import BaseMiddleware, Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    ChatMember,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from database.requests import get_or_create_user
import app.user.keyboards.user_kb as kb
from app.user.utils.profile import build_profile_text
from config.settings import REQUIRED_CHANNELS

check_router = Router(name="check_router")

# Только этот колбэк пропускаем без проверки
WHITELIST_CB = {"check_subs"}


def _is_subscribed(m: ChatMember) -> bool:
    return m.status not in ("left", "kicked")


class SubscriptionMiddleware(BaseMiddleware):
    """
    Проверяет подписку пользователя на каналы/чаты из REQUIRED_CHANNELS.
    Поддерживаются как username (строки с '@'), так и числовые chat_id (int).
    """

    def __init__(self, channels: Iterable[str | int] | None = None):
        super().__init__()
        # Если ничего не передали — берём из настроек
        ch = REQUIRED_CHANNELS if channels is None else channels

        # Нормализуем кортеж каналов. Важно: строку не разворачиваем посимвольно.
        if isinstance(ch, str):
            ch = (ch,)
        else:
            ch = tuple(ch)  # type: ignore[arg-type]

        self.channels: tuple[Union[str, int], ...] = tuple(ch)

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any],
    ) -> Any:
        # ✅ Разрешаем только колбэк "✅ Проверить" без проверки
        if isinstance(event, CallbackQuery) and event.data in WHITELIST_CB:
            return await handler(event, data)

        bot = data["bot"]
        user_id = event.from_user.id

        # 🔒 Проверяем подписку для ЛЮБОГО апдейта (включая /start)
        for ch in self.channels:
            try:
                member = await bot.get_chat_member(ch, user_id)
                if not _is_subscribed(member):
                    await self._prompt_subscribe(event, ch, data)
                    return
            except Exception:
                # нет прав/канал приватный/ошибка — считаем неподписанным
                await self._prompt_subscribe(event, ch, data)
                return

        # ✅ Подписан — пропускаем к хендлеру
        return await handler(event, data)

    async def _prompt_subscribe(
        self,
        event: Message | CallbackQuery,
        channel: str | int,
        data: Dict[str, Any],
    ) -> None:
        """
        Показывает приглашение подписаться. Если канал указан числовым ID,
        пытаемся получить username через get_chat — если его нет (приватный),
        кнопку-ссылку не показываем.
        """
        bot = data["bot"]
        url: str | None = None

        if isinstance(channel, str) and channel.startswith("@"):
            url = f"https://t.me/{channel.lstrip('@')}"
        elif isinstance(channel, int):
            # Пытаемся получить username у чата по id
            try:
                chat = await bot.get_chat(channel)
                if getattr(chat, "username", None):
                    url = f"https://t.me/{chat.username}"
            except Exception:
                # Не удалось получить username — без ссылки
                url = None

        # Собираем инлайн-клавиатуру корректными типами
        rows: list[list[InlineKeyboardButton]] = []
        if url:
            rows.append([InlineKeyboardButton(text="📲 Подписаться", url=url)])
        rows.append([InlineKeyboardButton(text="✅ Проверить", callback_data="check_subs")])
        markup = InlineKeyboardMarkup(inline_keyboard=rows)

        text = "📢 Для продолжения подпишитесь на канал и нажмите <b>✅ Проверить</b>."

        if isinstance(event, CallbackQuery):
            sent = await event.message.answer(text, reply_markup=markup, parse_mode="HTML")
        else:
            sent = await event.answer(text, reply_markup=markup, parse_mode="HTML")

        # Сохраним id приглашения, чтобы потом удалить по кнопке «Проверить»
        state: FSMContext | None = data.get("state")
        if state:
            st = await state.get_data()
            st["subs_prompt_id"] = sent.message_id
            await state.update_data(**st)


@check_router.callback_query(F.data == "check_subs")
async def check_subscriptions(call: CallbackQuery, state: FSMContext):
    # Повторная проверка подписки
    for ch in (REQUIRED_CHANNELS if not isinstance(REQUIRED_CHANNELS, str) else (REQUIRED_CHANNELS,)):
        try:
            m = await call.bot.get_chat_member(ch, call.from_user.id)
            if m.status == "left":
                await call.answer("❌ Вы всё ещё не подписаны!", show_alert=True)
                return
            if m.status == "kicked":
                await call.answer("❌ Вы были исключены из канала!", show_alert=True)
                return
        except Exception:
            await call.answer("❌ Не удалось проверить подписку.", show_alert=True)
            return

    # успех — алерт
    try:
        await call.answer("✅ Подписка подтверждена!", show_alert=True)
    except Exception:
        pass

    # 🎯 удаляем приглашение по сохранённому ID
    subs_prompt_id = (await state.get_data()).get("subs_prompt_id")
    if subs_prompt_id:
        try:
            await call.bot.delete_message(call.message.chat.id, subs_prompt_id)
        except TelegramBadRequest:
            pass
        except Exception:
            pass
        finally:
            await state.update_data(subs_prompt_id=None)

    # На всякий случай удалим и сам месседж с кнопкой (если это он)
    try:
        if call.message:
            await call.message.delete()
    except TelegramBadRequest:
        pass
    except Exception:
        pass

    # Продолжаем обычный поток: новый пользователь — заполнение профиля
    user = await get_or_create_user(
        telegram_id=call.from_user.id,
        username=call.from_user.username or "",
        name=call.from_user.full_name or "",
        status="new",
    )
    if user and getattr(user, "status", "") == "new":
        await call.message.answer("👋 Добро пожаловать! Пожалуйста, заполните профиль.", reply_markup=kb.new_user())
    else:
        text = "👤 Личный кабинет\n\n"
        text += await build_profile_text(call.from_user.id)
        await call.message.answer(text, reply_markup=kb.main_menu(), parse_mode="HTML")
