"""Package download + API-surface diff: artifact picking, hardened extraction,
surface extraction (parse-only), version diff, used-symbol marking. All offline
(constructed mini-wheels + MockTransport); a live faker diff is env-gated.
"""

import io
import json
import os
import tarfile
import zipfile
from pathlib import Path

import httpx
import pytest
from etki.adapters.package_download import (
    PackageDownloadError,
    PackageFetcher,
    _pick_artifact,
    api_surface,
    check_used_paths,
    diff_surfaces,
    extract_archive,
    mark_used,
    package_root,
)


def _mini_wheel(path: Path, source: str) -> Path:
    """A one-module wheel-shaped zip: fake_pkg/__init__.py with given source."""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("fake_pkg/__init__.py", source)
        zf.writestr("fake_pkg-1.0.dist-info/METADATA", "Name: fake-pkg")
    return path


_OLD_SRC = (
    "def get(url, timeout=None):\n    ...\n"
    "def legacy_helper():\n    ...\n"
    "class Client:\n    def request(self, method, url):\n        ...\n"
    "def _private():\n    ...\n"
)
_NEW_SRC = (
    "def get(url, *, timeout):\n    ...\n"  # signature changed
    "class Client:\n    def request(self, method, url, **kwargs):\n        ...\n"
    "def brand_new(x):\n    ...\n"
)


def test_pick_artifact_prefers_pure_wheel():
    urls = [
        {"packagetype": "sdist", "url": "u-sdist", "filename": "p.tar.gz"},
        {"packagetype": "bdist_wheel", "url": "u-plat", "filename": "p-cp312-macos.whl"},
        {"packagetype": "bdist_wheel", "url": "u-pure", "filename": "p-py3-none-any.whl"},
    ]
    assert _pick_artifact(urls) == ("u-pure", "p-py3-none-any.whl")
    assert _pick_artifact(urls[:2])[0] == "u-plat"  # any wheel beats sdist
    assert _pick_artifact(urls[:1])[0] == "u-sdist"
    assert _pick_artifact([]) == (None, "")


def test_extract_rejects_path_traversal(tmp_path):
    evil = tmp_path / "evil.whl"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("../outside.py", "x = 1")
    with pytest.raises(PackageDownloadError, match="güvensiz arşiv yolu"):
        extract_archive(evil, tmp_path / "out")


def test_extract_rejects_zip_bomb(tmp_path, monkeypatch):
    monkeypatch.setattr("etki.adapters.package_download._MAX_EXTRACT_MB", 0)
    bomb = _mini_wheel(tmp_path / "bomb.whl", "x = 1\n" * 10)
    with pytest.raises(PackageDownloadError, match="zip-bomb"):
        extract_archive(bomb, tmp_path / "out")


def test_api_surface_and_diff_mark_used(tmp_path):
    old_root = extract_archive(_mini_wheel(tmp_path / "old.whl", _OLD_SRC), tmp_path / "o")
    new_root = extract_archive(_mini_wheel(tmp_path / "new.whl", _NEW_SRC), tmp_path / "n")
    old_surface, new_surface = api_surface(old_root), api_surface(new_root)

    assert "fake_pkg.get" in old_surface
    assert "fake_pkg.Client.request" in old_surface
    assert "fake_pkg._private" not in old_surface  # private filtered

    diff = diff_surfaces(old_surface, new_surface)
    assert diff["removed"] == ["fake_pkg.legacy_helper"]
    assert diff["added"] == ["fake_pkg.brand_new"]
    changed_names = {c["symbol"] for c in diff["changed"]}
    assert {"fake_pkg.get", "fake_pkg.Client.request"} <= changed_names

    marked = mark_used(diff, ["get"])  # the code only calls `get`
    assert [c["symbol"] for c in marked["used"]["changed"]] == ["fake_pkg.get"]
    assert marked["used"]["removed"] == []  # legacy_helper isn't used → not flagged
    assert marked["all"]["removed"] == ["fake_pkg.legacy_helper"]  # full diff kept


def _api_wheel(path: Path) -> Path:
    """Realistic layout: __init__ re-exports the public class from a submodule;
    the submodule also holds an internal helper that is NOT exported."""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "pkg/__init__.py",
            "from .proxy import Client\n\ndef top_level(x):\n    ...\n",
        )
        zf.writestr(
            "pkg/proxy.py",
            "def internal_helper(a, b):\n    ...\n"
            "class Client:\n    def request(self, url):\n        ...\n",
        )
        zf.writestr(
            "pkg/sub/__init__.py",
            "__all__ = ['exported_fn']\n\n"
            "def exported_fn(q):\n    ...\n\ndef not_in_all():\n    ...\n",
        )
    return path


def test_exported_api_is_api_level_not_code_level(tmp_path):
    from etki.adapters.package_download import exported_api

    root = extract_archive(_api_wheel(tmp_path / "api.whl"), tmp_path / "out")
    api = exported_api(root)

    # Re-export keyed by the EXPORT path, signature resolved from the source.
    assert api["pkg.Client"] == "class"
    assert api["pkg.Client.request"] == "(self, url)"  # exported class → methods
    assert api["pkg.top_level"] == "(x)"
    assert api["pkg.sub.exported_fn"] == "(q)"  # __all__ honored
    # Internal helpers and non-__all__ names are NOT part of the API view…
    assert "pkg.proxy.internal_helper" not in api
    assert not any(k.endswith("not_in_all") for k in api)
    # …but the full (code-level) view still sees them.
    assert "pkg.proxy.internal_helper" in api_surface(root)


def _sdist(path: Path, top_dir: str, src_layout: bool = False) -> Path:
    """sdist-shaped tar.gz: pkg-1.0/(src/)pkg/__init__.py."""
    inner = f"{top_dir}/src/pkg" if src_layout else f"{top_dir}/pkg"
    import io as _io

    with tarfile.open(path, "w:gz") as tf:
        data = b"def fn(a):\n    ...\n"
        info = tarfile.TarInfo(f"{inner}/__init__.py")
        info.size = len(data)
        tf.addfile(info, _io.BytesIO(data))
    return path


def test_package_root_wheel_sdist_and_src_layouts(tmp_path):
    # Wheel: package at top → identity.
    wheel_root = extract_archive(_mini_wheel(tmp_path / "w.whl", "def f():\n    ...\n"),
                                 tmp_path / "w")
    assert package_root(wheel_root) == wheel_root
    # sdist: versioned top dir → descend.
    s_root = extract_archive(_sdist(tmp_path / "s.tar.gz", "pkg-1.0"), tmp_path / "s")
    assert (package_root(s_root) / "pkg" / "__init__.py").exists()
    # src-layout sdist → descend twice.
    sl_root = extract_archive(_sdist(tmp_path / "sl.tar.gz", "pkg-2.0", src_layout=True),
                              tmp_path / "sl")
    assert (package_root(sl_root) / "pkg" / "__init__.py").exists()


def test_sdist_versions_no_longer_diff_as_everything(tmp_path):
    """Latent-bug pin: two sdist versions used to share NO surface keys (the
    versioned top dir polluted every dotted path) → the diff claimed the whole
    package was removed+added. package_root fixes the general summary."""
    old_root = package_root(
        extract_archive(_sdist(tmp_path / "a.tar.gz", "pkg-1.0"), tmp_path / "a")
    )
    new_root = package_root(
        extract_archive(_sdist(tmp_path / "b.tar.gz", "pkg-2.0"), tmp_path / "b")
    )
    diff = diff_surfaces(api_surface(old_root), api_surface(new_root))
    assert diff["removed"] == [] and diff["added"] == []  # identical content


def test_your_code_check_catches_non_exported_break(tmp_path):
    """THE pinned regression (the CreditCard scenario): a symbol that is never
    exported is removed between versions. The API-level diff correctly reports
    no removal — but OUR code imports it, so your_code must flag the break."""
    from etki.adapters.package_download import exported_api

    def wheel(path, with_credit_card):
        src = "class CreditCard:\n    def check(self):\n        ...\n" \
            if with_credit_card else "def other():\n    ...\n"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("pkg/__init__.py", "")  # exports nothing
            zf.writestr("pkg/providers/__init__.py", "")
            zf.writestr("pkg/providers/credit_card.py", src)
        return path

    old_root = extract_archive(wheel(tmp_path / "o.whl", True), tmp_path / "o")
    new_root = extract_archive(wheel(tmp_path / "n.whl", False), tmp_path / "n")
    old_full, new_full = api_surface(old_root), api_surface(new_root)
    old_api = exported_api(old_root, old_full)
    new_api = exported_api(new_root, new_full)

    # API-level view: nothing removed (it was never exported) — correct…
    assert diff_surfaces(old_api, new_api)["removed"] == []
    # …but OUR code imports it → your_code flags the real break.
    result = check_used_paths(
        {**old_full, **old_api}, {**new_full, **new_api},
        ["pkg.providers.credit_card.CreditCard"],
    )
    assert [b["path"] for b in result["broken"]] == [
        "pkg.providers.credit_card.CreditCard"
    ]


def test_check_used_paths_resolution_tiers():
    old = {"pkg.mod.fn": "(a)", "pkg.mod.Cls": "class", "pkg.util.helper": "(x)"}
    new = {"pkg.mod.fn": "(a, b)", "pkg.mod.Cls": "class", "pkg.util.helper": "(x)"}
    result = check_used_paths(old, new, [
        "pkg.mod.fn",          # exact → signature changed
        "pkg.mod",             # module prefix → members live under it → ok
        "pkg.helper",          # unique suffix (.helper) → ok
        "pkg.dynamic_thing",   # nowhere → unresolved (honest bucket)
    ])
    assert [c["path"] for c in result["changed"]] == ["pkg.mod.fn"]
    assert set(result["ok"]) == {"pkg.mod", "pkg.helper"}
    assert result["unresolved"] == ["pkg.dynamic_thing"]
    assert result["broken"] == []


def test_check_used_paths_broken_carries_move_hint():
    old = {"pkg.a.fn": "(x)"}
    new = {"pkg.b.fn": "(x)"}  # moved to another module
    result = check_used_paths(old, new, ["pkg.a.fn"])
    assert result["broken"][0]["path"] == "pkg.a.fn"
    assert result["broken"][0]["hint"] == ["pkg.b.fn"]  # "moved, not deleted" evidence


def test_exported_api_precomputed_full_is_equivalent(tmp_path):
    from etki.adapters.package_download import exported_api

    root = extract_archive(_api_wheel(tmp_path / "eq.whl"), tmp_path / "eq")
    assert exported_api(root) == exported_api(root, api_surface(root))


async def test_fetcher_downloads_via_registry_metadata(tmp_path):
    wheel_bytes = io.BytesIO()
    with zipfile.ZipFile(wheel_bytes, "w") as zf:
        zf.writestr("fake_pkg/__init__.py", _OLD_SRC)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/pypi/fake-pkg/1.0/json":
            return httpx.Response(200, text=json.dumps({
                "urls": [{"packagetype": "bdist_wheel", "filename": "fake_pkg-py3-none-any.whl",
                          "url": "https://files.example/fake_pkg-py3-none-any.whl"}],
            }))
        if request.url.path == "/fake_pkg-py3-none-any.whl":
            return httpx.Response(200, content=wheel_bytes.getvalue())
        return httpx.Response(404)

    fetcher = PackageFetcher(transport=httpx.MockTransport(handler))
    artifact = await fetcher.download("fake-pkg", "1.0", tmp_path)
    surface = api_surface(extract_archive(artifact, tmp_path / "src"))
    assert "fake_pkg.get" in surface


async def test_fetcher_enforces_download_cap(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/json"):
            return httpx.Response(200, text=json.dumps({
                "urls": [{"packagetype": "sdist", "filename": "big.tar.gz",
                          "url": "https://files.example/big.tar.gz"}],
            }))
        return httpx.Response(200, content=b"x" * (2 * 1024 * 1024))

    fetcher = PackageFetcher(transport=httpx.MockTransport(handler), max_download_mb=1)
    with pytest.raises(PackageDownloadError, match="boyut sınırı"):
        await fetcher.download("big", "1.0", tmp_path)


async def test_version_diff_report_end_to_end_offline(tmp_path):
    """The shared report (MCP tool + web fragment): built entirely offline via
    MockTransport-served mini-wheels — your_code, counts, no registry → empty
    vulnerability lists, error path on unknown version."""
    from etki.adapters.package_download import version_diff_report

    old_bytes, new_bytes = io.BytesIO(), io.BytesIO()
    with zipfile.ZipFile(old_bytes, "w") as zf:
        zf.writestr("fake_pkg/__init__.py", _OLD_SRC)
    with zipfile.ZipFile(new_bytes, "w") as zf:
        zf.writestr("fake_pkg/__init__.py", _NEW_SRC)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/pypi/fake-pkg/1.0/json":
            return httpx.Response(200, text=json.dumps({"urls": [
                {"packagetype": "bdist_wheel", "filename": "f1-py3-none-any.whl",
                 "url": "https://f.example/f1-py3-none-any.whl"}]}))
        if request.url.path == "/pypi/fake-pkg/2.0/json":
            return httpx.Response(200, text=json.dumps({"urls": [
                {"packagetype": "bdist_wheel", "filename": "f2-py3-none-any.whl",
                 "url": "https://f.example/f2-py3-none-any.whl"}]}))
        if request.url.path == "/f1-py3-none-any.whl":
            return httpx.Response(200, content=old_bytes.getvalue())
        if request.url.path == "/f2-py3-none-any.whl":
            return httpx.Response(200, content=new_bytes.getvalue())
        return httpx.Response(404)

    fetcher = PackageFetcher(transport=httpx.MockTransport(handler))
    report = await version_diff_report(
        "fake-pkg", "1.0", "2.0",
        used_paths=["fake_pkg.get", "fake_pkg.legacy_helper"],
        used_symbols=["get", "legacy_helper"],
        fetcher=fetcher,
    )
    assert [b["path"] for b in report["your_code"]["broken"]] == ["fake_pkg.legacy_helper"]
    assert [c["path"] for c in report["your_code"]["changed"]] == ["fake_pkg.get"]
    assert report["vulnerabilities"] == {"old": [], "new": []}  # no registry
    assert report["counts"]["removed"] >= 1

    missing = await version_diff_report(
        "fake-pkg", "9.9", "2.0", used_paths=[], used_symbols=[], fetcher=fetcher
    )
    assert "error" in missing  # tool/screen answer, never a crash


@pytest.mark.skipif(
    not os.environ.get("ETKI_TEST_DEPS_ONLINE"),
    reason="canlı indirme testi: ETKI_TEST_DEPS_ONLINE=1 ile koşun",
)
async def test_live_faker_version_diff(tmp_path):  # pragma: no cover — live integration
    fetcher = PackageFetcher()
    old_art = await fetcher.download("faker", "24.0.0", tmp_path)
    surface = api_surface(extract_archive(old_art, tmp_path / "src"))
    assert any(s.startswith("faker.") for s in surface)
