"""Decision wiki (Faz 1 GraphRAG memory): file projection, search, rebuild guarantee.

The wiki is a PROJECTION of the DB — the tests assert exactly that: the same cases
always regenerate the same files, a wiki failure never breaks triage, and the
PMO decision re-sync keeps the files honest.
"""

from datetime import UTC, datetime

import pytest
from etki.adapters.filesystem_wiki import FileSystemWikiAdapter
from etki.core.enums import Decision, PmoDecision
from etki.core.models import (
    CaseFile,
    EffortEstimate,
    EvidenceChain,
    ScopeItem,
    TriageDecision,
)
from etki.hitl.service import ApprovalService
from etki.persistence.memory_repo import InMemoryCaseFileRepository


def _case(request_id: str = "REQ-demo-abc123", text: str = "SSO entegrasyonu") -> CaseFile:
    return CaseFile(
        request_id=request_id,
        project_id="demo",
        raw_request=text,
        decisions=[
            TriageDecision(
                request_id=request_id,
                decision=Decision.CR_CANDIDATE,
                confidence=0.66,
                evidence=EvidenceChain(
                    reasoning="Sözleşmede birebir karşılığı yok; kimlik doğrulama maddesine yakın.",
                    contract_clauses_cited=["Madde 7.1"],
                    impacted_modules=["auth"],
                    cited_clauses=[
                        ScopeItem(
                            id="S1",
                            contract_id="C-2026-01",
                            description="Kullanıcı kimlik doğrulama ve oturum yönetimi",
                            source_clause="Madde 7.1",
                        )
                    ],
                    assumptions=["Benzer geçmiş kayıt bulunamadı"],
                ),
                effort_estimate=EffortEstimate(low=12, high=18, basis="3 modül, PERT"),
            )
        ],
        created_at=datetime(2026, 7, 9, 10, 0, tzinfo=UTC),
    )


@pytest.fixture
def wiki(tmp_path) -> FileSystemWikiAdapter:
    return FileSystemWikiAdapter(str(tmp_path / "wiki-{id}"))


def test_write_decision_projects_case_to_markdown(wiki, tmp_path):
    doc_id = wiki.write_decision(_case())
    assert doc_id == "DEC-20260709-req-demo-abc123"
    content = wiki.read_decision("demo", doc_id)
    assert content is not None
    assert content.startswith("---\n")  # YAML frontmatter
    assert "case_id: REQ-demo-abc123" in content
    assert "CR_CANDIDATE" in content
    assert "Madde 7.1" in content and "kimlik doğrulama maddesine yakın" in content
    assert "12–18 hour" in content  # range, never a single number


def test_index_and_entity_pages_regenerate_on_write(wiki, tmp_path):
    wiki.write_decision(_case())
    index = (tmp_path / "wiki-demo" / "index.md").read_text(encoding="utf-8")
    assert "Toplam karar dosyası: **1**" in index
    assert "CR_CANDIDATE: 1" in index
    module_page = wiki.get_entity_page("demo", "modules", "auth")
    assert module_page is not None and "DEC-20260709-req-demo-abc123" in module_page
    contract_page = wiki.get_entity_page("demo", "contracts", "C-2026-01")
    assert contract_page is not None and "DEC-20260709" in contract_page


def test_rewrite_after_pmo_decision_updates_projection(wiki):
    case = _case()
    wiki.write_decision(case)
    case.status = PmoDecision.CONVERT_TO_CR
    case.decisions[0].human_decision = PmoDecision.CONVERT_TO_CR
    doc_id = wiki.write_decision(case)  # idempotent overwrite
    content = wiki.read_decision("demo", doc_id)
    assert content is not None
    assert "status: CONVERT_TO_CR" in content
    assert "**PMO kararı:** CONVERT_TO_CR" in content


def test_rebuild_regenerates_identical_files(wiki, tmp_path):
    cases = [_case(), _case("REQ-demo-def456", "raporlara excel dışa aktarım")]
    for c in cases:
        wiki.write_decision(c)
    root = tmp_path / "wiki-demo"
    snapshot = {p.relative_to(root): p.read_text(encoding="utf-8") for p in root.rglob("*.md")}

    count = wiki.rebuild("demo", cases)  # wipes + regenerates from the "DB"
    regenerated = {p.relative_to(root): p.read_text(encoding="utf-8") for p in root.rglob("*.md")}
    assert count == 2
    assert regenerated == snapshot  # projection guarantee: bit-identical content


def test_rebuild_skips_other_projects_cases(wiki):
    other = _case("REQ-shop-xyz789")
    other.project_id = "shop"
    assert wiki.rebuild("demo", [_case(), other]) == 1


def test_search_requires_all_tokens(wiki):
    wiki.write_decision(_case())
    wiki.write_decision(_case("REQ-demo-def456", "raporlara excel dışa aktarım"))
    hits = wiki.search("demo", "SSO entegrasyonu")
    assert [h.doc_id for h in hits] == ["DEC-20260709-req-demo-abc123"]
    assert hits[0].snippet
    assert wiki.search("demo", "SSO excel") == []  # AND semantics: no file has both
    assert wiki.search("demo", "") == []


def test_search_on_missing_project_is_empty(wiki):
    assert wiki.search("yok-boyle-proje", "sso") == []


def test_search_matches_inflected_tokens(wiki):
    wiki.write_decision(_case("REQ-demo-pay1", "ödeme sağlayıcı entegrasyonu yapılacak"))
    hits = wiki.search("demo", "ödemeler sağlayıcılar")  # inflected forms
    assert [h.doc_id for h in hits] == ["DEC-20260709-req-demo-pay1"]


def test_search_ignores_stopword_only_query(wiki):
    wiki.write_decision(_case())
    assert wiki.search("demo", "ile ve bu") == []


def test_search_without_rg_falls_back_to_python_scan(wiki, monkeypatch):
    wiki.write_decision(_case())
    monkeypatch.setattr("etki.adapters.filesystem_wiki.shutil.which", lambda _: None)
    hits = wiki.search("demo", "SSO entegrasyonu")
    assert hits and hits[0].doc_id == "DEC-20260709-req-demo-abc123"


def test_list_decisions_returns_metas(wiki):
    wiki.write_decision(_case())
    metas = wiki.list_decisions("demo")
    assert len(metas) == 1 and metas[0]["case_id"] == "REQ-demo-abc123"


def test_project_language_localizes_headings(tmp_path):
    wiki = FileSystemWikiAdapter(str(tmp_path / "wiki-{id}"), languages={"shop": "en"})
    case = _case("REQ-shop-en1")
    case.project_id = "shop"
    doc_id = wiki.write_decision(case)
    content = wiki.read_decision("shop", doc_id)
    assert content is not None
    assert "## Request" in content and "Decision 1 —" in content  # EN headings
    # Default (unmapped) projects keep the Turkish headings byte-identically.
    tr_doc = wiki.write_decision(_case())
    tr_content = wiki.read_decision("demo", tr_doc)
    assert tr_content is not None and "## Talep" in tr_content


def test_record_triage_writes_wiki_and_decide_resyncs(wiki):
    repo = InMemoryCaseFileRepository()
    service = ApprovalService(repo, wiki=wiki)
    case = _case()
    service.record_triage(case)
    assert wiki.read_decision("demo", "DEC-20260709-req-demo-abc123") is not None

    from etki.core.models import Baseline

    service.decide(
        case.request_id, 0, PmoDecision.APPROVE, actor="pmo",
        current_baseline=Baseline(contract_id="C-2026-01"),
    )
    content = wiki.read_decision("demo", "DEC-20260709-req-demo-abc123")
    assert content is not None and "**PMO kararı:** APPROVE" in content


def test_wiki_failure_never_breaks_triage():
    class ExplodingWiki:
        def write_decision(self, case):  # noqa: ANN001
            raise OSError("disk dolu")

    repo = InMemoryCaseFileRepository()
    service = ApprovalService(repo, wiki=ExplodingWiki())  # type: ignore[arg-type]
    case = _case()
    service.record_triage(case)  # must not raise
    assert repo.get_case(case.request_id) is not None  # DB record is safe
