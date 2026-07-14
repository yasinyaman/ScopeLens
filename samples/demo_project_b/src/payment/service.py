"""Ödeme — kredi/banka kartı (Madde 2.2).

Kripto para ile ödeme BURADA YOKTUR — sözleşmede kapsam dışı (Madde 6.1).
"""

from cart import service as cart
from db import store

_PROVIDERS = ("credit_card", "debit_card")


def charge(cart_id: str, provider: str, amount: float) -> dict:
    if provider not in _PROVIDERS:
        raise ValueError(f"desteklenmeyen ödeme sağlayıcı: {provider}")
    order = cart.create_order(cart_id)
    receipt = {"order": order["cart_id"], "provider": provider, "amount": amount, "status": "paid"}
    store.save("payments", cart_id, receipt)
    return receipt


def refund(cart_id: str) -> dict:
    receipt = store.load("payments", cart_id)
    if receipt is None:
        raise ValueError("ödeme bulunamadı")
    receipt["status"] = "refunded"
    store.save("payments", cart_id, receipt)
    return receipt
