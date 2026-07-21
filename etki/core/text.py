"""The production lexical scorer — the decision-path matcher.

Deterministic and golden-set-pinned: symmetric-normalized similarity
(``score`` = q_cov·√t_cov, thresholds live in Settings), bilingual TR/EN
stopword tables, a TR↔EN canonical/brand bridge (``_SYNONYM_STEMS``),
prefix-4 suffix tolerance (rapor↔rapora, filtre↔filtreleri) and a
short-query cap. Embeddings/rerankers exist as retrieval-side assists only —
they never replace this scorer on the decision path.

This file is freeze-guarded (engine side): changes here must never land in
the same change set as any ``eval/datasets/**/*.json`` edit, and behavioral
changes require re-running the eval gates.
"""

from __future__ import annotations

import math
import re

_STOP = {
    # conjunction / preposition / filler
    "ve", "ile", "bir", "için", "ayrıca", "dedi", "istiyor", "istedi", "müşteri",
    "olsun", "gerekiyor", "lazım", "olarak", "the", "and", "for", "with", "please",
    "add", "should",
    # generic imperative verbs — carry no scope signal (would pollute the analogy)
    "ekle", "eklensin", "eklendi", "eklenmesi", "eklenecek", "ekleme", "eklemek",
    "yapılsın", "yapılması", "güncellensin", "değiştirilsin",
    # contract boilerplate words — appear in every clause, zero content signal; if
    # left in, unrelated requests get a false hit off words like "kapsam/hariç"
    "kapsam", "kapsamı", "dahilindedir", "dahildir", "dahil", "içindedir",
    "dışındadır", "dışıdır", "hariç", "tutulanlar", "tutulmuştur",
    "sözleşme", "sözleşmenin", "sözleşmeye", "madde", "fiyatlandırılır", "yüklenici",
    # TR mirror of the stopped EN boilerplate "provide/provides/provided":
    # inflected forms of sağlamak carry no scope signal AND prefix-4-collide
    # with "sağlayıcı" (provider — a real content word in the IdP exclusion),
    # producing false exclusion hits. Surface forms only; "sağlayıcı" itself
    # must stay a token.
    "sağlanır", "sağlanacak", "sağlanacaktır", "sağlanması", "sağlar", "sağlamak",
    # TR mirror of the stopped EN "supported/supports": the inflected verb forms
    # are clause boilerplate ("X desteklenir"), yet the ("deste","support")
    # bridge promoted them to content tokens. Noun forms (destek/desteği =
    # support as a deliverable) stay tokens and keep the bridge.
    "desteklenir", "desteklenecek", "desteklenecektir", "desteklenmesi", "desteklenmektedir",
    # English function words — the symmetric score divides by |query|, so every
    # function word left in dilutes q_cov (the TR side already had this treatment;
    # this completes it for English requests/contracts).
    "their", "they", "them", "this", "that", "these", "those", "able", "want",
    "wants", "need", "needs", "let", "lets", "our", "your", "its", "all", "any",
    "can", "could", "will", "would", "when", "where", "while", "who", "what",
    "how", "get", "gets", "like", "look", "looks", "does", "don", "has", "have",
    "had", "are", "was", "were", "been", "being", "from", "into", "also", "just",
    "more", "most", "some", "such", "than", "then", "there", "here", "only",
    "very", "after", "before", "since", "about", "each", "every", "other", "own",
    "via", "per", "show", "see", "make", "use",
    # English contract boilerplate — mirrors the Turkish boilerplate list above.
    # "out" is stopped because it appears in every exclusion clause ("out of
    # scope") and produced false single-hit exclusion evidence on requests like
    # "logged out"/"sign-out".
    "out", "scope", "agreement", "contract", "contractor", "client", "shall",
    "priced", "separately", "included", "includes", "including", "excluded",
    "exclusions", "supported", "supports", "provide", "provides", "provided",
    "item", "items", "following", "within",
}

_PREFIX = 4  # a shared prefix of this length = a match (instead of proper stemming)

# ASCII-typed Turkish ("lazim", "sozlesme") used to slip past the diacritic-only
# _STOP entries and survive as noise tokens — the same sentence tokenized
# differently depending on how it was typed. Stopword lookup therefore folds
# diacritics on BOTH sides. Tokens themselves are NOT folded: the canonical
# bridge below already carries dual-spelling entries (kullanıc/kullanic, …).
# U+0307 handles Python's "İ".lower() → "i" + combining dot.
_FOLD = str.maketrans({"ı": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c", "̇": ""})


def _fold(word: str) -> str:
    return word.translate(_FOLD)


_STOP_FOLDED = frozenset(_fold(w) for w in _STOP)

# Turkish↔English domain-term bridge: since both sides reduce to the same canonical
# (English) form, Turkish-Turkish matches are preserved while cross-language matches
# are unlocked (e.g. TR request "veritabanı desteği" ↔ EN spec/code "database support").
# Keys are STEMs (prefixes) — cover Turkish inflectional suffixes (veritabanı/veritabanına/...).
_SYNONYM_STEMS: list[tuple[str, str]] = [
    ("veritaban", "database"),
    ("sürücü", "driver"), ("surucu", "driver"),
    ("ödeme", "payment"), ("odeme", "payment"),
    ("kullanıc", "user"), ("kullanic", "user"),
    # stems drop the final 'k' for k→ğ softening (desteği, kimliği, güvenliği, önbelleği)
    ("oturum", "auth"), ("yetkilendir", "auth"), ("kimli", "auth"),
    ("güvenli", "security"), ("guvenli", "security"),
    ("bildirim", "notification"),
    ("sayfalama", "pagination"),
    ("filtre", "filter"),
    ("sıralama", "sort"), ("siralama", "sort"),
    ("önbelle", "cache"), ("onbelle", "cache"),
    ("deste", "support"),
    ("rapor", "report"),
    ("arama", "search"),
    ("tarih", "date"),
    ("kategori", "category"),
    ("grafik", "chart"),
    ("parola", "password"),
    ("sıfırla", "reset"), ("sifirla", "reset"),
    # Vendor/brand lexicon (v4c): requests name PRODUCTS, contracts name CONCEPTS
    # ("integrate Okta" vs "third-party identity provider (IdP) ... out of scope").
    # Deliberately conservative — only brands whose category is unambiguous; broad
    # words ("live", "native", cloud vendors' non-identity products) stay out.
    # "azure" was mapped to idp until 2026-07 and mistranslated every Azure
    # product (a plausible Azure DevOps integration request became a two-hit
    # exclusion match); the identity sense stays covered by ("entra","idp").
    ("okta", "idp"), ("auth0", "idp"), ("keycloak", "idp"),
    ("onelogin", "idp"), ("entra", "idp"),
    ("android", "mobile"), ("iphone", "mobile"), ("ipad", "mobile"),
    ("ios", "mobile"), ("phone", "mobile"), ("telefon", "mobile"),
    ("ethereum", "cryptocurrency"),
]


def _canon(word: str) -> str:
    for stem, canon in _SYNONYM_STEMS:
        if word.startswith(stem):
            return canon
    return word


def tokenize(text: str) -> set[str]:
    words = re.findall(r"\w+", text.lower())
    return {_canon(w) for w in words if len(w) > 2 and _fold(w) not in _STOP_FOLDED}


def _match(a: str, b: str) -> bool:
    if a == b:
        return True
    return len(a) >= _PREFIX and len(b) >= _PREFIX and a[:_PREFIX] == b[:_PREFIX]


def hits(query: set[str], target: set[str]) -> int:
    """How many tokens in ``query`` find a match in ``target``."""
    count = 0
    for q in query:
        if any(_match(q, t) for t in target):
            count += 1
    return count


# Short-request guard: a 1-2 meaningful-word request can never count as a fully
# confident match against a long clause (the old asymmetric score would inflate
# requests like "rapor filtresi" to 1.0).
MIN_QUERY_TOKENS = 3
_SHORT_QUERY_CAP = 0.6


def score(query: set[str], target: set[str]) -> float:
    """SYMMETRIC-normalized similarity, in 0..1.

    The old score was query-coverage-only (the fraction of query tokens found in
    the target): a two-word request could reach 1.0 against any long clause,
    systematically inflating in-scope confidence. The new score also factors in
    the target direction:

        score = coverage(q→t) * sqrt(coverage(t→q))

    sqrt normalizes without fully penalizing long clauses. In addition, short
    (<MIN_QUERY_TOKENS token) requests are capped at _SHORT_QUERY_CAP; the decision
    engine further caps these at GRAY AREA at most (the PMO-escalation principle)."""
    if not query or not target:
        return 0.0
    q_cov = hits(query, target) / len(query)
    t_cov = hits(target, query) / len(target)
    s = q_cov * math.sqrt(t_cov)
    if len(query) < MIN_QUERY_TOKENS:
        s = min(s, _SHORT_QUERY_CAP)
    return s
