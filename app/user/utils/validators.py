import re

# ВАЛИДАТОРЫ
HOUSE_VALID_RE = re.compile(r"^\s*\d{1,5}(?:[\/\-]\d{1,4})?[a-zA-Zа-яА-Я]?\s*$")
HOUSE_BAD_PREFIX_RE = re.compile(r"^\s*(д\.?|дом|кв\.?|квартира)\s*", re.IGNORECASE)

def is_valid_phone(text: str) -> bool:
    """Проверка телефона: должно быть ровно 11 цифр (не считая +)"""
    # Убираем все кроме цифр
    digits = re.sub(r'\D', '', text)
    return len(digits) == 11

def is_valid_house(text: str) -> bool:
    if HOUSE_BAD_PREFIX_RE.match(text or ""):
        return False
    return bool(HOUSE_VALID_RE.match(text or ""))

def is_valid_apartment(text: str) -> bool:
    t = (text or "").strip()
    if t in {"-", "—"}:
        return True
    return t.isdigit() and 0 < len(t) <= 5

def is_valid_street(text: str) -> bool:
    """Разрешаем улицы с буквами, цифрами, пробелами и дефисами."""
    if not text:
        return False
    t = text.strip()
    # минимум 2 символа, хотя бы одна буква
    if len(t) < 2 or not re.search(r"[A-Za-zА-Яа-яЁё]", t):
        return False
    return bool(re.match(r"^[\w\s\-\.\,\/]+$", t))