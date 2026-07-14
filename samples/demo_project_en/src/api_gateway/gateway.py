"""Request routing and authorization gate."""

from auth import service


def handle(request: dict) -> dict:
    path = request.get("path", "")
    token = request.get("token", "")
    if path.startswith("/secure") and not service.is_authenticated(token):
        return {"status": 401}
    return {"status": 200, "path": path}
