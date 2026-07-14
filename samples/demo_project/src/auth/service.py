"""Yerel kimlik doğrulama ve oturum yönetimi (Madde 3.1).

SSO / üçüncü taraf IdP entegrasyonu BURADA YOKTUR — sözleşmede kapsam dışı (Madde 7.1).
"""

from config import settings
from db import store


def login(username: str, password: str) -> str | None:
    user = store.load("users", username)
    if user is None:
        return None
    if user.get("password") != password:
        return None
    token = f"tok-{username}"
    store.save("sessions", token, {"user": username, "ttl": settings.get("session_ttl")})
    return token


def logout(token: str) -> None:
    store.save("sessions", token, {})


def is_authenticated(token: str) -> bool:
    session = store.load("sessions", token)
    return bool(session) and "user" in session
