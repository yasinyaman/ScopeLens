"""etki-api — the stable plugin API for Etki.

Flat public surface: everything a plugin needs is importable from the top
level. This ``__all__`` IS the API contract — additions are a minor bump,
removals/renames a major bump (see CHANGELOG.md). Enforced by
``tests/unit/test_api_surface.py`` in the etki repo.
"""

from importlib.metadata import PackageNotFoundError, version

from etki_api.manifest import (
    MANIFEST_FILENAME,
    ManifestAdapter,
    PluginManifest,
    load_manifest,
)
from etki_api.models import (
    Churn,
    CodeModule,
    Complexity,
    DocumentRef,
    PackageMetadata,
    WorkItem,
)
from etki_api.plugin import (
    AdapterFactory,
    PluginSpec,
    PortName,
    SecurityCapabilities,
)
from etki_api.ports import (
    Capabilities,
    CodeRepositoryProvider,
    DocumentSourceProvider,
    EmbeddingProvider,
    LLMClient,
    RegistryMetadataProvider,
    RerankProvider,
    WorkItemProvider,
)

try:
    __version__ = version("etki-api")
except PackageNotFoundError:  # running from a source tree without install
    __version__ = "0.0.0"

__all__ = [
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
