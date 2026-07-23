from etki.core.enums import Polarity
from etki.extraction.scope_extractor import HeuristicScopeExtractor

CONTRACT = """
## Madde 4.2.1 — Raporlama
Aylık olarak en fazla 5 rapor üretimi kapsam içindedir. Raporlara filtre eklenmesi de dahildir.

## Madde 7.1 — Hariç Tutulanlar (Kapsam Dışı)
- SSO entegrasyonu kapsam dışıdır.
- Mobil uygulama dahil değildir.
"""


async def test_extracts_included_clause_with_limit():
    items = await HeuristicScopeExtractor().extract("C1", CONTRACT)
    reporting = next(i for i in items if i.source_clause == "Madde 4.2.1")
    assert reporting.polarity is Polarity.INCLUDED
    assert reporting.category == "reporting"
    assert reporting.limits.quantity == 5
    assert reporting.limits.period == "monthly"


async def test_excluded_bullets_each_become_excluded_item():
    items = await HeuristicScopeExtractor().extract("C1", CONTRACT)
    excluded = [i for i in items if i.polarity is Polarity.EXCLUDED]
    assert len(excluded) == 2
    assert any("sso" in i.description.lower() for i in excluded)


async def test_clause_keyword_survives_in_description():
    # 'filtre' must remain in the description (must not be truncated to the first
    # sentence) — critical for retrieval.
    items = await HeuristicScopeExtractor().extract("C1", CONTRACT)
    reporting = next(i for i in items if i.source_clause == "Madde 4.2.1")
    assert "filtre" in reporting.description.lower()


# English contract (same patterns as samples/demo_project_en).
CONTRACT_EN = """
## Clause 4.2.1 — Reporting
Up to 5 standard reports per month are in scope, including date and category filters.
This item has an effort pool of 40 hours.

## Clause 3.1 — User Authentication
Local username/password authentication with at most 3 concurrent sessions.

## Clause 7.1 — Exclusions (Out of Scope)
- Single sign-on (SSO) and third-party identity provider (SAML/OAuth) integration is out of scope.
- Mobile application development is not included in this agreement.
"""


async def test_english_headings_split_into_sections():
    items = await HeuristicScopeExtractor().extract("C2", CONTRACT_EN)
    assert {i.source_clause for i in items} == {"Clause 4.2.1", "Clause 3.1", "Clause 7.1"}


async def test_english_limits_pool_and_period():
    items = await HeuristicScopeExtractor().extract("C2", CONTRACT_EN)
    reporting = next(i for i in items if i.source_clause == "Clause 4.2.1")
    assert reporting.polarity is Polarity.INCLUDED
    assert reporting.category == "reporting"
    assert reporting.limits.quantity == 5
    assert reporting.limits.period == "monthly"
    assert reporting.effort_pool_hours == 40.0
    auth = next(i for i in items if i.source_clause == "Clause 3.1")
    assert auth.category == "auth"
    assert auth.limits.quantity == 3


async def test_capability_language_does_not_steal_category():
    # "... is supported" / "... desteklenir" is capability language, not maintenance:
    # a payment clause must keep category=payment (the effort-pool check keys
    # consumption by category — a mislabel silently disables it).
    contract = """
## Clause 2.2 — Payments
Accepting payments by credit card is in scope. At most 3 payment providers
is supported. This item has an effort pool of 30 hours.

## Madde 2.2 — Ödeme
Kredi kartı ile ödeme alma kapsam içindedir. En fazla 3 ödeme sağlayıcı
entegrasyonu desteklenir.

## Clause 7.1 — Maintenance
Bug-fix maintenance is in scope for 12 months after delivery.
"""
    items = await HeuristicScopeExtractor().extract("C3", contract)
    by_clause = {i.source_clause: i for i in items}
    assert by_clause["Clause 2.2"].category == "payment"
    assert by_clause["Madde 2.2"].category == "payment"
    assert by_clause["Clause 7.1"].category == "maintenance"


async def test_english_exclusions_are_excluded():
    items = await HeuristicScopeExtractor().extract("C2", CONTRACT_EN)
    excluded = [i for i in items if i.polarity is Polarity.EXCLUDED]
    assert len(excluded) == 2
    assert any("sso" in i.description.lower() for i in excluded)
    assert any(i.category == "mobile" for i in excluded)


def test_english_payments_clause_with_integration_wording_stays_payment():
    # v8: "Integration with at most 3 payment providers" used to tie 1-1 with the
    # integration category and lose on dict order — unkeying the effort pool from
    # the payment work items (consumed_by_category returned 0 forever).
    from etki.extraction.scope_extractor import _category

    text = ("Payments — Accepting payments by credit card and debit card is in "
            "scope. Integration with at most 3 payment providers is supported. "
            "This item has an effort pool of 30 hours.")
    assert _category(text.lower()) == "payment"


def test_one_excluded_bullet_does_not_flip_siblings():
    """A mixed section: only the bullet carrying exclusion wording is EXCLUDED;
    the sibling bullets stay INCLUDED (they used to all flip — the section
    polarity read every bullet's keywords)."""
    import asyncio

    contract = (
        "## Madde 6.2 — Entegrasyonlar\n"
        "- ERP sistemi ile veri alışverişi yapılır.\n"
        "- CRM senkronizasyonu sağlanır.\n"
        "- Kripto ödeme entegrasyonu kapsam dışıdır.\n"
    )
    items = asyncio.run(HeuristicScopeExtractor().extract("C", contract))
    polarities = [i.polarity.value for i in items]
    assert polarities == ["INCLUDED", "INCLUDED", "EXCLUDED"]


def test_exclusion_section_still_marks_every_bullet():
    import asyncio

    contract = (
        "## Madde 7.1 — Hariç Tutulanlar (Kapsam Dışı)\n"
        "Aşağıdaki işler kapsam dışındadır:\n"
        "- SSO entegrasyonu.\n"
        "- Mobil uygulama.\n"
    )
    items = asyncio.run(HeuristicScopeExtractor().extract("C", contract))
    assert all(i.polarity.value == "EXCLUDED" for i in items)


def test_negated_exclusions_stay_included():
    import asyncio

    contract = (
        "## Madde 5.3 — Raporlama Ekleri\n"
        "Ek rapor şablonları kapsam dışında değildir; talep üzerine hazırlanır.\n"
        "## Clause 5.4 — Exports\n"
        "Custom exports are not excluded and are delivered on request.\n"
    )
    items = asyncio.run(HeuristicScopeExtractor().extract("C", contract))
    assert [i.polarity.value for i in items] == ["INCLUDED", "INCLUDED"]


def test_real_world_heading_styles_extract_clauses():
    """En-dash, 'MADDE 5. BAŞLIK' dot separator and keyword-less '5. KAPSAM'
    numbered headings used to extract ZERO clauses silently."""
    import asyncio

    contract = (
        "Madde 3 – Kimlik Doğrulama\n"          # en-dash
        "Parola girişi kapsam dahilindedir.\n"
        "MADDE 5. RAPORLAMA\n"                   # uppercase + dot separator
        "Aylık rapor üretimi yapılır.\n"
        "6.1) Hariç Tutulanlar\n"                # keyword-less numbered heading
        "SSO entegrasyonu kapsam dışıdır.\n"
    )
    items = asyncio.run(HeuristicScopeExtractor().extract("C", contract))
    assert len(items) == 3
    assert items[0].source_clause == "Madde 3"
    assert items[1].source_clause == "MADDE 5"
    assert items[2].source_clause == "Madde 6.1"
    assert items[2].polarity is Polarity.EXCLUDED


def test_numbered_list_lines_in_prose_are_not_headings():
    import asyncio

    contract = (
        "## Madde 2 — Süreç\n"
        "1. adım tamamlanır ve rapor üretilir.\n"
        "2. adım onaya gider.\n"
    )
    items = asyncio.run(HeuristicScopeExtractor().extract("C", contract))
    assert len(items) == 1  # the numbered prose lines stay in the section body


def test_sla_durations_are_not_quota_limits():
    import asyncio

    contract = (
        "## Madde 9.1 — Destek\n"
        "Kritik hatalara en fazla 4 saat içinde yanıt verilir; "
        "ayda en fazla 5 rapor üretilir.\n"
        "## Clause 9.2 — Support\n"
        "Incidents are answered within at most 8 hours.\n"
    )
    items = asyncio.run(HeuristicScopeExtractor().extract("C", contract))
    assert items[0].limits.quantity == 5  # the SLA '4 saat' is skipped, the quota wins
    assert items[1].limits.quantity is None  # duration-only clause → no quota


def test_pool_phrasing_variants_and_bullet_sections():
    import asyncio

    contract = (
        "## Madde 4.1 — Raporlama\n"
        "Efor havuzu: 40 saat ayrılmıştır.\n"
        "## Clause 4.2 — Integrations\n"
        "A 24-hour effort pool applies to the items below:\n"
        "- ERP data exchange is delivered.\n"
        "- CRM sync is delivered.\n"
    )
    items = asyncio.run(HeuristicScopeExtractor().extract("C", contract))
    assert items[0].effort_pool_hours == 40.0  # 'Efor havuzu: N saat' variant
    assert [i.effort_pool_hours for i in items[1:]] == [24.0, 24.0]  # bullets inherit


def test_llm_extractor_falls_back_and_backfills():
    """W3: an LLM/endpoint error used to abort the whole project index; and LLM
    items silently lost limits/pools. Failure → heuristic fallback; success →
    deterministic backfill from each item's description."""
    import asyncio

    from etki.extraction.scope_extractor import LLMScopeExtractor

    contract = "## Madde 4.1 — Raporlama\nAyda en fazla 5 rapor. Efor havuzu 40 saattir.\n"

    class _Boom:
        async def complete_json(self, *, system: str, user: str) -> dict:
            raise RuntimeError("endpoint down")

    items = asyncio.run(LLMScopeExtractor(_Boom()).extract("C", contract))
    assert items and items[0].limits.quantity == 5  # heuristic fallback ran

    class _NoLimits:
        async def complete_json(self, *, system: str, user: str) -> dict:
            return {"items": [{
                "id": "S1", "description": "Ayda en fazla 5 rapor. Efor havuzu 40 saattir.",
                "category": "reporting", "polarity": "INCLUDED", "source_clause": "Madde 4.1",
            }]}

    items = asyncio.run(LLMScopeExtractor(_NoLimits()).extract("C", contract))
    assert items[0].limits.quantity == 5  # backfilled
    assert items[0].effort_pool_hours == 40.0
