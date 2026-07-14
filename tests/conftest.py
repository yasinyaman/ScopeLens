"""Shared pytest fixtures: engine with fake adapters, context with in-memory repo, API client."""

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from etki.adapters.fakes.code_repo import FakeCodeRepositoryProvider
from etki.adapters.fakes.document import FakeDocumentSourceProvider
from etki.adapters.fakes.seed import SEED_BASELINE
from etki.adapters.fakes.work_item import FakeWorkItemProvider
from etki.api.app import app
from etki.api.context import AppContext, get_context
from etki.api.security import current_user
from etki.auth import UserStore
from etki.config import Settings
from etki.core.models import Index
from etki.engine.triage import TriageEngine
from etki.hitl.service import ApprovalService
from etki.indexing.engine import map_scope_to_code
from etki.persistence.db import init_schema, make_session_factory
from etki.persistence.memory_repo import InMemoryCaseFileRepository
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool


def _memory_user_store() -> UserStore:
    """User store on a shared single-connection in-memory SQLite (StaticPool)."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
    )
    init_schema(engine)
    return UserStore(make_session_factory(engine))


@pytest.fixture(autouse=True)
def _hermetic_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests isolated from the local .env AND the UI-managed .etki/llm.json
    (so the developer's real key/settings don't leak in); otherwise the 'LLM off'
    paths would hit the real API and extraction would go nondeterministic."""
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    monkeypatch.setitem(Settings.model_config, "json_file", None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ETKI_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("ETKI_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ETKI_LLM_BASE_URL", raising=False)


@pytest.fixture(autouse=True)
def _isolated_process_log(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The process log appends to the RELATIVE .etki/process-log.jsonl — without
    this, suite runs would pollute the developer's real transcript (ask/index events)."""
    import etki.process_log as process_log

    monkeypatch.setattr(process_log, "_LOG", tmp_path / "process-log.jsonl")


@pytest.fixture
def auth_role() -> dict[str, str]:
    """Session role for test requests; defaults to pmo. RBAC tests set this to 'viewer'."""
    return {"role": "pmo", "username": "test"}


@pytest.fixture
def clause_memory() -> dict:
    """Live clause-memory dict shared by the engine and AppContext (the
    consumed_by_category idiom: refresh_precedents mutates it in place)."""
    return {}


@pytest.fixture
def engine(clause_memory: dict) -> TriageEngine:
    return TriageEngine(
        FakeWorkItemProvider(),
        FakeCodeRepositoryProvider(),
        FakeDocumentSourceProvider(),
        SEED_BASELINE.model_copy(deep=True),
        index_freshness="2026-06-21",
        precedents_by_clause=clause_memory,
    )


@pytest.fixture
def app_context(engine: TriageEngine, clause_memory: dict) -> AppContext:
    repo = InMemoryCaseFileRepository()
    return AppContext(
        engines={"demo": engine},
        consumed={"demo": {}},
        projects=[{"id": "demo", "name": "Demo Proje"}],
        repo=repo,
        approval=ApprovalService(repo),
        default_project="demo",
        user_store=_memory_user_store(),
        precedents={"demo": clause_memory},
    )


@pytest.fixture
def fake_index() -> Index:
    """Index built from the SAME fake corpus as the engine fixture — the UI
    screens that read the persisted index (Özet clause links, madde detayı,
    modül tablosu, Sor/graph query) must not depend on the developer's real
    .etki/index-*.json being on disk (CI has none)."""
    baseline = SEED_BASELINE.model_copy(deep=True)
    modules = asyncio.run(FakeCodeRepositoryProvider().list_modules())
    map_scope_to_code(baseline.scope_items, modules)
    return Index(baseline=baseline, modules=modules, freshness="2026-06-21")


@pytest.fixture
def client(
    app_context: AppContext,
    auth_role: dict[str, str],
    fake_index: Index,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[TestClient]:
    # Hermetic index: every web route resolves the project index through
    # web.load_index — serve the fake-corpus index instead of local disk state.
    monkeypatch.setattr("etki.api.web.load_index", lambda path: fake_index)
    app_context.indexes = {"demo": fake_index}
    # apply_baseline_bump persists the bumped index — give it a scratch target.
    app_context.index_paths = {"demo": str(tmp_path / "index-demo.json")}
    app.dependency_overrides[get_context] = lambda: app_context
    # Override current_user → require_user/require_pmo behave as if reading a verified session
    # (the RBAC logic is genuinely tested; the role comes from the auth_role fixture).
    app.dependency_overrides[current_user] = lambda: {
        "username": auth_role["username"],
        "role": auth_role["role"],
    }
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
