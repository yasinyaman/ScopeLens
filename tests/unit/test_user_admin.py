"""User administration + session-binding token (RBAC follow-up)."""

import pytest
from etki.auth import UserStore
from etki.persistence.db import init_schema, make_engine, make_session_factory


@pytest.fixture()
def store() -> UserStore:
    engine = make_engine("sqlite:///:memory:")
    init_schema(engine)
    return UserStore(make_session_factory(engine))


def test_list_and_count_role(store: UserStore) -> None:
    store.create("a", "pw-1", "pmo")
    store.create("b", "pw-2", "viewer")
    assert [u.username for u in store.list_users()] == ["a", "b"]
    assert store.count_role("pmo") == 1
    assert store.count_role("viewer") == 1


def test_set_role_validates(store: UserStore) -> None:
    store.create("a", "pw-1", "viewer")
    store.set_role("a", "engineer")
    assert store.get("a").role == "engineer"
    with pytest.raises(ValueError):
        store.set_role("a", "sultan")
    with pytest.raises(ValueError):
        store.set_role("yok", "viewer")


def test_password_change_rotates_session_token(store: UserStore) -> None:
    store.create("a", "eski-parola", "pmo")
    before = store.get_with_token("a").token
    assert before  # token is non-empty
    store.set_password("a", "yeni-parola")
    after = store.get_with_token("a").token
    assert before != after  # live sessions carrying `before` are now invalid
    assert store.authenticate("a", "yeni-parola") is not None
    assert store.authenticate("a", "eski-parola") is None


def test_authenticate_returns_matching_token(store: UserStore) -> None:
    store.create("a", "pw-1", "pmo")
    assert store.authenticate("a", "pw-1").token == store.get_with_token("a").token


def test_delete_removes_user_and_grants(store: UserStore) -> None:
    store.create("a", "pw-1", "viewer", projects=["demo", "shop"])
    assert store.projects_for("a") == {"demo", "shop"}
    store.delete("a")
    assert store.get("a") is None
    assert store.get_with_token("a") is None  # a live session dies on next request
    assert store.projects_for("a") == set()
    with pytest.raises(ValueError):
        store.delete("a")
