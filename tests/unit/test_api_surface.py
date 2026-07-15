"""The etki-api surface IS the plugin contract — these tests enforce it.

Three guarantees: (1) the etki.core shims re-export the SAME class objects
(isinstance/identity survive the extraction), (2) the moved models stay
enum-free and etki-free (a plugin never needs etki), (3) `etki_api.__all__`
is the exact frozen surface — accidental widening/narrowing fails here and
must be a deliberate CHANGELOG'd bump.
"""

import ast
import inspect

import etki.core.models
import etki.core.ports

import etki_api
import etki_api.manifest
import etki_api.models
import etki_api.plugin
import etki_api.ports

_EXPECTED_ALL = [
    "MANIFEST_FILENAME",
    "AdapterFactory",
    "Capabilities",
    "Churn",
    "CodeModule",
    "CodeRepositoryProvider",
    "Complexity",
    "DocumentRef",
    "DocumentSourceProvider",
    "EmbeddingProvider",
    "LLMClient",
    "ManifestAdapter",
    "PackageMetadata",
    "PluginManifest",
    "PluginSpec",
    "PortName",
    "RegistryMetadataProvider",
    "RerankProvider",
    "SecurityCapabilities",
    "WorkItem",
    "WorkItemProvider",
    "load_manifest",
]

_MOVED_MODELS = ["Churn", "CodeModule", "Complexity", "DocumentRef", "WorkItem"]
_MOVED_PORTS = [
    "Capabilities",
    "CodeRepositoryProvider",
    "DocumentSourceProvider",
    "EmbeddingProvider",
    "LLMClient",
    "PackageMetadata",
    "RegistryMetadataProvider",
    "RerankProvider",
    "WorkItemProvider",
]

# Built-in adapters that must compile against etki-api ALONE (the Faz 1 gate).
_API_ONLY_ADAPTERS = [
    "etki.adapters.glpi_work_item",
    "etki.adapters.linear_work_item",
]


def test_shims_reexport_identical_objects():
    for name in _MOVED_MODELS:
        assert getattr(etki.core.models, name) is getattr(etki_api, name), name
    for name in _MOVED_PORTS:
        assert getattr(etki.core.ports, name) is getattr(etki_api, name), name


def test_public_all_is_the_exact_contract():
    assert etki_api.__all__ == _EXPECTED_ALL, (
        "etki_api.__all__ changed — this is an API surface change and needs a "
        "deliberate semver bump + CHANGELOG entry in packages/etki-api."
    )
    for name in _EXPECTED_ALL:
        assert hasattr(etki_api, name), f"__all__ declares missing symbol: {name}"


def _imported_roots(module) -> set[str]:
    tree = ast.parse(inspect.getsource(module))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_etki_api_is_self_contained():
    """The API package must never import etki (nor its enums) — plugins depend
    on etki-api alone; a reverse dependency would drag the whole app in."""
    for module in (etki_api, etki_api.models, etki_api.ports, etki_api.plugin, etki_api.manifest):
        roots = _imported_roots(module)
        assert "etki" not in roots, f"{module.__name__} imports etki: {roots}"


def test_api_only_adapters_import_no_etki_core():
    """≥2 built-in adapters compile against the plugin API alone (Faz 1 gate)."""
    import importlib

    for dotted in _API_ONLY_ADAPTERS:
        module = importlib.import_module(dotted)
        roots = _imported_roots(module)
        assert "etki" not in roots, f"{dotted} still imports etki.*: {roots}"
        assert "etki_api" in roots, f"{dotted} should import from etki_api"
