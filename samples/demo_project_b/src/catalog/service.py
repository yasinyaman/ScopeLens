"""Ürün kataloğu — listeleme, filtreleme, arama (Madde 2.3)."""

from db import store


def list_products(category: str | None = None) -> list[dict]:
    if category is None:
        return store.query("products", lambda row: True)
    return store.query("products", lambda row: row.get("category") == category)


def search(term: str) -> list[dict]:
    term_low = term.lower()
    return store.query("products", lambda row: term_low in row.get("name", "").lower())
