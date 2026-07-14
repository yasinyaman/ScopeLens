"""Payments — credit/debit card (Clause 2.2).

Cryptocurrency payment is NOT here — it is out of scope per the agreement (Clause 6.1).
"""

from cart import service as cart
from db import store

_PROVIDERS = ("credit_card", "debit_card")


def charge(cart_id: str, provider: str, amount: float) -> dict:
    if provider not in _PROVIDERS:
        raise ValueError(f"unsupported payment provider: {provider}")
    order = cart.create_order(cart_id)
    receipt = {"order": order["cart_id"], "provider": provider, "amount": amount, "status": "paid"}
    store.save("payments", cart_id, receipt)
    return receipt


def refund(cart_id: str) -> dict:
    receipt = store.load("payments", cart_id)
    if receipt is None:
        raise ValueError("no payment found for this cart")
    receipt["status"] = "refunded"
    store.save("payments", cart_id, receipt)
    return receipt
