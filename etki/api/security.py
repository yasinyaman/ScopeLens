"""RBAC — the role now comes from the verified SESSION (the old fake `X-Role` header
was removed).

The user authenticates via `/login`; the role is kept signed in the session cookie.
Approval endpoints require the `pmo` role. `require_user` makes every protected route
require a valid session; a session-less request raises `NotAuthenticated` (redirects to
`/login` in the UI, 401 in the API). See docs/KVKK.md.

Project isolation (minimal RBAC v2): access is read from the `user_projects` table.
The `pmo` role has access to all projects via `Settings.pmo_global` (on by default); when
turned off, in a multi-customer setup everyone — including pmo — only sees the projects
they're granted. An inaccessible project returns 404 (not 403, so as not to leak its
existence).
"""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from etki.api.context import AppContext, get_context
from etki.auth import UserStore
from etki.config import Settings
from etki.i18n import t

ROLES = {"pmo", "engineer", "viewer"}
# Roles that may CREATE/CHANGE work (triage, pre-analysis, chat, batch analyze).
# `viewer` is read-only: sees everything it has project access to, mutates nothing.
WRITER_ROLES = {"pmo", "engineer"}


class NotAuthenticated(Exception):
    """No valid session. The handler in app.py converts this to a UI redirect / API 401."""


def current_user(
    request: Request, ctx: AppContext = Depends(get_context)  # noqa: B008
) -> dict[str, str]:
    """Returns the session's user ({username, role}); raises NotAuthenticated if absent.

    The cookie is stateless, so this ALSO re-validates it against the DB on every request:
    - `exp` (set at login by remember-me) in the past → session over;
    - the session-binding token no longer matches (password changed / user deleted) → out;
    - the role always comes fresh from the DB (an admin's role change applies immediately).
    """
    user = request.session.get("user")
    if not user:
        raise NotAuthenticated()
    exp = user.get("exp")
    if exp is not None and time.time() > float(exp):
        request.session.clear()
        raise NotAuthenticated()
    rec = ctx.user_store.get_with_token(str(user.get("username", "")))
    if rec is None or not user.get("tok") or rec.token != user.get("tok"):
        request.session.clear()
        raise NotAuthenticated()
    user["role"] = rec.role
    return user


UserDep = Annotated[dict[str, str], Depends(current_user)]


def require_user(user: UserDep) -> dict[str, str]:
    """Only enforces that the user is logged in (role doesn't matter)."""
    return user


def require_pmo(user: UserDep) -> dict[str, str]:
    if user.get("role") != "pmo":
        raise HTTPException(status_code=403, detail=t("err.pmo_required"))
    return user


def require_writer(user: UserDep) -> dict[str, str]:
    """Mutating work needs a writing role (`pmo`/`engineer`); `viewer` gets 403."""
    if user.get("role") not in WRITER_ROLES:
        raise HTTPException(status_code=403, detail=t("err.writer_required"))
    return user


# ---------------------------------------------------------------------------
# Project-based access (minimal RBAC v2)
# ---------------------------------------------------------------------------
def accessible_projects(user: dict[str, str], user_store: UserStore) -> set[str] | None:
    """Project ids the user may see; None = ALL projects (pmo-global)."""
    if user.get("role") == "pmo" and Settings().pmo_global:
        return None
    return user_store.projects_for(user.get("username", ""))


def has_project_access(user: dict[str, str], project_id: str, user_store: UserStore) -> bool:
    allowed = accessible_projects(user, user_store)
    return allowed is None or project_id in allowed


def ensure_project_access(
    user: dict[str, str], project_id: str | None, user_store: UserStore
) -> None:
    """Raises 404 when access is missing (not 403, so as not to leak the project's existence).

    Not checked when `project_id` is empty/None — this is backward compatibility for old
    records that carry no project info; all new records carry a project_id."""
    if project_id and not has_project_access(user, project_id, user_store):
        raise HTTPException(status_code=404, detail="Proje bulunamadı")


def require_project_access(
    project_id: str,
    user: UserDep,
    ctx: Annotated[AppContext, Depends(get_context)],
) -> dict[str, str]:
    """`/projeler/{project_id}/...` route dependency — requires access to the path's project."""
    ensure_project_access(user, project_id, ctx.user_store)
    return user
