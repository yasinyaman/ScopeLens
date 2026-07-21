"""Text matching: Turkish<->English domain-term bridge + inflection tolerance."""

from etki.core.text import score, tokenize


def test_turkish_english_bridge():
    # TR request <-> EN spec/code reduce to the same canonical form -> they match
    assert "database" in tokenize("Oracle veritabanı desteği")
    assert "support" in tokenize("Oracle veritabanı desteği")
    tr = tokenize("veritabanı desteği")
    en = tokenize("database support")
    assert score(tr, en) >= 0.5  # used to be 0 (cross-language never matched)


def test_turkish_inflections_normalize():
    # inflectional suffixes reduce to the same canon (veritabanı/veritabanına/veritabanları)
    assert "database" in tokenize("veritabanına")
    assert "database" in tokenize("veritabanları")
    assert "report" in tokenize("raporlama") and "report" in tokenize("rapora")


def test_same_language_match_preserved():
    # Turkish-Turkish matching must not regress (both sides reduce to the same canon)
    assert score(tokenize("rapora filtre ekle"), tokenize("rapor filtreleme")) > 0.5


def test_short_query_score_is_capped():
    # B2: a 1-2 token request no longer inflates to 1.0 against a long clause (cap 0.6).
    query = tokenize("rapor filtresi")
    target = tokenize(
        "Aylık olarak en fazla beş standart rapor üretimi kapsam içindedir; raporlara "
        "tarih ve kategori filtreleri eklenmesi de kapsam dahilindedir"
    )
    assert len(query) < 3
    assert score(query, target) <= 0.6


def test_symmetric_component_penalizes_long_targets():
    # B2: the same query should score higher against a short target than a long one
    # (the old asymmetric score gave both a 1.0).
    query = tokenize("rapor tarih filtresi eklensin")
    short_target = tokenize("rapor tarih filtresi")
    long_target = tokenize(
        "rapor tarih filtresi ve ayrıca kategori bazlı gruplama sayfalama "
        "dışa aktarma yetkilendirme loglama arşivleme bileşenleri"
    )
    assert score(query, short_target) > score(query, long_target) > 0


def test_azure_products_are_not_identity_providers():
    # ("azure","idp") is gone: an Azure DevOps request must not canonicalize to
    # the IdP concept, while the real identity brands still do.
    assert "idp" not in tokenize("Azure DevOps pipeline integration")
    assert "idp" in tokenize("Okta login")
    assert "idp" in tokenize("Entra ID login")
