"""Authentication: salted password hashing (stdlib pbkdf2) + DB user store.

No new heavyweight crypto dependency; a future switch to `argon2`/`bcrypt` stays isolated
to this module (`hash_password`/`verify_password`). Roles: `pmo` | `engineer` | `viewer`.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from etki.persistence.db import init_schema, make_engine, make_session_factory
from etki.persistence.models import UserProjectRow, UserRow

ROLES = {"pmo", "engineer", "viewer"}
_ITERATIONS = 200_000


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Returns (salt_hex, hash_hex). A random salt is generated if none is given."""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITERATIONS)
    return salt, digest.hex()


def session_token(salt: str, password_hash: str) -> str:
    """Short, non-reversible session-binding token (see UserRecord.token)."""
    return hashlib.sha256(f"{salt}:{password_hash}".encode()).hexdigest()[:16]


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    _, computed = hash_password(password, salt)
    return hmac.compare_digest(computed, expected_hash)  # constant-time comparison


@dataclass(frozen=True)
class UserRecord:
    username: str
    role: str
    # Session-binding token: a short hash derivative of (salt, password_hash). It goes
    # into the session cookie at login; `current_user` re-derives and compares it on
    # every request, so a password change / user deletion invalidates live sessions
    # without server-side session storage. Empty for records not meant for sessions.
    token: str = ""


class UserStore:
    """User CRUD + authentication (passwords are never stored in plaintext)."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def count(self) -> int:
        with self._sf() as session:
            return len(session.scalars(select(UserRow.username)).all())

    def get(self, username: str) -> UserRecord | None:
        with self._sf() as session:
            row = session.get(UserRow, username)
            return UserRecord(row.username, row.role) if row else None

    def create(
        self,
        username: str,
        password: str,
        role: str,
        projects: list[str] | None = None,
    ) -> UserRecord:
        username = username.strip()
        if not username or not password:
            raise ValueError("kullanıcı adı ve parola zorunlu")
        if role not in ROLES:
            raise ValueError(f"geçersiz rol: {role}")
        salt, pw_hash = hash_password(password)
        with self._sf() as session:
            if session.get(UserRow, username) is not None:
                raise ValueError(f"kullanıcı zaten var: {username}")
            session.add(
                UserRow(
                    username=username,
                    password_hash=pw_hash,
                    salt=salt,
                    role=role,
                    created_at=datetime.now(UTC),
                )
            )
            for pid in dict.fromkeys(projects or []):  # order preserved, duplicates dropped
                session.add(UserProjectRow(username=username, project_id=pid))
            session.commit()
        return UserRecord(username, role)

    def projects_for(self, username: str) -> set[str]:
        """Project ids the user may access (empty set if none granted)."""
        with self._sf() as session:
            rows = session.scalars(
                select(UserProjectRow.project_id).where(UserProjectRow.username == username)
            ).all()
            return set(rows)

    def set_projects(self, username: str, projects: list[str]) -> None:
        """REPLACES the user's project grants with the given list."""
        with self._sf() as session:
            if session.get(UserRow, username) is None:
                raise ValueError(f"kullanıcı yok: {username}")
            for row in session.scalars(
                select(UserProjectRow).where(UserProjectRow.username == username)
            ).all():
                session.delete(row)
            for pid in dict.fromkeys(projects):
                session.add(UserProjectRow(username=username, project_id=pid))
            session.commit()

    def authenticate(self, username: str, password: str) -> UserRecord | None:
        """Returns a UserRecord (incl. session token) on the correct password, else None."""
        with self._sf() as session:
            row = session.get(UserRow, username.strip())
            if row is None or not verify_password(password, row.salt, row.password_hash):
                return None
            return UserRecord(row.username, row.role, session_token(row.salt, row.password_hash))

    def get_with_token(self, username: str) -> UserRecord | None:
        """Record incl. the CURRENT session token — `current_user` compares it against
        the cookie's copy on every request (password change/deletion logs the user out)."""
        with self._sf() as session:
            row = session.get(UserRow, username)
            if row is None:
                return None
            return UserRecord(row.username, row.role, session_token(row.salt, row.password_hash))

    def list_users(self) -> list[UserRecord]:
        with self._sf() as session:
            rows = session.scalars(select(UserRow).order_by(UserRow.username)).all()
            return [UserRecord(r.username, r.role) for r in rows]

    def count_role(self, role: str) -> int:
        with self._sf() as session:
            return len(
                session.scalars(select(UserRow.username).where(UserRow.role == role)).all()
            )

    def set_role(self, username: str, role: str) -> None:
        if role not in ROLES:
            raise ValueError(f"geçersiz rol: {role}")
        with self._sf() as session:
            row = session.get(UserRow, username)
            if row is None:
                raise ValueError(f"kullanıcı yok: {username}")
            row.role = role
            session.commit()

    def set_password(self, username: str, new_password: str) -> None:
        """Also rotates the session token → the user's live sessions drop."""
        if not new_password:
            raise ValueError("parola boş olamaz")
        with self._sf() as session:
            row = session.get(UserRow, username)
            if row is None:
                raise ValueError(f"kullanıcı yok: {username}")
            row.salt, row.password_hash = hash_password(new_password)
            session.commit()

    def delete(self, username: str) -> None:
        """Removes the user + project grants (case history/audit stays untouched)."""
        with self._sf() as session:
            row = session.get(UserRow, username)
            if row is None:
                raise ValueError(f"kullanıcı yok: {username}")
            for grant in session.scalars(
                select(UserProjectRow).where(UserProjectRow.username == username)
            ).all():
                session.delete(grant)
            session.delete(row)
            session.commit()


def build_user_store(db_url: str | None = None) -> UserStore:
    """Builds schema + UserStore from Settings.db_url (same DB as the case repository)."""
    engine = make_engine(db_url)
    init_schema(engine)
    return UserStore(make_session_factory(engine))


class LoginRateLimiter:
    """Failed-login throttle per (client IP, username): after `max_failures` failures
    within `window_s`, the pair is locked for `lock_s`.

    In-memory on purpose: startup enforces a single worker (`_enforce_single_worker`),
    so process-local state is authoritative; a restart resetting counters is acceptable
    for this threat model (it only slows an online brute force, which it still does).
    """

    def __init__(
        self,
        max_failures: int = 5,
        window_s: float = 900.0,
        lock_s: float = 900.0,
        now: Callable[[], float] | None = None,  # injectable clock for tests
    ) -> None:
        self.max_failures = max_failures
        self.window_s = window_s
        self.lock_s = lock_s
        self._now = now or time.monotonic
        self._failures: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}

    def retry_after(self, key: str) -> float:
        """Seconds until the key may try again; 0 = allowed now."""
        now = self._now()
        until = self._locked_until.get(key, 0.0)
        if until > now:
            return until - now
        if until:  # lock expired — forget it (and start a fresh failure window)
            self._locked_until.pop(key, None)
            self._failures.pop(key, None)
        return 0.0

    def register_failure(self, key: str) -> None:
        now = self._now()
        window = [ts for ts in self._failures.get(key, []) if now - ts < self.window_s]
        window.append(now)
        self._failures[key] = window
        if len(window) >= self.max_failures:
            self._locked_until[key] = now + self.lock_s

    def reset(self, key: str) -> None:
        """Successful login clears the slate for the pair."""
        self._failures.pop(key, None)
        self._locked_until.pop(key, None)
