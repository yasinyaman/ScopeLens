"""Per-project LLM profile: domain registry + preamble + engine/agent integration."""

from typing import Any

import pytest
from etki.adapters.fakes.code_repo import FakeCodeRepositoryProvider
from etki.adapters.fakes.document import FakeDocumentSourceProvider
from etki.adapters.fakes.seed import SEED_BASELINE
from etki.adapters.fakes.work_item import FakeWorkItemProvider
from etki.agent import _build_system
from etki.domains import list_domain_profiles, load_domain_profile
from etki.engine.triage import TriageEngine
from etki.llm_profile import build_system_preamble


def test_domain_profiles_listed_and_loaded() -> None:
    ids = {d["id"] for d in list_domain_profiles()}
    assert "entegrasyon" in ids  # seeded by config/domains/entegrasyon.md
    text = load_domain_profile("entegrasyon")
    assert text and "Entegrasyon" in text


def test_load_domain_profile_rejects_traversal() -> None:
    assert load_domain_profile("../config") is None
    assert load_domain_profile("yok") is None
    assert load_domain_profile(None) is None


def test_build_system_preamble_combines() -> None:
    p = build_system_preamble("en", "entegrasyon", "extra context")
    assert "[DOMAIN CONTEXT]" in p and "Entegrasyon" in p
    assert "[PROJECT INSTRUCTIONS]" in p and "extra context" in p
    assert "'en'" in p  # language directive
    # no domain: language directive only
    bare = build_system_preamble("de")
    assert "DOMAIN CONTEXT" not in bare and "'de'" in bare


def test_agent_build_system_prepends_extra_and_lang() -> None:
    s = _build_system("DOMAIN-PREAMBLE", "fr")
    assert s.startswith("DOMAIN-PREAMBLE")
    assert "Etki" in s and "'fr'" in s


class _RecordingLLM:
    """A fake LLMClient that records the system prompt."""

    def __init__(self) -> None:
        self.last_system: str | None = None

    async def complete_json(self, *, system: str, user: str) -> dict[str, Any]:
        self.last_system = system
        return {"scope_item_id": None, "impacted_modules": [], "rationale": "test"}

    def capabilities(self) -> Any:  # pragma: no cover - required by the protocol
        from etki.core.ports import Capabilities

        return Capabilities()


@pytest.mark.asyncio
async def test_engine_llm_match_uses_preamble_and_language() -> None:
    llm = _RecordingLLM()
    engine = TriageEngine(
        FakeWorkItemProvider(),
        FakeCodeRepositoryProvider(),
        FakeDocumentSourceProvider(),
        SEED_BASELINE.model_copy(deep=True),
        llm_client=llm,  # type: ignore[arg-type]
        language="en",
        system_preamble="[DOMAIN CONTEXT]\nTEST-DOMAIN",
    )
    await engine._llm_match("some request", None, 0.0, [])
    assert llm.last_system is not None
    assert "TEST-DOMAIN" in llm.last_system  # domain prefix was appended to the system prompt
    assert "en" in llm.last_system  # rationale language directive
