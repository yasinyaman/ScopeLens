from etki.core.enums import RequestType
from etki.domains import load_module_hints
from etki.engine.understanding import guess_module, guess_type, split_request


def test_splits_on_conjunctions():
    subs = split_request("rapora filtre eklensin, ayrıca SSO entegrasyonu yapılsın")
    assert len(subs) == 2


def test_extracts_quantity_and_period():
    sub = split_request("ayda 8 farklı rapor üretilsin")[0]
    assert sub.quantity == 8
    assert sub.period == "monthly"


def test_detects_maintenance_type():
    sub = split_request("üretimdeki hata acilen düzeltilsin")[0]
    assert sub.type is RequestType.MAINTENANCE


def test_english_defect_vocabulary_classifies_as_maintenance():
    for text in (
        "The monthly report page crashes with a 500 error",
        "The Excel export produces a corrupt file",
        "The login button does nothing since the last deployment",
        "Users get logged out randomly — session broken",
    ):
        assert guess_type(text) is RequestType.MAINTENANCE, text


def test_plain_feature_requests_stay_non_maintenance():
    assert guess_type("Add a date filter to the monthly report") is not RequestType.MAINTENANCE


def test_module_hint_for_auth_keywords():
    sub = split_request("kullanıcı parola sıfırlama eklensin")[0]
    assert sub.module_hint == "auth"


def test_guess_module_without_hints_returns_none():
    """B1: no module guess for a project without hints (falls back to the LLM/similarity
    path)."""
    assert guess_module("sepete kripto ödeme eklensin", {}) is None


def test_domain_hints_are_config_driven_not_hardcoded():
    """B1: the e-commerce vocabulary is NOT in the core — the generic hints have no
    'sepet' (cart); it matches once the e-commerce profile
    (config/domains/eticaret.hints.yaml) is loaded."""
    assert guess_module("sepete iade eklensin") is None  # no cart in the generic hints
    hints = load_module_hints("eticaret")
    assert guess_module("sepete iade eklensin", hints) == "cart"
    assert guess_module("kripto ödeme", hints) == "payment"


# --- v5a: word-number quantities ---

from etki.engine.understanding import _quantity  # noqa: E402


def test_english_cardinal_and_ordinal_words():
    assert _quantity("Six standard reports every month") == 6
    assert _quantity("Add a fourth payment provider") == 4


def test_turkish_cardinal_and_ordinal_words():
    assert _quantity("ayda altı standart rapor") == 6
    assert _quantity("dördüncü ödeme sağlayıcısını ekleyelim") == 4


def test_digits_win_over_words():
    assert _quantity("3 of the six reports") == 3


def test_ambiguous_words_are_excluded():
    assert _quantity("show reports on the dashboard") is None  # EN "on" != TR 10
    assert _quantity("bir rapor ekleyelim") is None  # TR article, not a quantity
