"""GraphQueryPort implementation over the in-memory Index (GraphRAG Faz 2).

Three retrieval strategies behind one port (`core/ports.py: GraphQueryPort`):

- **find_k_nodes** — top-k over scope clauses + code modules + historical work
  items. Embedding cosine when an `EmbeddingProvider` is configured, otherwise
  the same deterministic lexical score as the engine (`core/text.score`). This
  is CANDIDATE RETRIEVAL only — never a decision signal (the measured
  bi-encoder rule: paraphrase-IN vs new-capability-CR is not separable here).
- **expand** — token-budgeted BFS over the real edges of the index: scope↔module
  mapping, module dependencies, work-item↔module category links.
- **nl_query** — LLM picks ONE read-only IndexTools call from a whitelist
  (prompt-injection-guarded, 3 attempts); no LLM or repeated failure → falls
  back to find_k_nodes, so the system never dies on a bad generation.

There is no graph database and no Cypher: the "graph" is the normalized
`Index` (JSON) the whole product runs on — nl_query therefore targets
`IndexTools`, not a query language (repo-audited plan decision, v0.2).
"""

from __future__ import annotations

import logging
import math
from collections import deque

from etki.core.models import Index, WorkItem
from etki.core.ports import (
    EmbeddingProvider,
    GraphEdge,
    GraphNode,
    LLMClient,
    QueryResult,
    RerankProvider,
    Subgraph,
)
from etki.core.text import score, tokenize
from etki.index_tools import IndexTools
from etki.llm_profile import UNTRUSTED_GUARD, sanitize_untrusted, wrap_untrusted

logger = logging.getLogger("etki")

NODE_TYPES = ("scope", "module", "workitem", "package")

# Read-only tool whitelist for nl_query: name → (IndexTools method, required args).
# Anything outside this list is refused regardless of what the LLM asks for.
_NL_TOOLS: dict[str, tuple[str, dict[str, type]]] = {
    "scope_lookup": ("scope_lookup", {"query": str}),
    "impact_analysis": ("impact_analysis", {"module": str}),
    "similar_effort": ("similar_effort", {"description": str}),
    "baseline_summary": ("baseline_summary", {}),
    "dependency_impact": ("dependency_impact", {"package": str}),
}

_NL_SYSTEM = (
    "You are a READ-ONLY query selector over the Etki knowledge graph. Pick the "
    "single tool that best fits the user's question and return this JSON: "
    '{"tool": "<tool>", "args": {...}}. Tools: '
    'scope_lookup(query: str) — search contract clauses; '
    'impact_analysis(module: str) — a module\'s impact spread; '
    'similar_effort(description: str) — similar past work + effort range; '
    'baseline_summary() — scope/code-graph summary; '
    'dependency_impact(package: str) — a library\'s declaration/usage/impact surface. '
    "Only these tools; add no other keys.\n\n" + UNTRUSTED_GUARD
)

# Strategy-selector keyword rules (v1). Dependency/impact wording → the graph
# walk; interrogatives → the NL tool picker; everything else → plain top-k.
_EXPAND_HINTS = (
    "bağımlılık", "bağımlı", "etki", "dokunuyor", "kullanıyor", "kullanan",
    "hangi modül", "depends", "dependency", "impact", "affected",
)
_NL_HINTS = ("kaç ", "ne kadar", "özet", "summary", "how many", "how much", "?")


def choose_strategy(question: str) -> str:
    q = question.lower()
    if any(h in q for h in _EXPAND_HINTS):
        return "expand"
    if any(h in q for h in _NL_HINTS):
        return "nl_query"
    return "find_k"


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


class IndexGraphQuery:
    """`GraphQueryPort` over a project's `Index` + work items. Stateless between
    calls except the lazily-built node list and embedding cache (deterministic
    for a given index + embedding model)."""

    def __init__(
        self,
        index: Index,
        work_items: list[WorkItem] | None = None,
        *,
        embedder: EmbeddingProvider | None = None,
        llm: LLMClient | None = None,
        reranker: RerankProvider | None = None,
    ) -> None:
        self._index = index
        self._items = work_items or []
        self._embedder = embedder
        self._llm = llm
        self._reranker = reranker
        self._tools = IndexTools(index, self._items)
        self._nodes: list[GraphNode] | None = None
        self._node_vecs: list[list[float]] | None = None

    # ------------------------------------------------------------- node corpus

    def _all_nodes(self) -> list[GraphNode]:
        if self._nodes is None:
            nodes: list[GraphNode] = []
            for s in self._index.baseline.scope_items:
                text = " ".join(filter(None, [s.description, s.category, s.source_clause]))
                nodes.append(GraphNode(id=f"scope:{s.id}", type="scope", text=text))
            for m in self._index.modules:
                text = " ".join([m.id, m.path, *m.responsibilities])
                nodes.append(GraphNode(id=f"module:{m.id}", type="module", text=text))
            for w in self._items:
                text = " ".join(filter(None, [w.title, w.description, w.category]))
                nodes.append(GraphNode(id=f"workitem:{w.id}", type="workitem", text=text))
            seen_pkgs: set[str] = set()
            for d in self._index.dependencies:
                pkg_id = f"package:{d.ecosystem}:{d.name}"
                if pkg_id in seen_pkgs:
                    continue
                seen_pkgs.add(pkg_id)
                nodes.append(
                    GraphNode(
                        id=pkg_id, type="package",
                        text=" ".join(filter(None, [d.name, d.ecosystem, d.raw_spec])),
                    )
                )
            self._nodes = nodes
        return self._nodes

    def _edges(self) -> list[GraphEdge]:
        """The real relations in the index (no synthetic similarity edges)."""
        edges: list[GraphEdge] = []
        module_ids = {m.id for m in self._index.modules}
        for s in self._index.baseline.scope_items:
            for mod in s.mapped_modules:
                if mod in module_ids:
                    edges.append(
                        GraphEdge(source=f"scope:{s.id}", relation="maps_to",
                                  target=f"module:{mod}")
                    )
        for m in self._index.modules:
            for dep in m.depends_on:
                if dep in module_ids:
                    edges.append(
                        GraphEdge(source=f"module:{m.id}", relation="depends_on",
                                  target=f"module:{dep}")
                    )
            for user in m.depended_by:
                if user in module_ids:
                    edges.append(
                        GraphEdge(source=f"module:{m.id}", relation="depended_by",
                                  target=f"module:{user}")
                    )
        for w in self._items:
            if w.category in module_ids:
                edges.append(
                    GraphEdge(source=f"workitem:{w.id}", relation="touches",
                              target=f"module:{w.category}")
                )
        if self._index.dependencies:
            from etki.adapters.manifests import match_packages

            usage = match_packages(self._index.dependencies, self._index.modules)
            seen_edges: set[tuple[str, str]] = set()
            for d in self._index.dependencies:
                for module_id in usage.get(d.name, []):
                    key = (module_id, f"package:{d.ecosystem}:{d.name}")
                    if key in seen_edges:
                        continue
                    seen_edges.add(key)
                    edges.append(
                        GraphEdge(source=f"module:{module_id}", relation="uses_package",
                                  target=key[1])
                    )
        return edges

    # ------------------------------------------------------------ find_k_nodes

    async def find_k_nodes(
        self, text: str, k: int = 5, node_types: list[str] | None = None
    ) -> list[GraphNode]:
        nodes = self._all_nodes()
        if node_types:
            nodes = [n for n in nodes if n.type in node_types]
        if not nodes or not text.strip():
            return []
        scores = await self._score(text, nodes)
        scored = (
            n.model_copy(update={"score": round(s, 4)})
            for n, s in zip(nodes, scores, strict=True)
        )
        ranked = sorted(scored, key=lambda n: (-n.score, n.id))
        return [n for n in ranked if n.score > 0][:k]

    async def _score(self, text: str, nodes: list[GraphNode]) -> list[float]:
        if self._embedder is not None:
            try:
                return await self._embed_scores(text, nodes)
            except Exception:  # noqa: BLE001 — endpoint down → lexical, unchanged behavior
                logger.warning("embedding skorlaması başarısız; leksik yola düşülüyor",
                               exc_info=True)
        q = tokenize(text)
        return [score(q, tokenize(n.text)) for n in nodes]

    async def _embed_scores(self, text: str, nodes: list[GraphNode]) -> list[float]:
        all_nodes = self._all_nodes()
        if self._node_vecs is None:
            self._node_vecs = await self._embedder.embed(  # type: ignore[union-attr]
                [n.text for n in all_nodes], kind="document"
            )
        by_id = {n.id: v for n, v in zip(all_nodes, self._node_vecs, strict=True)}
        (qvec,) = await self._embedder.embed([text], kind="query")  # type: ignore[union-attr]
        return [_cosine(qvec, by_id[n.id]) for n in nodes]

    # ----------------------------------------------------------------- expand

    async def expand(
        self,
        seed_ids: list[str],
        max_hops: int = 2,
        token_budget: int = 1500,
        query: str | None = None,
    ) -> Subgraph:
        """Two stages: (1) collect the seed neighbourhood in BFS order, then
        (2) pack it into the token budget. Packing order is BFS by default; with
        a `query` AND a configured reranker the non-seed candidates are packed
        by cross-encoder relevance instead (Faz 4) — under a tight budget the
        relevant neighbours survive, not the accidentally-nearest ones. No
        reranker / endpoint error → behavior is byte-identical to plain BFS."""
        by_id = {n.id: n for n in self._all_nodes()}
        adjacency: dict[str, list[GraphEdge]] = {}
        for e in self._edges():
            adjacency.setdefault(e.source, []).append(e)
            adjacency.setdefault(e.target, []).append(e)

        # Stage 1 — frontier collection (budget-free; the budget prunes packing,
        # not reachability, so rerank gets the full candidate set to order).
        order: list[str] = []
        queue: deque[tuple[str, int]] = deque(
            (sid, 0) for sid in seed_ids if sid in by_id
        )
        seeds = {sid for sid, _ in queue}
        seen = set(seeds)
        while queue:
            node_id, hops = queue.popleft()
            order.append(node_id)
            if hops >= max_hops:
                continue
            for edge in adjacency.get(node_id, []):
                for nxt in (edge.source, edge.target):
                    if nxt not in seen:
                        seen.add(nxt)
                        queue.append((nxt, hops + 1))

        # Stage 2 — packing order.
        packing = "bfs"
        scores: dict[str, float] = {}
        if query and self._reranker is not None and len(order) > len(seeds):
            try:
                order, scores = await self._rerank_order(query, order, seeds, by_id)
                packing = "rerank"
            except Exception:  # noqa: BLE001 — endpoint down → BFS, unchanged behavior
                logger.warning("rerank paketleme başarısız; BFS sırasına düşülüyor",
                               exc_info=True)

        # Stage 3 — fill the budget along the chosen order.
        picked: dict[str, GraphNode] = {}
        spent = 0
        truncated = False
        for node_id in order:
            node = by_id[node_id]
            cost = len(node.text) // 4 + 8  # rough token estimate per node
            if spent + cost > token_budget:
                truncated = True  # budget-based pruning, not depth-based
                break
            picked[node_id] = (
                node.model_copy(update={"score": round(scores[node_id], 4)})
                if node_id in scores
                else node
            )
            spent += cost

        edges = [
            e for e in self._edges() if e.source in picked and e.target in picked
        ]
        return Subgraph(
            nodes=list(picked.values()), edges=edges,
            token_estimate=spent, truncated=truncated, packing=packing,
        )

    async def _rerank_order(
        self,
        query: str,
        order: list[str],
        seeds: set[str],
        by_id: dict[str, GraphNode],
    ) -> tuple[list[str], dict[str, float]]:
        """Seeds stay first (they ARE the query match); the rest is reordered by
        cross-encoder relevance. Returns the new order + raw-logit scores."""
        rest = [nid for nid in order if nid not in seeds]
        raw = await self._reranker.rerank(  # type: ignore[union-attr]
            query, [by_id[nid].text for nid in rest]
        )
        scores = dict(zip(rest, raw, strict=True))
        ranked_rest = sorted(rest, key=lambda nid: (-scores[nid], nid))
        seed_first = [nid for nid in order if nid in seeds]
        return seed_first + ranked_rest, scores

    # ---------------------------------------------------------------- nl_query

    async def nl_query(self, question: str) -> QueryResult:
        """LLM picks one whitelisted read-only IndexTools call. Guardrails: the
        untrusted question is delimiter-wrapped, the tool name/args are validated
        against the whitelist, and 3 failures (or no LLM) → find_k fallback —
        a bad generation can never take the system down."""
        if self._llm is not None:
            for _attempt in range(3):
                try:
                    raw = await self._llm.complete_json(
                        system=_NL_SYSTEM,
                        user=wrap_untrusted(sanitize_untrusted(question, limit=2000)),
                    )
                    call = self._validate_call(raw)
                    if call is None:
                        continue
                    tool, args = call
                    method, _schema = _NL_TOOLS[tool]
                    result = getattr(self._tools, method)(**args)
                    return QueryResult(
                        strategy="nl_query", tool=tool, tool_args=args, tool_result=result
                    )
                except Exception:  # noqa: BLE001 — retry, then fall back
                    logger.warning("nl_query denemesi başarısız", exc_info=True)
        nodes = await self.find_k_nodes(question, k=5)
        return QueryResult(strategy="nl_fallback", nodes=nodes)

    @staticmethod
    def _validate_call(raw: dict) -> tuple[str, dict] | None:
        tool = raw.get("tool")
        if tool not in _NL_TOOLS:
            return None
        _method, schema = _NL_TOOLS[tool]
        args = raw.get("args") or {}
        if not isinstance(args, dict):
            return None
        cleaned: dict = {}
        for name, typ in schema.items():
            value = args.get(name)
            if not isinstance(value, typ):
                return None  # missing/mistyped required arg → invalid call
            cleaned[name] = (
                sanitize_untrusted(value, limit=500) if isinstance(value, str) else value
            )
        return tool, cleaned  # extra keys are dropped, never forwarded

    # -------------------------------------------------------- strategy façade

    async def query(self, question: str, *, k: int = 5) -> QueryResult:
        """Rule-based strategy selection (v1): the caller asks a question, the
        port picks the path and RECORDS it in `strategy` (auditable)."""
        strategy = choose_strategy(question)
        if strategy == "expand":
            seeds = await self.find_k_nodes(question, k=3)
            sub = await self.expand([n.id for n in seeds], max_hops=2, query=question)
            return QueryResult(strategy="expand", nodes=seeds, subgraph=sub)
        if strategy == "nl_query":
            return await self.nl_query(question)
        return QueryResult(strategy="find_k", nodes=await self.find_k_nodes(question, k=k))
