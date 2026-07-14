"""Basit bellek-içi veri erişim katmanı (persistence)."""

from collections.abc import Callable

_DB: dict[str, dict[str, dict]] = {}


def save(table: str, key: str, value: dict) -> None:
    _DB.setdefault(table, {})[key] = value


def load(table: str, key: str) -> dict | None:
    return _DB.get(table, {}).get(key)


def query(table: str, predicate: Callable[[dict], bool]) -> list[dict]:
    rows = []
    for row in _DB.get(table, {}).values():
        if predicate(row):
            rows.append(row)
    return rows
