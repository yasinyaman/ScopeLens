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


def test_direction_pair_takes_the_target_number():
    # "from X to Y" family: the requested amount is the TARGET, not the first
    # digit (the M3-09 miss) and not the max of the two (decrease case).
    assert split_request("Raise concurrent sessions per user from 3 to 10")[0].quantity == 10
    assert split_request("Reduce concurrent sessions per user from 6 to 2")[0].quantity == 2
    assert split_request("Aylık rapor sayısı 5'ten 8'e çıkarılsın")[0].quantity == 8
    assert split_request("Oturum sınırı 3’ten 10’a yükseltilsin")[0].quantity == 10  # curly '
    assert split_request("Rapor limiti 5ten 8e cikarilsin")[0].quantity == 8  # no apostrophe
    assert split_request("Oturum sınırı 3'ten 6'ya çıksın")[0].quantity == 6  # buffer -ya
    assert split_request("Rapor sayısını 8'den 4'e düşürelim")[0].quantity == 4


def test_yerine_pair_takes_the_second_number():
    assert split_request("Aylık rapor sayısı 5 yerine 12 olsun")[0].quantity == 12


def test_locative_and_genitive_digits_are_not_pairs():
    # "10'da"/"10'un" must not match the dative side of the pair regex;
    # the plain first-digit rule stays in charge.
    assert split_request("3 rapor 10'da bir kontrol edilsin")[0].quantity == 3


def test_llm_splitter_clears_quantity_for_dependency_items():
    # The LLM-splitter path mirrors split_request: a version number is not a
    # quantity ("Spring Boot 3" must not trip the quota step as "3 items").
    import asyncio

    from etki.engine.understanding import LLMRequestSplitter

    class FakeLLM:
        async def complete_json(self, system: str, user: str) -> dict:
            return {"items": [{"item": "spring boot 3 sürümüne yükseltilsin"}]}

    sub = asyncio.run(LLMRequestSplitter(FakeLLM()).split("yükseltme"))[0]
    assert sub.type is RequestType.DEPENDENCY_CHANGE
    assert sub.quantity is None
