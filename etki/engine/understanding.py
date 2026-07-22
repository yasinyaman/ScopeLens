"""Request understanding (Epic D): free text → atomic sub-requests.

Rule-based by default (deterministic): splits on conjunctions/punctuation,
extracts a module/type hint + quantity/period. `LLMRequestSplitter` is optional
enrichment (when an endpoint exists); the gate always runs rule-based.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Protocol

from etki.core.enums import RequestType
from etki.core.models import SubRequest
from etki.core.ports import LLMClient

_SPLIT = re.compile(r"\s*(?:[,;+]|\bayrıca\b|\bbir de\b)\s*", re.IGNORECASE)

# Module hints live in config, NOT IN CODE (config/domains/*.hints.yaml): generics
# in `_common.hints.yaml`, domain-specific ones in profile files, project-specific
# additions in `projects.yaml module_hints`. That way one project's demo dictionary
# never leaks into another.
ModuleHints = Mapping[str, Sequence[str]]

_NEW_FEATURE_KW = ("sso", "entegrasyon", "oauth", "idp", "mobil", "streaming")
# The defect/maintenance dictionary is bilingual: English defect reports ("crashes
# with a 500", "produces a corrupt file") overlap the broken feature's clause, not
# the maintenance clause; type classification therefore has to stay word-based.
_MAINT_KW = (
    "hata", "bug", "arıza", "düzelt", "onar", "çökme", "patch",
    "crash", "error", "broken", "fix", "regression", "corrupt", "defect",
    "doesn't work", "does not work", "not working", "does nothing",
    # v5c: defect phrasings that name the SYMPTOM without defect vocabulary —
    # kept as phrases (not single words) to avoid false maintenance routing.
    "cuts off", "empty page", "stopped working", "boş sayfa", "çalışmıyor", "calismiyor",
)

# Dependency-change recognition (v1, deterministic). Fires on an explicit
# dependency NOUN, or a known (manifest-declared) package name combined with an
# upgrade VERB or a version number. "güncelle"/"update" ALONE never fires —
# "raporu güncelle" is a MODIFICATION, not a dependency change.
_DEP_NOUN = (
    "kütüphane", "kutuphane", "library", "dependency", "bağımlılığ", "bağımlılık",
    "bagimlilik", "paket sürüm", "package version", "cve", "zafiyet", "vulnerability",
)
_DEP_VERB = (
    "yükselt", "yukselt", "upgrade", "bump", "güncelle", "guncelle", "update",
    "geçelim", "gecelim", "geçiş", "gecis", "geçilsin", "gecilsin", "migrate",
    # Downgrade wording — a version change in EITHER direction is the same
    # request shape ("faker'ın versiyonunu düşürelim").
    "düşür", "dusur", "downgrade", "rollback", "geri al",
)
# Dotted versions first ("49.0.0"); bare integers only as a fallback and only
# SMALL ones ("Spring Boot 3") — never CVE years/ids ("CVE-2024-26130": the
# hyphen context and the 4+ digit length both exclude it).
_VERSION_DOTTED = re.compile(r"(?<![\w.-])v?(\d+(?:\.\d+){1,2})(?![\w.-])")
_VERSION_BARE = re.compile(r"(?<![\w.-])v?(\d{1,3})(?![\w.-])")
_VERSION = _VERSION_DOTTED  # dependency-change trigger: dotted or bare both count
# Security wording on a dependency request: the SCOPE decision still follows
# the contract (an out-of-scope upgrade stays a CR — someone pays), but the
# RISK layer escalates: deferring a security fix is a risk regardless of scope.
_SEC_KW = (
    "cve", "güvenlik", "guvenlik", "zafiyet", "vulnerability", "security",
    "exploit", "açığı", "acigi",
)


def has_security_wording(text: str) -> bool:
    low = text.lower()
    return any(kw in low for kw in _SEC_KW)

_QTY = re.compile(r"\b(\d+)\b")
# Direction pairs: "from 3 to 10" / "5'ten 8'e" / "5 yerine 12" — the requested
# amount is the TARGET (second) number, but the first-digit rule used to pick
# the FROM value ("from 3 to 10" read as 3, so 3 > limit(3) never fired — the
# M3-09 miss; a decrease "from 6 to 2" even produced a FALSE breach). Checked
# before the plain first-digit rule. Turkish side: ablative N'den/N'ten →
# dative M'e/M'a/M'ye/M'ya, both apostrophe forms (' and ’) or none; the \b
# after the dative keeps locative "10'da" and genitive "10'un" out.
_PAIR_PATTERNS = (
    re.compile(r"\bfrom\s+(\d+)\s+to\s+(\d+)\b", re.IGNORECASE),
    re.compile(r"\b(\d+)['’]?[dt][ae]n\s+(\d+)['’]?y?[ae]\b", re.IGNORECASE),
    re.compile(r"\b(\d+)\s+yerine\s+(\d+)\b", re.IGNORECASE),
)
# Word-numbers (v5a): requests say "six reports" / "a fourth provider" while the
# contract states a numeric limit — cardinals AND ordinals map to their value
# (an ordinal N implies a total of N: "a fourth provider" = 4 providers).
# Deliberate exclusions: EN "on" (collides with Turkish 10 — "reports on the
# dashboard" must not read as quantity 10), EN "one"/TR "bir" (articles would
# tag nearly every request with quantity 1) and multiword Turkish compounds
# ("on iki") — a limit below 2 doesn't occur in practice anyway.
_WORD_NUM: dict[str, int] = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
    "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
    "iki": 2, "üç": 3, "uc": 3, "dört": 4, "dort": 4, "beş": 5, "bes": 5,
    "altı": 6, "alti": 6, "yedi": 7, "sekiz": 8, "dokuz": 9,
    "ikinci": 2, "üçüncü": 3, "ucuncu": 3, "dördüncü": 4, "dorduncu": 4,
    "beşinci": 5, "besinci": 5, "altıncı": 6, "altinci": 6, "yedinci": 7,
    "sekizinci": 8, "dokuzuncu": 9, "onuncu": 10,
}
# EN + ASCII-Turkish period vocabulary mirrors the clause side
# (scope_extractor): without it "50 reports per year" had no request period and
# the quota step false-CR'd against a 5/month cap.
_MONTHLY = re.compile(
    r"\b(ayda|aylık|aylik|her ay|monthly|per month|every month)\b", re.IGNORECASE
)
_YEARLY = re.compile(
    r"\b(yılda|yilda|yıllık|yillik|her yıl|her yil|yearly|per year|every year|annually)\b",
    re.IGNORECASE,
)


def _default_hints() -> ModuleHints:
    # Late import: the engine core touches the config layer only when the default is needed.
    from etki.domains import load_module_hints

    return load_module_hints(None)


def guess_module(text: str, hints: ModuleHints | None = None) -> str | None:
    """Module hint from text. When `hints` is not given, the generic (_common) hints
    are used; an empty dict ({}) → no hints at all → None (falls to the LLM/similarity
    path)."""
    resolved = _default_hints() if hints is None else hints
    low = text.lower()
    for module, keywords in resolved.items():
        if any(kw in low for kw in keywords):
            return module
    return None


def guess_type(text: str) -> RequestType:
    low = text.lower()
    if any(kw in low for kw in _MAINT_KW):
        return RequestType.MAINTENANCE
    if any(kw in low for kw in _NEW_FEATURE_KW):
        return RequestType.NEW_FEATURE
    return RequestType.MODIFICATION


def _find_package(text: str, known_packages: Sequence[str]) -> str | None:
    """First manifest-declared package whose name appears in the text (longest
    name first, so 'spring-boot-starter-web' beats 'spring'). Names arrive from
    the index — the engine core stays dictionary-free."""
    low = text.lower()
    for name in sorted(known_packages, key=len, reverse=True):
        simple = name.split(":")[-1].lower()  # maven groupId:artifactId → artifactId
        if simple and simple in low:
            return name
    return None


def _target_version(text: str) -> str | None:
    match = _VERSION_DOTTED.search(text)
    if match:
        return match.group(1)
    match = _VERSION_BARE.search(text)
    return match.group(1) if match else None


def _is_dependency_change(text: str, package: str | None) -> bool:
    low = text.lower()
    if any(kw in low for kw in _DEP_NOUN):
        return True
    if package is not None and (
        any(v in low for v in _DEP_VERB)
        or _VERSION_DOTTED.search(low)
        or _VERSION_BARE.search(low)
    ):
        return True
    # "sürüm/versiyon/version" + an upgrade verb, package name unrecognized:
    # still a dependency-change shape ("yeni sürüme geçelim").
    version_word = any(w in low for w in ("sürüm", "surum", "versiyon", "version"))
    return version_word and any(v in low for v in _DEP_VERB)


def _quantity(text: str) -> int | None:
    for pattern in _PAIR_PATTERNS:
        pair = pattern.search(text)
        if pair:
            return int(pair.group(2))  # direction pair: the TARGET is the ask
    match = _QTY.search(text)
    if match:
        return int(match.group(1))  # a digit always wins over word-numbers
    for word in re.findall(r"\w+", text.lower()):
        if word in _WORD_NUM:
            return _WORD_NUM[word]
    return None


def _period(text: str) -> str | None:
    if _MONTHLY.search(text):
        return "monthly"
    if _YEARLY.search(text):
        return "yearly"
    return None


def split_request(
    raw: str,
    hints: ModuleHints | None = None,
    known_packages: Sequence[str] = (),
) -> list[SubRequest]:
    parts = [p.strip(" .") for p in _SPLIT.split(raw) if p.strip(" .")]
    if not parts:
        parts = [raw.strip(" .")]
    subs: list[SubRequest] = []
    for p in parts:
        sub_type = guess_type(p)
        package = _find_package(p, known_packages)
        # Dependency change is recognized AFTER maintenance (patch/defect wording
        # keeps its maintenance routing); since 2026-07-09 the decision tree DOES
        # branch on it (`_classify` step 1b — see the RequestType docstring).
        if sub_type is not RequestType.MAINTENANCE and _is_dependency_change(p, package):
            sub_type = RequestType.DEPENDENCY_CHANGE
        is_dep = sub_type is RequestType.DEPENDENCY_CHANGE
        subs.append(
            SubRequest(
                item=p,
                type=sub_type,
                module_hint=guess_module(p, hints),
                # A version number is NOT a quantity: "Spring Boot 3" must not
                # trip the limit/quota step as "3 items".
                quantity=None if is_dep else _quantity(p),
                period=_period(p),
                package=package if is_dep else None,
                target_version=_target_version(p) if is_dep else None,
            )
        )
    return subs


class RequestSplitter(Protocol):
    async def split(self, raw: str) -> list[SubRequest]: ...


class RuleBasedRequestSplitter:
    async def split(self, raw: str) -> list[SubRequest]:
        return split_request(raw)


class LLMRequestSplitter:
    """Schema-constrained LLM splitting; falls back to rule-based on failure."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    async def split(self, raw: str) -> list[SubRequest]:
        system = (
            "Split the given request into atomic sub-requests. Return JSON only: "
            '{"items": [{"item": "..."}]}. Each item must be a single piece of work.'
        )
        try:
            payload = await self._llm.complete_json(system=system, user=raw)
        except Exception:  # noqa: BLE001 — fall to the deterministic path on LLM error
            return split_request(raw)
        subs: list[SubRequest] = []
        for raw_item in payload.get("items", []):
            text = raw_item.get("item", "").strip() if isinstance(raw_item, dict) else str(raw_item)
            if text:
                sub_type = guess_type(text)
                # Mirror split_request's dependency handling: recognize the type
                # and never let a version number feed the limit/quota step as a
                # quantity (this path used to skip both).
                if sub_type is not RequestType.MAINTENANCE and _is_dependency_change(
                    text, None
                ):
                    sub_type = RequestType.DEPENDENCY_CHANGE
                is_dep = sub_type is RequestType.DEPENDENCY_CHANGE
                subs.append(
                    SubRequest(
                        item=text,
                        type=sub_type,
                        module_hint=guess_module(text),
                        quantity=None if is_dep else _quantity(text),
                        period=_period(text),
                        target_version=_target_version(text) if is_dep else None,
                    )
                )
        return subs or split_request(raw)
