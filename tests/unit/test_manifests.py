"""Manifest parsing (dependency impact, Round A): per-ecosystem parsers, raw
specs, normalization/matching, scan boundaries — all offline, all deterministic.
"""

from pathlib import Path

from etki.adapters.manifests import (
    MANIFEST_PARSERS,
    NOISE_IMPORTS,
    match_packages,
    normalize_pkg,
    parse_manifests,
)
from etki.core.models import CodeModule

_FIXTURES = Path(__file__).parents[2] / "samples" / "demo_deps"


def _by_name(deps):
    return {d.name: d for d in deps}


def test_requirements_txt_strips_comments_markers_and_options():
    deps = _by_name(parse_manifests(_FIXTURES / "src"))
    assert deps["requests"].raw_spec == ">=2.28,<3"
    assert deps["PyYAML"].raw_spec == "==6.0.1"
    assert deps["pandas"].raw_spec == "~=2.2"  # env marker after ';' dropped
    assert "base.txt" not in deps and "-r" not in deps  # option lines skipped
    assert all(d.ecosystem == "pypi" for d in deps.values() if d.manifest == "requirements.txt")


def test_pyproject_dependencies_and_optional_dev_groups():
    deps = parse_manifests(_FIXTURES / "src")
    httpx_dep = next(d for d in deps if d.name == "httpx")
    assert httpx_dep.raw_spec == "[http2]>=0.27" and httpx_dep.dev is False
    pytest_dep = next(d for d in deps if d.name == "pytest")
    assert pytest_dep.dev is True and pytest_dep.manifest == "pyproject.toml[dev]"


def test_package_json_deps_and_dev_deps():
    text = (_FIXTURES / "manifests" / "package.json").read_text(encoding="utf-8")
    deps = _by_name(MANIFEST_PARSERS["package.json"](text))
    assert deps["express"].raw_spec == "^4.19.0" and deps["express"].dev is False
    assert deps["@tanstack/react-query"].ecosystem == "npm"
    assert deps["vitest"].dev is True


def test_pom_xml_default_namespace_and_raw_property():
    text = (_FIXTURES / "manifests" / "pom.xml").read_text(encoding="utf-8")
    deps = _by_name(MANIFEST_PARSERS["pom.xml"](text))
    spring = deps["org.springframework.boot:spring-boot-starter-web"]
    assert spring.raw_spec == "${spring.version}"  # placeholder stays RAW
    assert deps["com.fasterxml.jackson.core:jackson-databind"].raw_spec == "2.17.0"
    assert deps["org.junit.jupiter:junit-jupiter"].dev is True  # test scope


def test_go_mod_block_and_single_require():
    text = (_FIXTURES / "manifests" / "go.mod").read_text(encoding="utf-8")
    deps = _by_name(MANIFEST_PARSERS["go.mod"](text))
    assert deps["github.com/gin-gonic/gin"].raw_spec == "v1.10.0"
    assert deps["golang.org/x/sync"].raw_spec == "v0.7.0"  # single-line require


def test_cargo_string_and_table_forms():
    text = (_FIXTURES / "manifests" / "Cargo.toml").read_text(encoding="utf-8")
    deps = _by_name(MANIFEST_PARSERS["Cargo.toml"](text))
    assert deps["serde"].raw_spec == "1.0"
    assert deps["tokio"].raw_spec == "1.38"  # table form { version = ... }
    assert deps["criterion"].dev is True


def test_parse_manifests_scans_root_and_parent_only():
    # src/ has no manifests; the corpus root (its parent) does — both levels scanned.
    deps = parse_manifests(_FIXTURES / "src")
    names = {d.name for d in deps}
    assert {"requests", "httpx"} <= names
    # From src/api the corpus root is TWO levels up → out of reach (no upward walk).
    assert parse_manifests(_FIXTURES / "src" / "api") == []
    # And nothing leaks downward either (never rglob into subtrees).
    assert not [d for d in parse_manifests(_FIXTURES.parents[1]) if d.name == "requests"]


def test_normalize_pkg_aliases_and_scopes():
    assert normalize_pkg("PyYAML") == "yaml"
    assert normalize_pkg("scikit-learn") == "sklearn"
    assert normalize_pkg("@tanstack/react-query") == "react_query"
    assert normalize_pkg("python-dateutil") == "dateutil"


def test_match_packages_links_deps_to_using_modules():
    deps = parse_manifests(_FIXTURES / "src")
    modules = [
        CodeModule(id="api", path="api/", packages=["requests", "yaml"]),
        CodeModule(id="jobs", path="jobs/", packages=["pandas"]),
    ]
    usage = match_packages(deps, modules)
    assert usage["requests"] == ["api"]
    assert usage["PyYAML"] == ["api"]  # alias: PyYAML ↔ import yaml
    assert usage["pandas"] == ["jobs"]
    assert usage["httpx"] == []  # declared, no import seen — informational


def test_first_version_prefill_guess():
    from etki.adapters.manifests import first_version

    assert first_version(">=42.0.0,<50") == "42.0.0"
    assert first_version("^4.17") == "4.17"
    assert first_version("[http2]>=0.27") == "0.27"
    assert first_version("") == "" and first_version("*") == ""


def test_noise_imports_cover_stdlib_and_node_builtins():
    assert {"os", "json", "pathlib", "fs", "crypto"} <= set(NOISE_IMPORTS)
