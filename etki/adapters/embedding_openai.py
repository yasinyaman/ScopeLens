"""OpenAI-compatible EmbeddingProvider (Ollama / vLLM / LM Studio).

Activated by ETKI_EMBED_BASE_URL (e.g. http://localhost:11434/v1 for Ollama);
no endpoint → registry returns None and the engine stays purely lexical. Embeddings
are deterministic for a given model, so semantic matching through this adapter is
reproducible — the property that keeps the evidence chain auditable.
"""

from __future__ import annotations

import httpx


class OpenAICompatibleEmbeddingClient:
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        model: str = "nomic-embed-text",
        timeout: float = 30.0,
        query_prefix: str = "search_query: ",
        doc_prefix: str = "search_document: ",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        # Retrieval models need task prefixes; without them similarity collapses
        # (nomic-embed-text: search_query/search_document; e5: query/passage).
        self._query_prefix = query_prefix
        self._doc_prefix = doc_prefix

    async def embed(self, texts: list[str], *, kind: str = "document") -> list[list[float]]:
        prefix = self._query_prefix if kind == "query" else self._doc_prefix
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/embeddings",
                headers=headers,
                json={"model": self._model, "input": [prefix + t for t in texts]},
            )
            response.raise_for_status()
            data = response.json()["data"]
        # The API may reorder; the index field restores request order.
        ordered = sorted(data, key=lambda d: d.get("index", 0))
        return [d["embedding"] for d in ordered]
