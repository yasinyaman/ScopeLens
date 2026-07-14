"""Graph-retrieval eval (GraphRAG Faz 2.6): three paths, one recall yardstick.

Measures, over `eval/datasets/graph_queries.json` (committed BEFORE the retrieval
code — freeze discipline), the node recall of:

- **find_k**  — plain top-k retrieval (lexical in CI; embedding when
  ETKI_EMBED_* is configured, deterministic per model)
- **find_k + expand** — top-3 seeds widened by the token-budgeted graph walk

The gate (wired into eval/runner) is TR-only so CI stays deterministic: the EN
paraphrase rows are report-only measurement points for embedding runs — a
lexical miss there is the datum, not a failure.

Standalone: `python -m eval.graph_retrieval`
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from etki.adapters.ast_code_index import AstCodeRepositoryProvider
from etki.adapters.registry import (
    build_documents,
    build_embedder,
    build_reranker,
    build_work_items,
)
from etki.config import Settings, load_connectors
from etki.core.models import WorkItem
from etki.extraction.scope_extractor import build_scope_extractor
from etki.graphquery import IndexGraphQuery
from etki.indexing.engine import IndexingEngine

_DATASET = Path(__file__).parent / "datasets" / "graph_queries.json"
_DATASETS_DIR = Path(__file__).parent / "datasets"

# Corpus table: (label, connectors yaml or None=default, dataset file, gated?).
# TR sets gate CI; the EN set is report-only — demo_shop_en is the HELD-OUT
# corpus, so it must never become a repeated CI gate (held-out discipline).
CORPORA: list[tuple[str, str | None, Path, bool]] = [
    ("demo", None, _DATASETS_DIR / "graph_queries.json", True),
    ("shop", "config/connectors.shop.yaml", _DATASETS_DIR / "graph_queries_shop.json", True),
    ("shop_en", "config/connectors.heldout.yaml",
     _DATASETS_DIR / "graph_queries_shop_en.json", False),
]


async def build_query_layer(connectors_path: str | None = None) -> IndexGraphQuery:
    """Same reproducible corpus as the other gates: ast engine, no Joern/LLM."""
    settings = Settings()
    connectors = load_connectors(connectors_path or settings.connectors_path)
    documents = build_documents(connectors.documents)
    src_root = connectors.code_repo.options.get("src_root", "samples/demo_project/src")
    index = await IndexingEngine(
        documents, AstCodeRepositoryProvider(src_root), build_scope_extractor()
    ).build()
    provider = build_work_items(connectors.work_items)
    items: list[WorkItem] = provider.all_items() if hasattr(provider, "all_items") else []
    # Embedder + reranker are env-driven (ETKI_EMBED_/RERANK_BASE_URL):
    # absent in CI → lexical find_k and plain-BFS packing, fully deterministic.
    return IndexGraphQuery(
        index, items,
        embedder=build_embedder(settings),
        reranker=build_reranker(settings),
    )


def _recall(expected: list[str], retrieved: set[str]) -> float:
    return len(set(expected) & retrieved) / len(expected) if expected else 1.0


def _precision(expected: list[str], retrieved: set[str]) -> float:
    return len(set(expected) & retrieved) / len(retrieved) if retrieved else 0.0


async def evaluate(
    gq: IndexGraphQuery, dataset: Path = _DATASET, *, k: int = 5
) -> dict:
    cases = json.loads(dataset.read_text(encoding="utf-8"))
    rows = []
    for case in cases:
        top = await gq.find_k_nodes(case["query"], k=k)
        find_k_ids = {n.id for n in top}
        sub = await gq.expand([n.id for n in top[:3]], max_hops=2, token_budget=1200)
        combined_ids = find_k_ids | {n.id for n in sub.nodes}
        rows.append(
            {
                "id": case["id"],
                "lang": case.get("lang", "tr"),
                "find_k": round(_recall(case["expected"], find_k_ids), 3),
                "combined": round(_recall(case["expected"], combined_ids), 3),
                # Recall alone is cheap on a small corpus (a wide-enough expand
                # sweeps the whole graph) — precision + size expose that cost.
                "precision": round(_precision(case["expected"], combined_ids), 3),
                "retrieved": len(combined_ids),
                "missed": sorted(set(case["expected"]) - combined_ids),
            }
        )

    def _mean(lang: str, key: str) -> float:
        vals = [r[key] for r in rows if r["lang"] == lang]
        return round(sum(vals) / len(vals), 3) if vals else 0.0

    return {
        "rows": rows,
        "tr_find_k": _mean("tr", "find_k"),
        "tr_combined": _mean("tr", "combined"),
        "tr_precision": _mean("tr", "precision"),
        "tr_retrieved": _mean("tr", "retrieved"),
        "en_find_k": _mean("en", "find_k"),
        "en_combined": _mean("en", "combined"),
    }


def report(metrics: dict) -> str:
    parts = []
    if any(r["lang"] == "tr" for r in metrics["rows"]):
        parts.append(
            f"TR recall find_k={metrics['tr_find_k']:.2f} → "
            f"find_k+expand={metrics['tr_combined']:.2f} "
            f"(precision={metrics['tr_precision']:.2f}, ort. {metrics['tr_retrieved']:.0f} node)"
        )
    if any(r["lang"] == "en" for r in metrics["rows"]):
        parts.append(f"EN {metrics['en_find_k']:.2f} → {metrics['en_combined']:.2f}")
    lines = ["graf-retrieval: " + " | ".join(parts)]
    for r in metrics["rows"]:
        mark = "✓" if r["combined"] >= 1.0 else ("~" if r["combined"] > 0 else "✗")
        missed = f" eksik: {', '.join(r['missed'])}" if r["missed"] else ""
        lines.append(
            f"  {mark} {r['id']} [{r['lang']}] find_k={r['find_k']} "
            f"combined={r['combined']}{missed}"
        )
    return "\n".join(lines)


async def ab_pack(
    gq: IndexGraphQuery, dataset: Path = _DATASET, *, budget: int = 400
) -> dict:
    """A/B (Faz 4): under a TIGHT budget, does relevance packing beat BFS order?
    Both arms use the same seeds and budget; only the packing order differs
    (query=None → BFS arm, query=text → rerank arm)."""
    cases = json.loads(dataset.read_text(encoding="utf-8"))
    rows = []
    for case in cases:
        seeds = [n.id for n in await gq.find_k_nodes(case["query"], k=3)]
        bfs = await gq.expand(seeds, max_hops=2, token_budget=budget)
        rr = await gq.expand(seeds, max_hops=2, token_budget=budget, query=case["query"])
        bfs_ids = {n.id for n in bfs.nodes}
        rr_ids = {n.id for n in rr.nodes}
        rows.append(
            {
                "id": case["id"],
                "bfs_recall": round(_recall(case["expected"], bfs_ids), 3),
                "rr_recall": round(_recall(case["expected"], rr_ids), 3),
                "bfs_precision": round(_precision(case["expected"], bfs_ids), 3),
                "rr_precision": round(_precision(case["expected"], rr_ids), 3),
                "packing": rr.packing,  # "bfs" here means the reranker didn't run
            }
        )

    def _mean(key: str) -> float:
        return round(sum(r[key] for r in rows) / len(rows), 3) if rows else 0.0

    return {
        "rows": rows,
        "budget": budget,
        "bfs_recall": _mean("bfs_recall"),
        "rr_recall": _mean("rr_recall"),
        "bfs_precision": _mean("bfs_precision"),
        "rr_precision": _mean("rr_precision"),
    }


def ab_report(ab: dict) -> str:
    return (
        f"rerank A/B (bütçe {ab['budget']} token): "
        f"recall BFS {ab['bfs_recall']:.2f} → rerank {ab['rr_recall']:.2f} | "
        f"precision BFS {ab['bfs_precision']:.2f} → rerank {ab['rr_precision']:.2f}"
    )


async def evaluate_corpora() -> dict[str, dict]:
    """Runs the retrieval eval over every corpus in CORPORA. Returns
    {label: metrics + "gated"} — the runner gates on the gated TR sets only."""
    results: dict[str, dict] = {}
    for label, connectors, dataset, gated in CORPORA:
        gq = await build_query_layer(connectors)
        metrics = await evaluate(gq, dataset)
        metrics["gated"] = gated
        results[label] = metrics
    return results


def corpora_report(results: dict[str, dict]) -> str:
    return "\n".join(
        f"[{label}]{'' if m['gated'] else ' (rapor)'} " + report(m)
        for label, m in results.items()
    )


async def main() -> int:
    settings = Settings()
    results = await evaluate_corpora()
    print(corpora_report(results))
    if settings.rerank_base_url:
        gq = await build_query_layer()
        print(ab_report(await ab_pack(gq)))
    else:
        print(
            "rerank A/B: atlandı — ETKI_RERANK_BASE_URL yok (Noop davranışı; "
            "TEI endpoint'iyle yeniden koşun)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
