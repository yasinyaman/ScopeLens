"""Extracts structured scope items (ScopeItem) from contract text.

Two strategies, same interface (`ScopeExtractor`):
- `HeuristicScopeExtractor` — the default, works with no infrastructure; splits "Madde X"
  headings into sections, catches EXCLUDED via keywords, extracts limit/category.
- `LLMScopeExtractor` — schema-constrained LLM extraction; used when an `LLMClient`
  endpoint is configured (otherwise falls back to heuristic).
"""

from __future__ import annotations

import re
from typing import Protocol

from etki.core.enums import Polarity
from etki.core.models import ScopeItem, ScopeLimit
from etki.core.ports import LLMClient

_EXCLUSION_KW = (
    "hariç",
    "kapsam dışı",
    "kapsam dışında",
    "dışındadır",
    "dahil değil",
    "hariçtir",
    "hariç tutul",
    "istisna",
    # Equivalent markers for English contracts (e.g. samples/demo_project_en).
    "out of scope",
    "outside the scope",
    "excluded",
    "exclusion",
    "not included",
    "not covered",
)

_CATEGORY_KW: dict[str, tuple[str, ...]] = {
    "dashboard": ("gösterge", "dashboard", "panel", "grafik", "widget", "chart"),
    "reporting": (
        "rapor",
        "filtre",
        "export",
        "dışa aktar",
        "excel",
        "xlsx",
        "pdf",
        "report",
        "filter",
    ),
    "auth": (
        "giriş",
        "oturum",
        "parola",
        "kimlik",
        "sso",
        "login",
        "idp",
        "oauth",
        "saml",
        "password",
        "session",
        "authentication",
    ),
    "mobile": ("mobil",),  # "mobil" ⊂ "mobile" — also catches English
    "integration": (
        "entegrasyon",
        "streaming",
        "akış",
        "bildirim",
        "push",
        "dış sistem",
        "integration",
        "notification",
        "external system",
    ),
    # e-commerce (demo_project_b)
    "cart": ("sepet", "sipariş", "order", "cart"),
    # "credit card"/"debit card" matter: without them an English payments clause
    # that also says "integration with N payment providers" ties 1–1 with the
    # integration category and loses the tie on dict order — miscategorizing the
    # clause and silently unkeying its effort pool from the payment work items.
    "payment": (
        "ödeme", "kredi kartı", "banka kartı", "kripto", "bitcoin",
        "payment", "credit card", "debit card",
    ),
    "catalog": ("ürün", "katalog", "kategori", "arama", "product", "catalog"),
    # Maintenance is checked LAST: its keywords include capability language that
    # contracts use everywhere ("... is supported" / "... desteklenir"), which used to
    # steal clauses from their real category — e.g. a payment clause reading "at most
    # 3 providers is supported" got category=maintenance, which silently broke the
    # effort-pool check (consumption is keyed by category). A real maintenance clause
    # contains no cart/payment/report vocabulary, so it still lands here.
    "maintenance": (
        "bakım",
        "hata düzeltme",
        "sla",
        "destek",
        "hata",
        "maintenance",
        "bug fix",
        "support",
    ),
}

# `#` is optional: catches both markdown (## Madde X) and plain-text (Madde X — ...) uploads.
# Besides TR "Madde", EN contract headings (Clause/Section/Article) also count as sections.
# Separators: em-dash, EN-dash, hyphen, colon and "Madde 5. Başlık"-style dot (real
# uploads use all of them; the unmatched ones used to extract ZERO clauses silently).
_HEADING = re.compile(
    r"^#{0,6}\s*((?:Madde|Bölüm|Clause|Section|Article)\s+[\d.]+)\s*[—–\-:.]\s*(.+?)\s*$",
    re.IGNORECASE,
)
# Fallback for keyword-less numbered headings ("5. KAPSAM", "5.1) Teslimatlar"):
# the number needs a dot/paren and the title must start with an uppercase letter,
# so numbered LIST lines in prose ("1. adım…") don't get promoted to sections.
_HEADING_NUMBERED = re.compile(
    r"^#{0,6}\s*(\d+(?:\.\d+)*)[.)]\s+([A-ZÇĞİÖŞÜ].{2,}?)\s*$"
)
_BULLET = re.compile(r"^\s*[-*]\s+(.*\S)\s*$")
_LIMIT = re.compile(
    r"en\s+(?:fazla|çok)\s+(\d+)|max(?:imum)?\s+(\d+)|at\s+most\s+(\d+)|up\s+to\s+(\d+)",
    re.IGNORECASE,
)
_MONTHLY = re.compile(r"\b(ayda|aylık|aylik|her ay|monthly|per month)\b", re.IGNORECASE)
_YEARLY = re.compile(r"\b(yılda|yıllık|her yıl|yearly|per year|annually)\b", re.IGNORECASE)
_POOL = re.compile(r"efor havuzu\s+(\d+)\s*saat|effort pool of\s+(\d+)\s*hours?", re.IGNORECASE)


def _effort_pool(text: str) -> float | None:
    match = _POOL.search(text)
    if not match:
        return None
    return float(next(g for g in match.groups() if g))


# Negated exclusions ("hariç değildir" = NOT excluded) used to invert: the bare
# substring 'hariç' matched and flipped the clause to EXCLUDED — the exact
# opposite of the contract's intent. Conservative list of negation shapes; a
# clause carrying BOTH a negation and a genuine exclusion resolves to INCLUDED
# (documented trade-off — rare, and the safe direction for a copilot is to keep
# the clause visible rather than auto-excluding it).
_NEGATED_EXCLUSION_KW = (
    "hariç değil",  # covers "hariç değildir"
    "kapsam dışı değil",
    "kapsam dışında değil",
    "istisna değil",
    "not excluded",
    "not out of scope",
    "not outside the scope",
)


def _polarity(text: str) -> Polarity:
    low = text.lower()
    if any(kw in low for kw in _NEGATED_EXCLUSION_KW):
        return Polarity.INCLUDED
    return Polarity.EXCLUDED if any(kw in low for kw in _EXCLUSION_KW) else Polarity.INCLUDED


def _category(text: str) -> str:
    """The category with the MOST distinct keyword hits wins (ties → dict order).

    First-match-wins let one ambient keyword steal the clause: "ödeme sağlayıcı
    entegrasyonu desteklenir" is a payment clause, but 'entegrasyon' (integration)
    or 'destek' (maintenance) matched first. Counting distinct hits lets the
    dominant vocabulary decide; maintenance sits last as the tie-break loser."""
    low = text.lower()
    best, best_hits = "genel", 0
    for category, keywords in _CATEGORY_KW.items():
        h = sum(1 for kw in keywords if kw in low)
        if h > best_hits:
            best, best_hits = category, h
    return best


# A number followed by a DURATION unit is an SLA ("en fazla 4 saat içinde
# yanıt"), not a deliverable quota — it used to parse as limit=4 and the quota
# step flagged "5 rapor" against it.
_DURATION_AFTER = re.compile(
    r"^\s*(?:saat|sa\b|dakika|dk\b|iş\s*günü|is\s*gunu|gün|gun\b"
    r"|hours?|minutes?|business\s+days?|days?)",
    re.IGNORECASE,
)


def _limits(text: str) -> ScopeLimit:
    for match in _LIMIT.finditer(text):
        if _DURATION_AFTER.match(text[match.end():]):
            continue  # SLA duration → skip; the first NON-duration limit wins
        quantity = int(next(g for g in match.groups() if g))
        period = (
            "monthly" if _MONTHLY.search(text) else "yearly" if _YEARLY.search(text) else None
        )
        return ScopeLimit(quantity=quantity, period=period)
    return ScopeLimit()


def _condense(text: str, limit: int = 240) -> str:
    # Keep the whole body (whitespace-normalized, truncated) — don't lose keywords.
    return " ".join(text.split())[:limit]


class ScopeExtractor(Protocol):
    async def extract(self, contract_id: str, text: str) -> list[ScopeItem]: ...


class HeuristicScopeExtractor:
    async def extract(self, contract_id: str, text: str) -> list[ScopeItem]:
        items: list[ScopeItem] = []
        counter = 0
        for clause, title, body_lines in _split_sections(text):
            body = "\n".join(body_lines)
            bullets = [m.group(1) for line in body_lines if (m := _BULLET.match(line))]
            # Section polarity comes from the title + NON-bullet prose only: one
            # excluded bullet in a mixed list must not flip its siblings (it used
            # to — the body string carried every bullet's keywords). A genuine
            # exclusion section still marks all bullets via its title/intro.
            non_bullet_prose = " ".join(
                line for line in body_lines if not _BULLET.match(line)
            )
            section_polarity = _polarity(f"{title} {non_bullet_prose}")
            if bullets:
                for bullet in bullets:
                    counter += 1
                    polarity = (
                        Polarity.EXCLUDED
                        if section_polarity is Polarity.EXCLUDED
                        or _polarity(bullet) is Polarity.EXCLUDED
                        else Polarity.INCLUDED
                    )
                    items.append(
                        ScopeItem(
                            id=f"SCOPE-{counter:03d}",
                            contract_id=contract_id,
                            description=f"{title}: {bullet}",
                            category=_category(f"{bullet} {title}"),
                            polarity=polarity,
                            limits=_limits(bullet),
                            source_clause=clause,
                        )
                    )
            else:
                counter += 1
                description = title if not body.strip() else f"{title} — {_condense(body)}"
                items.append(
                    ScopeItem(
                        id=f"SCOPE-{counter:03d}",
                        contract_id=contract_id,
                        description=description,
                        category=_category(f"{title} {body}"),
                        polarity=section_polarity,
                        limits=_limits(body),
                        effort_pool_hours=_effort_pool(body),
                        source_clause=clause,
                    )
                )
        return items


class LLMScopeExtractor:
    """Schema-constrained LLM extraction. Works via the `llm_client` endpoint."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    async def extract(self, contract_id: str, text: str) -> list[ScopeItem]:
        system = (
            "Extract the scope clauses from the contract text. For each clause return "
            "id, description, category, polarity (INCLUDED/EXCLUDED), source_clause. "
            'JSON only: {"items": [...]}.'
        )
        payload = await self._llm.complete_json(system=system, user=text)
        items: list[ScopeItem] = []
        for raw in payload.get("items", []):
            raw.setdefault("contract_id", contract_id)
            items.append(ScopeItem.model_validate(raw))
        return items


def build_scope_extractor(llm_client: LLMClient | None = None) -> ScopeExtractor:
    """Returns the LLM extractor if an LLM client is given, otherwise the heuristic extractor.

    The client is provider-agnostic (OpenAI-compatible or Anthropic) —
    `registry.build_llm_client(settings)` picks it."""
    if llm_client is not None:
        return LLMScopeExtractor(llm_client)
    return HeuristicScopeExtractor()


def _split_sections(text: str) -> list[tuple[str, str, list[str]]]:
    sections: list[tuple[str, str, list[str]]] = []
    clause: str | None = None
    title = ""
    body: list[str] = []
    for line in text.splitlines():
        heading = _HEADING.match(line)
        numbered = _HEADING_NUMBERED.match(line) if heading is None else None
        if heading or numbered:
            if clause is not None:
                sections.append((clause, title, body))
            if heading:
                clause, title = heading.group(1), heading.group(2)
            else:
                assert numbered is not None
                clause, title = f"Madde {numbered.group(1)}", numbered.group(2)
            body = []
        elif clause is not None:
            body.append(line)
    if clause is not None:
        sections.append((clause, title, body))
    return sections
