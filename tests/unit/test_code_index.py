from pathlib import Path

from etki.adapters.code_index import CodeIndex, impacted_modules, parse_code_index

# Real Joern output fixture — proves the parser correctly handles the Joern schema.
FIXTURE = Path(__file__).parent.parent / "fixtures" / "joern_code_index.json"


def _modules():
    return parse_code_index(CodeIndex.model_validate_json(FIXTURE.read_text(encoding="utf-8")))


def test_parse_joern_output_builds_dependency_graph():
    mods = {m.id: m for m in _modules()}
    assert set(mods) == {"api_gateway", "auth", "config", "db", "reporting"}
    assert set(mods["auth"].depends_on) == {"config", "db"}
    assert set(mods["auth"].depended_by) == {"api_gateway", "reporting"}
    assert set(mods["reporting"].depends_on) == {"auth", "db"}


def test_complexity_metrics_populated():
    auth = next(m for m in _modules() if m.id == "auth")
    assert auth.complexity.loc > 0
    assert auth.complexity.files >= 1


def test_impacted_spreads_to_neighbors():
    impacted = {m.id for m in impacted_modules(_modules(), "auth")}
    assert "auth" in impacted
    assert len(impacted) >= 2


def test_impacted_empty_hint_returns_empty():
    assert impacted_modules(_modules(), None) == []
