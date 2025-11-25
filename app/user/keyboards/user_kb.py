from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.filters.callback_data import CallbackData
from enum import Enum
from typing import Optional
from datetime import date
from database.models import TicketStatus

class UserCb(CallbackData, prefix="u"):
    a: str
    type: Optional[str] = None
    month: Optional[int] = None
    year: Optional[int] = None
    id: Optional[int] = None
    page: Optional[int] = None
    status: Optional[str] = None
    u: Optional[str] = None
cb = UserCb

# Определяем, строковые ли значения у Enum
_IS_STR_ENUM = isinstance(TicketStatus.OPEN.value, str)

def _status_val_to_str(s: TicketStatus) -> str:
    """
    Конвертируем TicketStatus -> str для callback_data.
    Для строкового Enum вернём 'open'/'work'/'cancelled',
    для числового — '0'/'1'/...
    """
    val = s.value if isinstance(s, Enum) else s
    if _IS_STR_ENUM:
        return str(val)
    return str(int(val))

def _status_from_val(v: str) -> TicketStatus:
    """
    Конвертируем str из callback_data обратно в TicketStatus.
    """
    if _IS_STR_ENUM:
        return TicketStatus(v)
    return TicketStatus(int(v))

def ticket_history_filter_menu() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(
            text=f"🟢 {TicketStatus.label(TicketStatus.OPEN)}",
            callback_data=cb(a="uh_list", id=0, status=_status_val_to_str(TicketStatus.OPEN), page=1).pack()
        )],
        [InlineKeyboardButton(
            text=f"🟡 {TicketStatus.label(TicketStatus.WORK)}",
            callback_data=cb(a="uh_list", id=0, status=_status_val_to_str(TicketStatus.WORK), page=1).pack()
        )],
        [InlineKeyboardButton(
            text=f"⚪ {TicketStatus.label(TicketStatus.CANCELLED)}",
            callback_data=cb(a="uh_list", id=0, status=_status_val_to_str(TicketStatus.CANCELLED), page=1).pack()
        )],
        [InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=cb(a="ticket_menu", id=0, status="0", page=0).pack()
        )],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def ticket_history_list_menu(items: list[dict], status: TicketStatus, page: int, total: int, per_page: int) -> InlineKeyboardMarkup:
    rows = []
    for it in items:
        created = it["created_at"].strftime("%d.%m %H:%M") if it.get("created_at") else "—"
        rows.append([InlineKeyboardButton(
            text=f"№{it['id']} • {created}",
            callback_data=cb(a="uh_open", id=it["id"], status=_status_val_to_str(status), page=page).pack()
        )])

    pages = max(1, (total + per_page - 1) // per_page)
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(
            text="« Назад",
            callback_data=cb(a="uh_list", id=0, status=_status_val_to_str(status), page=page - 1).pack()
        ))
    if page < pages:
        nav.append(InlineKeyboardButton(
            text="Вперёд »",
            callback_data=cb(a="uh_list", id=0, status=_status_val_to_str(status), page=page + 1).pack()
        ))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(
        text="⬅️ К фильтрам",
        callback_data=cb(a="uh_menu", id=0, status="0", page=0).pack()
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ticket_history_detail_actions(tid: int, status: TicketStatus) -> InlineKeyboardMarkup:
    rows = []
    if status in (TicketStatus.OPEN, TicketStatus.WORK):
        rows.append([InlineKeyboardButton(text="✍️ Ответить диспетчеру", callback_data=f"user_reply:{tid}")])
        rows.append([InlineKeyboardButton(
                        text="🚫 Отменить заявку",
                        callback_data=cb(a="uh_cancel", id=tid, status=_status_val_to_str(status), page=0).pack())
                    ])
    rows.append([InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data=cb(a="uh_back", id=0, status=_status_val_to_str(status), page=1).pack()
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def new_user():
    kb = InlineKeyboardBuilder()
    kb.button(text="📝 Заполнить профиль", callback_data=cb(a="fill_profile").pack())
    return kb.as_markup()

def main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="🚰 Показания", callback_data=cb(a="meter_menu").pack())
    kb.button(text="👷 Меню заявок", callback_data=cb(a="ticket_menu").pack())
    kb.button(text="✏️ Редактировать данные", callback_data=cb(a="edit_profile").pack())
    # kb.button(text="🛟 Поддержка", callback_data=cb(a="help").pack())
    kb.adjust(1, 1, 2)
    return kb.as_markup()

def edit_profile():
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Имя", callback_data=cb(a="edit_name").pack())
    kb.button(text="📞 Телефон", callback_data=cb(a="edit_phone").pack())
    kb.button(text="🏙️ Улица", callback_data=cb(a="edit_street").pack())
    kb.button(text="🏠 Дом", callback_data=cb(a="edit_house").pack())
    kb.button(text="🚪 Квартира", callback_data=cb(a="edit_apartment").pack())
    kb.button(text="🔙 Назад", callback_data=cb(a="cabinet").pack())
    kb.adjust(2, 2)
    return kb.as_markup()

def type_meter_menu():
    kb = InlineKeyboardBuilder()
    kb.button(
        text="🔥 Горячая вода",
        callback_data=cb(a="select_meter_type", type="hot").pack()
    )
    # kb.button(
    #     text="❄️ Холодная вода",
    #     callback_data=cb(a="select_meter_type", type="cold").pack()
    # )
    kb.button(text="🔙 Назад", callback_data=cb(a="cabinet").pack())
    kb.adjust(1, 1)
    return kb.as_markup()

def meter_history(meter_type: str):
    kb = InlineKeyboardBuilder()
    current_year = date.today().year

    months = [
        ("Январь", 1), ("Февраль", 2), ("Март", 3),
        ("Апрель", 4), ("Май", 5), ("Июнь", 6),
        ("Июль", 7), ("Август", 8), ("Сентябрь", 9),
        ("Октябрь", 10), ("Ноябрь", 11), ("Декабрь", 12)
    ]

    for month_name, month_num in months:
        kb.button(
            text=month_name,
            callback_data=cb(a="history_month", type=meter_type, month=month_num, year=current_year).pack()
        )

    kb.button(
        text="🔙 Назад",
        callback_data=cb(a="back_to_meter", type=meter_type).pack()
    )
    kb.adjust(3, 3, 3, 3, 1)
    return kb.as_markup()

def meter_menu(meter_type: str, month_num: int, month_name: str, year: int):
    kb = InlineKeyboardBuilder()
    kb.button(
        text="📃 История",
        callback_data=cb(a="meter_history", type=meter_type).pack()
    )
    kb.button(
        text=f"🚰 Передать за {month_name}",
        callback_data=cb(a="meter_new", type=meter_type, month=month_num, year=year).pack()
    )
    kb.button(
        text="🔙 Назад",
        callback_data=cb(a="meter_menu").pack()
    )
    kb.adjust(1, 1, 1)
    return kb.as_markup()

def back_to_meter_type(meter_type: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data=cb(a="select_meter_type", type=meter_type).pack())
    return kb.as_markup()

def cancel_input():
    """Кнопка отмены ввода"""
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отменить", callback_data=cb(a="cancel_input").pack())
    return kb.as_markup()

def confirm_reading():
    """Кнопки для предпросмотра показаний"""
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить", callback_data=cb(a="confirm_reading").pack())
    kb.button(text="✏️ Изменить", callback_data=cb(a="edit_reading").pack())
    kb.button(text="❌ Отменить", callback_data=cb(a="cancel_input").pack())
    kb.adjust(1)
    return kb.as_markup()

def back_to_main():
    """Кнопка возврата в главное меню"""
    kb = InlineKeyboardBuilder()
    kb.button(text="🏠 Главное меню", callback_data=cb(a="cabinet").pack())
    return kb.as_markup()


def ticket_menu_no_active():
    kb = InlineKeyboardBuilder()
    kb.button(text="📝 Создать заявку", callback_data=cb(a="ticket_create").pack())
    kb.button(text="📃 Мои заявки", callback_data=cb(a="ticket_history").pack())
    kb.button(text="🔙 Назад", callback_data=cb(a="cabinet").pack())
    kb.adjust(1, 1)
    return kb.as_markup()

def ticket_menu_with_active(ticket_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="📂 Открыть", callback_data=cb(a="ticket_open_active", id=str(ticket_id)).pack())
    kb.button(text="❌ Отменить", callback_data=cb(a="ticket_cancel_active", id=str(ticket_id)).pack())
    kb.button(text="🔙 Назад", callback_data=cb(a="cabinet").pack())
    kb.adjust(1, 1, 1)
    return kb.as_markup()

def ticket_cancel_creation():
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отменить", callback_data=cb(a="ticket_abort").pack())
    kb.button(text="🔙 Назад", callback_data=cb(a="ticket_menu").pack())
    kb.adjust(1, 1)
    return kb.as_markup()

def ticket_preview_controls():
    kb = InlineKeyboardBuilder()
    kb.button(text="✍️ Изменить", callback_data=cb(a="ticket_edit").pack())
    kb.button(text="➕ Вложения", callback_data=cb(a="ticket_add_attachments").pack())
    kb.button(text="✅ Подтвердить", callback_data=cb(a="ticket_confirm").pack())
    kb.button(text="❌ Отменить", callback_data=cb(a="ticket_abort").pack())
    kb.adjust(2, 2)
    return kb.as_markup()

def ticket_back_to_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data=cb(a="ticket_menu").pack())
    return kb.as_markup()

def ticket_attachments_controls():
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Готово", callback_data=cb(a="ticket_attachments_done").pack())
    kb.button(text="❌ Отменить", callback_data=cb(a="ticket_abort").pack())
    kb.adjust(1, 1)
    return kb.as_markup()

def ticket_active_controls(ticket_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отменить заявку", callback_data=cb(a="ticket_cancel_active", id=str(ticket_id)).pack())
    kb.button(text="🔙 Назад", callback_data=cb(a="ticket_menu").pack())
    kb.adjust(1, 1)
    return kb.as_markup()

def phone_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой отправки телефона"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def remove_keyboard() -> ReplyKeyboardRemove:
    """Убрать ReplyKeyboard"""
    return ReplyKeyboardRemove()

# --- Вспомогательная клавиатура "Ответить диспетчеру" ---
def reply_to_dispatcher_kb(ticket_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✍️ Ответить диспетчеру", callback_data=f"user_reply:{ticket_id}")
    kb.button(text="🔙 Назад в меню", callback_data=cb(a="cabinet").pack())
    kb.adjust(1)
    return kb.as_markup()

def meter_main_menu(month_num: int, month_name: str, year: int, submitted_count: int):
    """Главное меню показаний ГВС"""
    kb = InlineKeyboardBuilder()
    
    # Кнопка подачи показаний (если ещё не все переданы)
    if submitted_count < 3:  # MAX_METERS
        kb.button(
            text=f"🚰 Передать показания ({submitted_count}/3)",
            callback_data=cb(a="meter_select_number", month=month_num, year=year).pack()
        )
    
    # История всегда доступна
    kb.button(
        text="📃 История показаний",
        callback_data=cb(a="meter_history").pack()
    )
    
    kb.button(
        text="🔙 Назад",
        callback_data=cb(a="cabinet").pack()
    )
    
    kb.adjust(1)
    return kb.as_markup()


def meter_number_menu(month_num: int, year: int):
    """Меню выбора номера счётчика"""
    kb = InlineKeyboardBuilder()
    
    for i in range(1, 4):  # 1, 2, 3
        kb.button(
            text=f"Счётчик №{i}",
            callback_data=cb(a="meter_new", id=i, month=month_num, year=year).pack()
        )
    
    kb.button(
        text="🔙 Назад",
        callback_data=cb(a="meter_menu").pack()
    )
    
    kb.adjust(1)
    return kb.as_markup()


def meter_history():
    """Меню истории показаний"""
    kb = InlineKeyboardBuilder()
    current_year = date.today().year

    months = [
        ("Январь", 1), ("Февраль", 2), ("Март", 3),
        ("Апрель", 4), ("Май", 5), ("Июнь", 6),
        ("Июль", 7), ("Август", 8), ("Сентябрь", 9),
        ("Октябрь", 10), ("Ноябрь", 11), ("Декабрь", 12)
    ]

    for month_name, month_num in months:
        kb.button(
            text=month_name,
            callback_data=cb(a="history_month", month=month_num, year=current_year).pack()
        )

    kb.button(
        text="🔙 Назад",
        callback_data=cb(a="meter_menu").pack()
    )
    kb.adjust(3, 3, 3, 3, 1)
    return kb.as_markup()


def back_to_meter_menu():
    """Кнопка возврата в меню показаний"""
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data=cb(a="meter_history").pack())
    return kb.as_markup()