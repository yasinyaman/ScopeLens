"""Cross-encoder reranker adapter — TEI-compatible `/rerank` endpoint.

Works with Hugging Face text-embeddings-inference (TEI) serving a reranker such
as `BAAI/bge-reranker-v2-m3`, or anything speaking the same shape:

    POST {base}/rerank  {"query": "...", "texts": ["...", ...], "raw_scores": true}
    → [{"index": 0, "score": -7.2}, ...]

`raw_scores=true` matters: the engine's thresholds are calibrated in RAW logit
space (see `Settings.rerank_strong`), not post-sigmoid. Scores are returned
aligned to the input order. Config example:

    ETKI_RERANK_BASE_URL=http://localhost:8021   # no default — off unless set
    ETKI_RERANK_STRONG=-6.8                      # calibrated per model
"""

from __future__ import annotations

import httpx


class TeiRerankClient:
    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/rerank",
                json={"query": query, "texts": documents, "raw_scores": True},
            )
            response.raise_for_status()
            scores = [0.0] * len(documents)
            for row in response.json():
                idx = int(row["index"])
                if 0 <= idx < len(scores):
                    scores[idx] = float(row["score"])
            return scores
