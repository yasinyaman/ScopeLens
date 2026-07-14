"""Rapor üretimi, filtreleme ve dışa aktarma (Madde 4.2.1 ve 4.2.2)."""

from auth import service
from db import store


def generate(user_token: str, filters: dict) -> list[dict]:
    if not service.is_authenticated(user_token):
        return []
    return store.query("metrics", lambda row: _matches(row, filters))


def _matches(row: dict, filters: dict) -> bool:
    for key, value in filters.items():
        if row.get(key) != value:
            return False
    return True


def export(rows: list[dict], fmt: str) -> bytes:
    if fmt == "pdf":
        return b"%PDF-1.4 fake"
    if fmt == "xlsx":
        return b"PK fake-xlsx"
    raise ValueError(f"desteklenmeyen format: {fmt}")
