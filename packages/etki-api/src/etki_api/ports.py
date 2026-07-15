"""External-integration ports (hexagonal architecture) — the frozen plugin API.

Adapters (built-in or plugin) implement these Protocols structurally (no
inheritance) and normalize vendor differences away. The Etki core talks ONLY
to these; it knows no vendor name. Internal ports (persistence, wiki, graph
query, HITL ingest) are deliberately NOT here — they live in ``etki.core.ports``
and are free to change.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from etki_api.models import CodeModule, DocumentRef, PackageMetadata, WorkItem


class Capabilities(BaseModel):
    """FUNCTIONAL capability declaration. The system degrades gracefully based
    on this: falls back to polling when there's no webhook, to a full re-index
    when there's no incremental diff. (Security capabilities — network/fs — are
    a separate declaration on the plugin manifest, not here.)
    """

    supports_webhooks: bool = False
    supports_realtime: bool = False
    supports_effort_tracking: bool = False
    supports_incremental_diff: bool = False


@runtime_checkable
class WorkItemProvider(Protocol):
    """Abstracts the work-tracking tool (GLPI/Jira/ADO...). Effort arrives normalized."""

    async def get_work_item(self, item_id: str) -> WorkItem: ...

    async def find_similar(self, description: str, *, limit: int = 5) -> list[WorkItem]: ...

    def capabilities(self) -> Capabilities: ...


@runtime_checkable
class CodeRepositoryProvider(Protocol):
    """Abstracts the code repository (GitHub/GitLab/git...) and the indexed
    module graph."""

    async def list_modules(self) -> list[CodeModule]: ...

    async def get_impacted(self, module_hint: str | None) -> list[CodeModule]: ...

    def capabilities(self) -> Capabilities: ...


@runtime_checkable
class DocumentSourceProvider(Protocol):
    """Abstracts the document source (FileSystem/SharePoint/Confluence...)."""

    async def list_documents(self) -> list[DocumentRef]: ...

    async def fetch_content(self, document_id: str) -> bytes: ...

    def capabilities(self) -> Capabilities: ...


@runtime_checkable
class LLMClient(Protocol):
    """Abstracts the LLM serving layer (Anthropic / OpenAI-compatible). Falls
    back to heuristics when there's no endpoint.

    Deliberately single-method in 0.x: a tool-loop/streaming surface would be a
    minor (additive) bump — recorded in the etki-api CHANGELOG."""

    async def complete_json(self, *, system: str, user: str) -> dict: ...


@runtime_checkable
class RerankProvider(Protocol):
    """Abstracts a cross-encoder reranker endpoint (TEI-compatible `/rerank`).
    Reads (query, document) pairs JOINTLY. Deterministic for a given model.
    No endpoint configured → the engine runs without this evidence layer."""

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        """Returns one raw-logit score per document, aligned with the input order."""
        ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Abstracts the embedding serving layer (Ollama / vLLM / any OpenAI-compatible
    endpoint). Unlike the LLM, embeddings are DETERMINISTIC for a given model —
    semantic matching through this port stays reproducible and auditable. No
    endpoint configured → the engine runs pure lexical matching, unchanged."""

    async def embed(self, texts: list[str], *, kind: str = "document") -> list[list[float]]:
        """kind: "document" (clause texts) or "query" (the incoming request) —
        retrieval embedding models require distinct task prefixes per side."""
        ...


@runtime_checkable
class RegistryMetadataProvider(Protocol):
    """Abstracts the public package registries (PyPI / npm / Maven Central…).
    OPTIONAL and off by default — CI and air-gapped deployments never call out;
    any failure degrades to None."""

    async def latest(self, ecosystem: str, name: str) -> PackageMetadata | None: ...
