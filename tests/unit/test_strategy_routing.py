"""Strategy-routing answer key: choose_strategy vs the pre-committed dataset.

The routing rules are plain keyword heuristics (v1); this pins them against a
labeled set so a rule change that silently reroutes queries fails loudly.
"""

import json
from pathlib import Path

import pytest
from etki.graphquery import choose_strategy

_DATASET = Path(__file__).parents[2] / "eval" / "datasets" / "strategy_routing.json"
_ROWS = json.loads(_DATASET.read_text(encoding="utf-8"))


@pytest.mark.parametrize("row", _ROWS, ids=[r["question"][:40] for r in _ROWS])
def test_choose_strategy_matches_answer_key(row):
    assert choose_strategy(row["question"]) == row["expected_strategy"]
