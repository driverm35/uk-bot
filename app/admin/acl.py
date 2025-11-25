# app/admin/acl.py
from typing import Set
_admin_ids: Set[int] = set()

def set_admin_ids(ids: list[int]):
    _admin_ids.clear()
    _admin_ids.update(ids)

def is_admin(tg_id: int) -> bool:
    return tg_id in _admin_ids

def get_admin_ids() -> list[int]:
    """Получить список всех админов из кеша"""
    return list(_admin_ids)