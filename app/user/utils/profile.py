from database.requests import get_user_by_tg, check_month_meters, count_user_tickets_grouped

MONTHS_RU = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
             "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]


async def build_profile_text(user_id: int) -> str:
    user_info = await get_user_by_tg(user_id)
    if not user_info:
        return "⛔ Профиль не найден."

    # --- Адрес ---
    addr = "—"
    if any([user_info.get("street"), user_info.get("house"), user_info.get("apartment")]):
        parts: list[str] = []
        if user_info.get("street"):
            parts.append(f"{user_info['street']}")
        if user_info.get("house"):
            parts.append(f"д. {user_info['house']}")
        if user_info.get("apartment"):
            parts.append(f"кв. {user_info['apartment']}")
        addr = ", ".join(parts)

    # --- Показания за текущий месяц (ГВС) ---
    meters = await check_month_meters(user_id)
    period = meters.get("period") or {}
    month = period.get("month", 0)
    year = period.get("year", "—")
    month_name = MONTHS_RU[month] if month and month < len(MONTHS_RU) else "—"

    hot = meters.get("hot", {}) or {}

    if hot.get("exists"):
        # Есть хотя бы одно показание
        readings = hot.get("readings") or []

        # Группируем все показания по номеру счётчика
        by_meter: dict[int, list[dict[str, str]]] = {}
        for r in readings:
            num = r.get("meter_number") or 1
            by_meter.setdefault(num, []).append(r)

        lines: list[str] = []
        lines.append(f"✅ Показания переданы.\n")

        # Подробный список по каждому счётчику
        if by_meter:
            for meter_num in sorted(by_meter.keys()):
                lines.append(f"🔥 Счётчик №{meter_num}:")
                for r in by_meter[meter_num]:
                    line = f"  • {r['date']}: <b>{r['value']}</b> м³"
                    if r.get("created_at_local"):
                        line += f"\n<i>(внесено: {r['created_at_local']})</i>"
                    lines.append(line)
                lines.append("")  # пустая строка между счётчиками

        hot_info = "\n".join(lines).strip()
    else:
        hot_info = "❌ Показания за текущий месяц ещё не переданы."

    # --- Статистика заявок ---
    counters = await count_user_tickets_grouped(user_id)
    open_cnt = counters.get("OPEN", 0)
    work_cnt = counters.get("WORK", 0)
    done_cnt = counters.get("CANCELLED", 0)
    active_cnt = counters.get("active", 0)
    total_cnt = counters.get("total", 0)

    return (
        f"<blockquote><b>Имя:</b> {user_info.get('name') or '—'}\n"
        f"<b>Адрес:</b> {addr}\n"
        f"<b>Телефон:</b> {user_info.get('phone') or '—'}</blockquote>\n\n"
        f"🔥 <b>Показания ГВС за {month_name} {year}</b>\n\n"
        f"{hot_info}\n\n"
        f"👷 <b>Мои заявки</b>\n"
        f"• Активные: <b>{active_cnt}</b>\n(Открыты: {open_cnt}, В работе: {work_cnt})\n"
        f"• Завершены: <b>{done_cnt}</b>\n"
        f"• Всего: <b>{total_cnt}</b>\n\n"
        "<i>Показания принимаем с 10 до 23 числа каждого месяца</i>"
    )
