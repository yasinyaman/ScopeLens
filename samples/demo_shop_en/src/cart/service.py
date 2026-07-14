"""Cart and order management (Clause 2.1)."""

from catalog import service as catalog
from db import store


def add_item(cart_id: str, product_id: str, qty: int) -> dict:
    cart = store.load("carts", cart_id) or {"items": {}}
    products = catalog.list_products()
    if not any(p.get("id") == product_id for p in products):
        raise ValueError(f"no such product: {product_id}")
    cart["items"][product_id] = cart["items"].get(product_id, 0) + qty
    store.save("carts", cart_id, cart)
    return cart


def create_order(cart_id: str) -> dict:
    cart = store.load("carts", cart_id)
    if cart is None or not cart["items"]:
        raise ValueError("cart is empty")
    order = {"cart_id": cart_id, "status": "created", "items": dict(cart["items"])}
    store.save("orders", cart_id, order)
    return order
