"""Non-technical user bundle: .docx report + chat agent (without an LLM)."""

from etki.adapters.fakes.code_repo import FakeCodeRepositoryProvider
from etki.adapters.fakes.document import FakeDocumentSourceProvider
from etki.adapters.fakes.seed import SEED_BASELINE
from etki.adapters.fakes.work_item import FakeWorkItemProvider
from etki.engine.triage import TriageEngine
from etki.reporting.docx_report import build_case_report


def _engine(**kw) -> TriageEngine:
    return TriageEngine(
        FakeWorkItemProvider(),
        FakeCodeRepositoryProvider(),
        FakeDocumentSourceProvider(),
        SEED_BASELINE.model_copy(deep=True),
        **kw,
    )


async def test_docx_report_is_valid_document():
    engine = _engine()
    case = await engine.triage("login ekranına SSO entegrasyonu")
    data = build_case_report(case, [])
    assert data[:2] == b"PK"  # .docx = zip signature
    assert len(data) > 1000


async def test_agent_without_llm_returns_config_hint(monkeypatch):
    monkeypatch.delenv("ETKI_LLM_BASE_URL", raising=False)
    from etki.agent import ask

    message = await ask("SSO kapsamda mı?")
    assert "LLM yapılandırılmamış" in message
