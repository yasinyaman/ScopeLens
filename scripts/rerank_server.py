"""Minimal TEI-compatible /rerank server — for hosts where the official TEI
image is unavailable (e.g. arm64 boxes like a DGX Spark / GX10).

Serves the exact shape `etki.adapters.rerank_tei.TeiRerankClient` expects:

    POST /rerank  {"query": "...", "texts": ["...", ...], "raw_scores": true}
    → [{"index": 0, "score": -7.2}, ...]

IMPORTANT: scores are RAW logits (no sigmoid) — the engine's threshold
(`ETKI_RERANK_STRONG`, default -6.8 for BAAI/bge-reranker-v2-m3) is calibrated
in raw logit space.

Usage (on the inference box, NOT the app machine):

    pip install fastapi uvicorn sentence-transformers
    python rerank_server.py --model BAAI/bge-reranker-v2-m3 --port 8021

Then point the app at it: ETKI_RERANK_BASE_URL=http://<host>:8021
"""

from __future__ import annotations

import argparse

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel


class RerankRequest(BaseModel):
    query: str
    texts: list[str]
    raw_scores: bool = True  # accepted for TEI parity; output is always raw logits


def build_app(model_id: str) -> FastAPI:
    # activation_fn=identity → raw logits (CrossEncoder would apply sigmoid by
    # default for single-label rerankers, which would break the calibration).
    import torch
    from sentence_transformers import CrossEncoder

    try:
        model = CrossEncoder(model_id, activation_fn=torch.nn.Identity())
    except TypeError:  # older sentence-transformers: pre-rename kwarg
        model = CrossEncoder(model_id, default_activation_function=torch.nn.Identity())
    app = FastAPI(title="etki-rerank", version="1.0")

    @app.post("/rerank")
    def rerank(body: RerankRequest) -> list[dict]:
        if not body.texts:
            return []
        scores = model.predict([(body.query, t) for t in body.texts])
        return [{"index": i, "score": float(s)} for i, s in enumerate(scores)]

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "model": model_id}

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="BAAI/bge-reranker-v2-m3")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8021)
    args = parser.parse_args()
    uvicorn.run(build_app(args.model), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
