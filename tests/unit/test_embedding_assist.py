"""Embedding-based semantic matching: deterministic assist symmetric to the LLM one.

Tested with a fake EmbeddingProvider — no endpoint needed. The fake maps known
phrases to fixed unit vectors so cosine similarities are exact and predictable.
"""

from etki.adapters.fakes.code_repo import FakeCodeRepositoryProvider
from etki.adapters.fakes.document import FakeDocumentSourceProvider
from etki.adapters.fakes.seed import SEED_BASELINE
from etki.adapters.fakes.work_item import FakeWorkItemProvider
from etki.engine.triage import TriageEngine

# SEED_BASELINE: SCOPE-014 reporting (INCLUDED), SCOPE-007 auth (INCLUDED),
# SCOPE-022 SSO/IdP (EXCLUDED) — vectors chosen so cosine hits the intended item.
_AXES = {"reporting": [1.0, 0.0, 0.0], "auth": [0.0, 1.0, 0.0], "sso": [0.0, 0.0, 1.0]}


class _FakeEmbedder:
    """Maps texts to axis vectors by keyword; unknown text → a diagonal (low cosine
    to every axis: ~0.577)."""

    def __init__(self) -> None:
        self.calls = 0

    async def embed(self, texts: list[str], *, kind: str = "document") -> list[list[float]]:
        self.calls += 1
        out: list[list[float]] = []
        for text in texts:
            low = text.lower()
            if "sso" in low or "kimlik sağlayıcı" in low or "single sign" in low:
                out.append(_AXES["sso"])
            elif "rapor" in low or "report" in low or "monthly numbers" in low:
                out.append(_AXES["reporting"])
            elif "oturum" in low or "giriş" in low or "session" in low:
                out.append(_AXES["auth"])
            else:
                n = 3 ** -0.5
                out.append([n, n, n])
        return out


class _FailingEmbedder:
    async def embed(self, texts: list[str], *, kind: str = "document") -> list[list[float]]:
        raise RuntimeError("endpoint down")


def _engine(embedder=None, strong: float = 0.75, weak: float = 0.62) -> TriageEngine:
    return TriageEngine(
        FakeWorkItemProvider([]),
        FakeCodeRepositoryProvider(),
        FakeDocumentSourceProvider(),
        SEED_BASELINE.model_copy(deep=True),
        embedder=embedder,
        embed_strong=strong,
        embed_weak=weak,
    )


async def test_no_embedder_keeps_pure_lexical_behavior():
    decision = (await _engine(None).triage("tamamen alakasız kelimeler qqq www")).decisions[0]
    assert decision.decision.value == "CR_CANDIDATE"
    assert not any("embedding" in a.lower() for a in decision.evidence.assumptions)


async def test_semantic_include_annotates_but_never_changes_the_decision():
    # DELIBERATE asymmetry: cosine cannot tell "paraphrase of a clause (IN)" from
    # "new capability near a clause (CR)" — the include side only records an
    # informational evidence note; the decision stays lexical.
    embedder = _FakeEmbedder()
    decision = (
        await _engine(embedder).triage("managers download the monthly numbers qqq")
    ).decisions[0]
    assert decision.decision.value == "CR_CANDIDATE"  # lexical outcome, unchanged
    assert any("kosinüs" in a or "cosine" in a for a in decision.evidence.assumptions)


async def test_strong_semantic_exclude_routes_out_of_scope():
    embedder = _FakeEmbedder()
    decision = (
        await _engine(embedder).triage("single sign on everywhere qqq zzz")
    ).decisions[0]
    assert decision.decision.value == "OUT_OF_SCOPE"
    assert "SCOPE-022" in [c.id for c in decision.evidence.cited_clauses]


async def test_below_weak_threshold_changes_nothing():
    # unknown text embeds to the diagonal → cosine ≈ 0.577 < weak (0.62) → untouched
    embedder = _FakeEmbedder()
    decision = (
        await _engine(embedder).triage("tamamen alakasız kelimeler qqq www")
    ).decisions[0]
    assert decision.decision.value == "CR_CANDIDATE"


async def test_endpoint_failure_degrades_to_lexical():
    decision = (
        await _engine(_FailingEmbedder()).triage("tamamen alakasız kelimeler qqq www")
    ).decisions[0]
    assert decision.decision.value == "CR_CANDIDATE"  # lexical outcome, no crash


async def test_item_vectors_are_cached_across_triages():
    embedder = _FakeEmbedder()
    engine = _engine(embedder)
    await engine.triage("managers download the monthly numbers qqq")
    calls_after_first = embedder.calls  # 1 batch (items) + 1 query
    await engine.triage("another unrelated request zzz")
    # second triage adds only ONE query call — item vectors come from the cache
    assert embedder.calls == calls_after_first + 1