"""PLUGIN FAZ 2 EXIT GATE (three assertions, all in CI):

1. A project configured with `adapter: linear` triages END-TO-END through the
   plugin path (the builtin branch is gone; network is canned).
2. The TRIAGED audit event carries the active plugin set.
3. A broken adapter build does not prevent `get_context()` — the project keeps
   serving with the documented degradation (no effort history / empty docs).
"""

from pathlib import Path

import etki.api.context as context_mod
import pytest
from etki.adapters.fakes.code_repo import FakeCodeRepositoryProvider
from etki.adapters.fakes.document import FakeDocumentSourceProvider
from etki.adapters.fakes.seed import SEED_BASELINE
from etki.adapters.fakes.work_item import FakeWorkItemProvider
from etki.adapters.plugins import get_plugin_registry
from etki.adapters.registry import build_work_items
from etki.config import ConnectorConfig
from etki.engine.triage import TriageEngine
from etki.hitl.service import ApprovalService
from etki.persistence.memory_repo import InMemoryCaseFileRepository

_CANNED_SEARCH = {
    "searchIssues": {
        "nodes": [
            {
                "identifier": "ENG-7",
                "title": "CSV dışa aktarım",
                "description": "raporlama ekranına csv export",
                "estimate": 3,
                "state": {"name": "Done"},
                "labels": {"nodes": [{"name": "raporlama"}]},
            }
        ]
    }
}


async def test_triage_end_to_end_via_plugin_with_audit_stamp(monkeypatch):
    """Gate 1+2: plugin-built provider feeds a real triage; audit carries plugin_set."""
    monkeypatch.setenv("LINEAR_API_KEY", "lk")
    provider = build_work_items(
        ConnectorConfig(
            adapter="linear",
            options={"api_key": "env:LINEAR_API_KEY", "hours_per_point": 4},
        )
    )

    async def canned_graphql(query, variables):
        return _CANNED_SEARCH

    monkeypatch.setattr(provider, "_graphql", canned_graphql)

    stamp = get_plugin_registry().stamp()
    assert any(s.startswith("etki-plugin-linear@") for s in stamp)

    engine = TriageEngine(
        provider,
        FakeCodeRepositoryProvider(),
        FakeDocumentSourceProvider(),
        SEED_BASELINE.model_copy(deep=True),
        plugin_set=stamp,
    )
    case = await engine.triage(
        "Mevcut raporlama ekranına CSV dışa aktarma eklensin", request_id="REQ-PLUGIN-1"
    )
    assert case.decisions, "triyaj plugin sağlayıcısıyla karar üretmeli"
    assert all(d.plugin_set == stamp for d in case.decisions)

    repo = InMemoryCaseFileRepository()
    ApprovalService(repo).record_triage(case)
    (event,) = repo.list_audit("REQ-PLUGIN-1")
    assert event.action == "TRIAGED"
    audited = event.detail["decisions"][0]["plugin_set"]
    assert any(s.startswith("etki-plugin-linear@") for s in audited)


@pytest.fixture
def hermetic_context_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A minimal fake-adapter project so get_context() runs hermetically."""
    connectors = tmp_path / "connectors.yaml"
    connectors.write_text(
        "work_items:\n  adapter: fake\ncode_repo:\n  adapter: fake\ndocuments:\n  adapter: fake\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)  # .etki/ index artifacts land in the sandbox
    monkeypatch.setenv("ETKI_CONNECTORS_PATH", str(connectors))
    monkeypatch.setenv("ETKI_PROJECTS_PATH", str(tmp_path / "projects.yaml"))  # absent → demo
    monkeypatch.setenv("ETKI_DB_URL", f"sqlite:///{tmp_path}/etki.db")
    monkeypatch.setenv("ETKI_WIKI_DIR", "")
    context_mod.get_context.cache_clear()
    yield
    context_mod.get_context.cache_clear()


def test_broken_adapter_degrades_project_not_context(hermetic_context_env, monkeypatch):
    """Gate 3: adapter build failure (e.g. a failed plugin) ≠ project loss.

    First pass builds+persists the index with healthy adapters (an indexing-time
    failure is the EXISTING whole-project skip); then the serving adapters break
    — the engine must come up on the documented fallbacks instead."""
    ctx = context_mod.get_context()
    assert "demo" in ctx.engines  # index now persisted under tmp .etki/
    assert ctx.degraded_adapters("demo") == []  # healthy build → no badge
    context_mod.get_context.cache_clear()

    def boom(cfg):
        raise RuntimeError("plugin kurulumu patladı")

    monkeypatch.setattr(context_mod, "build_work_items", boom)
    monkeypatch.setattr(context_mod, "build_documents", boom)

    ctx = context_mod.get_context()

    assert "demo" in ctx.engines, "proje adaptör hatasına rağmen servis etmeli"
    assert isinstance(ctx.work_item_providers["demo"], FakeWorkItemProvider)
    assert ctx.consumed["demo"] == {}  # no effort history → pool tracking empty
    # The fallback is RECORDED, not silent: both ports degraded, error preserved
    # (this is what the project screens' warning badges render).
    degraded = {h.port: h for h in ctx.degraded_adapters("demo")}
    assert set(degraded) == {"work_items", "documents"}
    assert "RuntimeError" in (degraded["work_items"].error or "")

def test_runtime_workitem_failure_flips_the_health_badge(
    hermetic_context_env, monkeypatch
):
    """W2: a provider that builds fine but fails AT TRIAGE TIME (expired token,
    401 mid-poll) must degrade AdapterHealth — the badge used to stay green
    while every triage silently lost its effort history."""

    class _ExpiredToken:
        def capabilities(self):  # noqa: ANN202 — provider double
            from etki.core.ports import Capabilities

            return Capabilities()

        async def find_similar(self, description, *, limit=5):  # noqa: ANN001
            raise RuntimeError("401 Unauthorized")

        async def get_work_item(self, item_id):  # noqa: ANN001
            raise RuntimeError("401 Unauthorized")

    ctx = context_mod.get_context()  # healthy pass persists the index (gate-3 pattern)
    assert "demo" in ctx.engines
    context_mod.get_context.cache_clear()
    monkeypatch.setattr(context_mod, "build_work_items", lambda cfg: _ExpiredToken())
    ctx = context_mod.get_context()
    assert ctx.degraded_adapters("demo") == []  # build succeeded → green

    import asyncio

    case = asyncio.run(ctx.engines["demo"].triage("rapora yeni filtre eklensin"))
    assert case.decisions  # triage still succeeds (graceful degradation)
    (health,) = ctx.degraded_adapters("demo")
    assert health.port == "work_items"
    assert "401" in (health.error or "")
