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


def test_saglan_boilerplate_is_stopped_but_saglayici_survives():
    # TR mirror of the stopped EN provide/provides/provided: inflected sağlamak
    # forms are boilerplate (and prefix-collide with sağlayıcı), so they are
    # stopped; "sağlayıcı" (provider) is a real content word and must survive.
    assert tokenize("bildirim gönderimi sağlanır") == tokenize("bildirim gönderimi")
    assert "sağlayıcı" in tokenize("üçüncü taraf kimlik sağlayıcı entegrasyonu")


def test_desteklen_verb_forms_are_stopped_but_destek_noun_bridges():
    # "X desteklenir" is clause boilerplate (EN twin "supported" is stopped);
    # the noun (veritabanı desteği = database support) is a deliverable and
    # must keep bridging to the canonical "support".
    assert "support" not in tokenize("PDF dışa aktarım desteklenir")
    assert "support" in tokenize("veritabanı desteği")


def test_ascii_typed_turkish_stopwords_are_stopped_too():
    # The same sentence must tokenize identically however it was typed:
    # diacritic-proper and ASCII spellings fold to the same stop lookup.
    assert tokenize("rapor filtresi lazim") == tokenize("rapor filtresi lazım")
    assert tokenize("sozlesme kapsami dahilindedir rapor") == tokenize(
        "sözleşme kapsamı dahilindedir rapor"
    )
    # Folding is lookup-only: ASCII content words still bridge via the lexicon.
    assert "driver" in tokenize("yazici surucu guncellemesi")


def test_short_query_cap_uses_surface_count_not_canon_count():
    from etki.core.text import surface_token_count

    # Three content words collapse to two canonical tokens (okta+auth0 → idp) —
    # the surface count is what says this was NOT a two-word request.
    text = "Okta ve Auth0 entegrasyonu"
    q = tokenize(text)
    assert len(q) < 3 <= surface_token_count(text)
    target = tokenize("IdP entegrasyonu sağlanacaktır")  # short clause: raw score 1.0
    assert score(q, target) == 0.6  # canon count 2 → capped as a "short" query
    assert score(q, target, query_size=surface_token_count(text)) == 1.0  # not short


def test_connect_bridges_to_integration():
    # "Connect X to Y" requests describe integrations; the bridge lets them
    # reach the integration clause (kept by measurement: v0 45→46, no set down).
    assert "integration" in tokenize("Connect the CRM to the warehouse system")
