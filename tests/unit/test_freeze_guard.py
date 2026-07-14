"""Answer-key freeze guard: engine changes and dataset edits must not mix."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from freeze_guard import classify, violation  # noqa: E402


def test_engine_plus_dataset_is_a_violation():
    msg = violation(
        ["etki/engine/triage.py", "eval/datasets/frozen/golden_crs.json"]
    )
    assert msg is not None and "FREEZE VIOLATION" in msg


def test_engine_only_is_clean():
    assert violation(["etki/engine/triage.py", "tests/unit/test_engine.py"]) is None


def test_dataset_only_is_clean():
    assert violation(["eval/datasets/etkibench/etkibench_v0.json"]) is None


def test_text_and_extraction_count_as_engine():
    engine, datasets = classify(
        [
            "etki/core/text.py",
            "etki/extraction/scope_extractor.py",
            "eval/datasets/backtest_crs.json",
        ]
    )
    assert len(engine) == 2 and len(datasets) == 1


def test_unrelated_files_are_clean():
    assert violation(["README.md", "etki/api/web.py", "docs/MCP.md"]) is None


def test_dataset_readme_is_documentation_not_answer_key():
    # Scoreboard/docs inside eval/datasets/ may change alongside engine work.
    assert violation(
        ["etki/engine/triage.py", "eval/datasets/etkibench/README.md"]
    ) is None
