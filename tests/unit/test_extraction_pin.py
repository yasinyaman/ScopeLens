"""Characterization pin: the four samples contracts must keep extracting EXACTLY
these values through the W3 extraction-safety round (and any future change).

The samples corpora anchor every benchmark baseline (golden, EtkiBench, dev
sets) — a silent extraction shift here would move all of them at once. Values
recorded from the shipped extractor on 2026-07-23 (before the W3 fixes)."""

import asyncio
from pathlib import Path

import pytest
from etki.extraction.scope_extractor import HeuristicScopeExtractor

_PIN = {
    "demo_project": {
        "n": 9,
        "polarity": "IIIIIEEEI",
        "limits": [(3, None), (5, "monthly"), (2, None)],
        "pools": [("SCOPE-002", 40.0), ("SCOPE-005", 24.0)],
    },
    "demo_project_en": {
        "n": 9,
        "polarity": "IIIIIEEEI",
        "limits": [(3, None), (5, "monthly"), (2, None)],
        "pools": [("SCOPE-002", 40.0), ("SCOPE-005", 24.0)],
    },
    "demo_shop_en": {
        "n": 6,
        "polarity": "IIIEEI",
        "limits": [(3, None)],
        "pools": [("SCOPE-002", 30.0)],
    },
    "demo_project_b": {
        "n": 6,
        "polarity": "IIIEEI",
        "limits": [(3, None)],
        "pools": [("SCOPE-002", 30.0)],
    },
}


@pytest.mark.parametrize("corpus", sorted(_PIN))
def test_samples_contract_extraction_is_pinned(corpus: str) -> None:
    text = Path(f"samples/{corpus}/contract.md").read_text(encoding="utf-8")
    items = asyncio.run(HeuristicScopeExtractor().extract("C", text))
    expected = _PIN[corpus]
    assert len(items) == expected["n"]
    assert "".join(
        "E" if i.polarity.value == "EXCLUDED" else "I" for i in items
    ) == expected["polarity"]
    assert [
        (i.limits.quantity, i.limits.period) for i in items if i.limits.quantity
    ] == expected["limits"]
    assert [
        (i.id, i.effort_pool_hours) for i in items if i.effort_pool_hours
    ] == expected["pools"]
