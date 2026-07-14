"""Cross-encoder reranker evidence layer (v4b): include-side floor, off by default."""

from etki.adapters.fakes.code_repo import FakeCodeRepositoryProvider
from etki.adapters.fakes.document import FakeDocumentSourceProvider
from etki.adapters.fakes.seed import SEED_BASELINE
from etki.adapters.fakes.work_item import FakeWorkItemProvider
from etki.adapters.registry import build_reranker
from etki.config import Settings
from etki.engine.triage import TriageEngine


class _StubReranker:
    """Returns a fixed score for one clause id, a very low score for the rest."""

    def __init__(self, target_id: str, target_score: float) -> None:
        self.target_id = target_id
        self.target_score = target_score
        self.calls = 0

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        self.calls += 1
        included = [
            i for i in SEED_BASELINE.scope_items if i.polarity.value != "EXCLUDED"
        ]
        return [
            self.target_score if i.id == self.target_id else -12.0 for i in included
        ]


class _BoomReranker:
    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        raise RuntimeError("endpoint down")


def _engine(reranker=None) -> TriageEngine:
    return TriageEngine(
        FakeWorkItemProvider([]),
        FakeCodeRepositoryProvider(),
        FakeDocumentSourceProvider(),
        SEED_BASELINE.model_copy(deep=True),
        reranker=reranker,
        rerank_strong=-6.8,
    )


async def test_no_reranker_is_pure_deterministic():
    decision = (await _engine().triage("tamamen alakasız kelimeler qqq www")).decisions[0]
    assert decision.decision.value == "CR_CANDIDATE"  # unchanged fall-through


async def test_strong_rerank_score_floors_to_in_scope():
    rr = _StubReranker("SCOPE-014", target_score=-3.0)  # above -6.8
    decision = (await _engine(rr).triage("tamamen alakasız kelimeler qqq www")).decisions[0]
    assert rr.calls == 1
    assert decision.decision.value == "IN_SCOPE"
    assert "SCOPE-014" in [c.id for c in decision.evidence.cited_clauses]
    assert any("rerank" in a.lower() or "cross-encoder" in a.lower()
               for a in decision.evidence.assumptions)


async def test_below_threshold_changes_nothing():
    rr = _StubReranker("SCOPE-014", target_score=-8.5)  # below -6.8
    decision = (await _engine(rr).triage("tamamen alakasız kelimeler qqq www")).decisions[0]
    assert decision.decision.value == "CR_CANDIDATE"


async def test_not_consulted_on_strong_deterministic_match():
    rr = _StubReranker("SCOPE-014", target_score=-3.0)
    item = SEED_BASELINE.scope_items[0]
    await _engine(rr).triage(item.description)  # exact clause text -> strong lexical
    assert rr.calls == 0


async def test_endpoint_error_degrades_gracefully():
    decision = (
        await _engine(_BoomReranker()).triage("tamamen alakasız kelimeler qqq www")
    ).decisions[0]
    assert decision.decision.value == "CR_CANDIDATE"  # deterministic outcome preserved


def test_registry_returns_none_without_endpoint(monkeypatch):
    monkeypatch.delenv("ETKI_RERANK_BASE_URL", raising=False)
    assert build_reranker(Settings()) is None


# --- v5b: reranker as negative evidence (gray band -> CR) ---


class _LowReranker:
    """Scores every clause far below the floor threshold: 'no clause covers this'."""

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        return [-9.5] * len(documents)


# Shares "aylık rapor" with SCOPE-014 (gray-band lexical overlap) but asks for a
# capability no clause grants — the tokenizer-artifact population of the band.
_ARTIFACT_REQ = "rapor verilerini yapay zeka ile analiz edelim"
# 1-2 token vague ask sharing a word with SCOPE-014 — the legitimate-gray population.
_VAGUE_REQ = "rapor iyileştirme"


async def test_gray_band_without_reranker_stays_gray():
    decision = (await _engine().triage(_ARTIFACT_REQ)).decisions[0]
    assert decision.decision.value == "GRAY_AREA"


async def test_sem_no_cover_demotes_gray_band_to_cr():
    decision = (await _engine(_LowReranker()).triage(_ARTIFACT_REQ)).decisions[0]
    assert decision.decision.value == "CR_CANDIDATE"


async def test_short_vague_requests_keep_their_gray():
    decision = (await _engine(_LowReranker()).triage(_VAGUE_REQ)).decisions[0]
    assert decision.decision.value == "GRAY_AREA"


async def test_interrogative_gray_band_requests_stay_gray():
    # a question in the gray band signals the asker's own uncertainty -> GRAY,
    # even when the cross-encoder finds no covering clause
    decision = (
        await _engine(_LowReranker()).triage("rapor verileri yapay zeka ile analiz edilebilir mi?")
    ).decisions[0]
    assert decision.decision.value == "GRAY_AREA"
