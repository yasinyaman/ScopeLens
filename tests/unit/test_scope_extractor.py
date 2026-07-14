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
