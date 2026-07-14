"""i18n core: catalog translation + fallback + locale resolution priority."""

from types import SimpleNamespace

from etki.config import Settings
from etki.i18n import resolve_locale, t


def test_t_translates_known_key() -> None:
    assert t("decision.IN_SCOPE", "tr") == "Kapsam içi"
    assert t("decision.IN_SCOPE", "en") == "In scope"
    assert t("decision.IN_SCOPE", "de") == "Im Umfang"


def test_t_falls_back_to_tr_then_key() -> None:
    # Unknown language -> tr; unknown key -> the key itself.
    assert t("risk.HIGH", "xx") == "Yüksek"
    assert t("yok.boyle.anahtar", "en") == "yok.boyle.anahtar"


def test_t_formats_params() -> None:
    # format params (even a key not in the catalog still gets formatted)
    assert t("{n} modül", "en", n=3) == "3 modül"


def _req(session: dict | None = None, accept: str = "") -> object:
    return SimpleNamespace(
        session=session if session is not None else {},
        headers={"accept-language": accept},
    )


def test_resolve_locale_priority() -> None:
    s = Settings(default_language="tr")
    # 1) session takes priority
    assert resolve_locale(_req(session={"lang": "de"}, accept="en"), s) == "de"
    # 2) no session -> first supported Accept-Language
    assert resolve_locale(_req(accept="fr, en-US;q=0.9, de"), s) == "en"
    # 3) neither present -> default
    assert resolve_locale(_req(accept="fr-FR"), s) == "tr"
    # unsupported session value is ignored -> header/default
    assert resolve_locale(_req(session={"lang": "xx"}, accept="de"), s) == "de"
