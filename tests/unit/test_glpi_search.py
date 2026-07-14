"""GLPI similar-work search: criteria building is pure and unit-testable."""

from etki.adapters.glpi_work_item import GlpiWorkItemProvider


def test_glpi_search_params_build_or_criteria_over_title_and_content() -> None:
    params = GlpiWorkItemProvider._search_params("raporlara kategori filtre ekle", 5)
    assert params["range"] == "0-4"
    # 3 salient tokens × 2 fields = 6 criteria; first has no link, the rest OR
    assert params["criteria[0][searchtype]"] == "contains"
    assert "criteria[0][link]" not in params
    assert params["criteria[1][link]"] == "OR"
    assert params["criteria[5][link]"] == "OR"
    fields = {params["criteria[0][field]"], params["criteria[1][field]"]}
    assert fields == {"1", "21"}  # title + content
    values = {params[k] for k in params if k.endswith("[value]")}
    assert values == {"raporlara", "kategori", "filtre"}  # top-3 longest tokens win
    assert "ekle" not in values  # shorter word doesn't make the cut


def test_glpi_search_params_short_words_dropped() -> None:
    params = GlpiWorkItemProvider._search_params("db fix ek iş", 3)
    # every word ≤3 chars → no criteria, plain recent listing
    assert not any(k.startswith("criteria") for k in params)
    assert params["range"] == "0-2"
