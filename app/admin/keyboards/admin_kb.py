from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters.callback_data import CallbackData
from database.models import TicketStatus
from datetime import datetime


class AdminCb(CallbackData, prefix="adm"):
    a: str
    status: str | None = None
    page: int | None = None
    id: int | None = None
    type: str | None = None
    period: str | None = None
    month: int | None = None
    year: int | None = None
    format: str | None = None


cb = AdminCb


def admin_main_menu():
    """Главное меню администратора"""
    kb = InlineKeyboardBuilder()
    kb.button(text="📤 Выгрузить показания", callback_data=cb(a="admin_export_meters").pack())
    kb.button(text="📧 Отправить на email", callback_data=cb(a="admin_send_meters_to_mail").pack())
    kb.button(text="📊 Выгрузить заявки", callback_data=cb(a="admin_export_tickets").pack())
    kb.button(text="📢 Создать пост", callback_data=AdminCb(a="admin_create_post").pack())
    kb.adjust(2, 1, 1)
    return kb.as_markup()


# ========== Клавиатуры для экспорта показаний ==========

def export_menu_keyboard():
    """Меню выбора типа счётчика для экспорта (только ГВС)"""
    kb = InlineKeyboardBuilder()
    kb.button(text="🔥 Горячая вода", callback_data=AdminCb(a="export_type", type="hot").pack())
    kb.button(text="🔙 Назад", callback_data=AdminCb(a="admin_main_menu").pack())
    kb.adjust(1)
    return kb.as_markup()


def period_menu_keyboard(meter_type: str):
    """Меню выбора периода для показаний"""
    kb = InlineKeyboardBuilder()
    kb.button(text="📅 Текущий месяц", callback_data=AdminCb(a="export_period", type=meter_type, period="current_month").pack())
    kb.button(text="📆 Выбрать месяц", callback_data=AdminCb(a="export_period", type=meter_type, period="select_month").pack())
    kb.button(text="📊 Весь год", callback_data=AdminCb(a="export_period", type=meter_type, period="year").pack())
    kb.button(text="📋 Все данные", callback_data=AdminCb(a="export_period", type=meter_type, period="all").pack())
    kb.button(text="◀️ Назад", callback_data=AdminCb(a="export_back_to_type").pack())
    kb.adjust(2, 2, 1)
    return kb.as_markup()


# ========== Клавиатуры для отправки по email ==========

def email_type_menu():
    """Меню выбора типа счётчика для email (только ГВС)"""
    kb = InlineKeyboardBuilder()
    kb.button(text="🔥 Горячая вода", callback_data=AdminCb(a="email_select_type", type="hot").pack())
    kb.button(text="🔙 Назад", callback_data=AdminCb(a="admin_main_menu").pack())
    kb.adjust(1)
    return kb.as_markup()


def email_month_menu(meter_type: str, year: int):
    """Меню выбора месяца для email"""
    kb = InlineKeyboardBuilder()
    
    MONTHS = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
              "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
    
    for month_num in range(1, 13):
        kb.button(
            text=MONTHS[month_num],
            callback_data=AdminCb(a="email_select_month", type=meter_type, month=month_num, year=year).pack()
        )
    
    kb.button(text="🔙 Назад", callback_data=AdminCb(a="admin_send_meters_to_mail").pack())
    kb.adjust(2, 2, 2, 2, 2, 2, 1)
    return kb.as_markup()


def email_confirm_menu(meter_type: str, month: int, year: int):
    """Меню подтверждения отправки email"""
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ Отправить",
        callback_data=AdminCb(a="email_send_confirm", type=meter_type, month=month, year=year).pack()
    )
    kb.button(text="❌ Отменить", callback_data=AdminCb(a="email_cancel").pack())
    kb.adjust(1)
    return kb.as_markup()


def email_back_to_menu():
    """Кнопка возврата в главное меню после email"""
    kb = InlineKeyboardBuilder()
    kb.button(text="🏠 Главное меню", callback_data=AdminCb(a="admin_main_menu").pack())
    return kb.as_markup()


# ========== Клавиатуры для экспорта заявок ==========

def tickets_export_period_menu():
    """Меню выбора периода для экспорта заявок"""
    kb = InlineKeyboardBuilder()
    kb.button(text="📅 Сегодня", callback_data=AdminCb(a="tex_period", period="today").pack())
    kb.button(text="📆 Текущая неделя", callback_data=AdminCb(a="tex_period", period="week").pack())
    kb.button(text="🗓 Текущий месяц", callback_data=AdminCb(a="tex_period", period="month").pack())
    kb.button(text="📋 Выбрать месяц", callback_data=AdminCb(a="tex_period", period="select_month").pack())
    kb.button(text="📅 Произвольный период", callback_data=AdminCb(a="tex_period", period="custom").pack())
    kb.button(text="📊 Все данные", callback_data=AdminCb(a="tex_period", period="all").pack())
    kb.button(text="🔙 Назад", callback_data=AdminCb(a="admin_main_menu").pack())
    kb.adjust(2, 2, 2, 1)
    return kb.as_markup()


def tickets_export_month_menu(year: int = None):
    """Меню выбора месяца для экспорта заявок"""
    if year is None:
        year = datetime.now().year

    MONTHS = [
        "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
        "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
    ]

    kb = InlineKeyboardBuilder()
    for month_num in range(1, 13):
        kb.button(
            text=MONTHS[month_num],
            callback_data=AdminCb(a="tex_month", month=month_num, year=year).pack()
        )
    kb.button(text="🔙 Назад", callback_data=AdminCb(a="tex_back").pack())
    kb.adjust(3, 3, 3, 3, 1)
    return kb.as_markup()


def tickets_export_format_menu():
    """Меню выбора формата файла для экспорта заявок"""
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Excel", callback_data=AdminCb(a="tex_format", format="xlsx").pack())
    kb.button(text="📄 CSV", callback_data=AdminCb(a="tex_format", format="csv").pack())
    kb.button(text="🔙 Назад", callback_data=AdminCb(a="tex_back").pack())
    kb.adjust(1)
    return kb.as_markup()


def tickets_export_back_menu():
    """Кнопка возврата для экспорта заявок"""
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data=AdminCb(a="tex_back").pack())
    return kb.as_markup()


# ========== Клавиатуры для постов ==========

def post_add_button_choice():
    """Выбор добавления кнопки к посту"""
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить кнопку", callback_data="post:add_button")
    kb.button(text="Без кнопки", callback_data="post:no_button")
    kb.adjust(1)
    return kb.as_markup()


def post_confirm_keyboard():
    """Подтверждение публикации поста"""
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить", callback_data=AdminCb(a="post_confirm").pack())
    kb.button(text="❌ Отменить", callback_data=AdminCb(a="post_cancel").pack())
    kb.adjust(1)
    return kb.as_markup()


# ========== Прочие клавиатуры ==========

def admin_open_button(user_id: int):
    """Кнопка для открытия профиля пользователя"""
    kb = InlineKeyboardBuilder()
    kb.button(text="👤 Открыть заявку", url="https://t.me/+xeH-TfLjn3UzYzJi")
    kb.button(text="🏠 Главное меню", callback_data=AdminCb(a="admin_main_menu").pack())
    kb.adjust(1)
    return kb.as_markup()


def status_panel_kb(ticket_id: int):
    """Панель управления статусом заявки"""
    kb = InlineKeyboardBuilder()
    kb.button(text="🟢 Открыта", callback_data=f"tset:{ticket_id}:open")
    kb.button(text="🟡 В работе", callback_data=f"tset:{ticket_id}:work")
    kb.button(text="🟣 Завершена", callback_data=f"tset:{ticket_id}:done")
    kb.adjust(1)
    return kb.as_markup()