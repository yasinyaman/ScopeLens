"""Query tools over the index — pure, deterministic functions used by both the MCP
server and the LLM agent. (These are what get tested; transport/LLM stay separate.)
"""

from __future__ import annotations

from etki.adapters.code_index import impacted_modules
from etki.core.enums import Polarity
from etki.core.models import CodeModule, Index, WorkItem
from etki.core.text import score, tokenize
from etki.engine.estimation import DependencySurface, estimate


class IndexTools:
    def __init__(self, index: Index, work_items: list[WorkItem] | None = None) -> None:
        self._index = index
        self._items = work_items or []

    def scope_lookup(self, query: str, limit: int = 3) -> list[dict]:
        """Returns the contract scope clauses closest to the request
        (included/excluded + similarity)."""
        q = tokenize(query)
        ranked = sorted(
            (
                (score(q, tokenize(f"{s.description} {s.category}")), s)
                for s in self._index.baseline.scope_items
            ),
            key=lambda pair: pair[0],
            reverse=True,
        )
        return [
            {
                "id": s.id,
                "polarity": s.polarity.value,
                "clause": s.source_clause,
                "category": s.category,
                "similarity": round(sim, 3),
            }
            for sim, s in ranked[:limit]
            if sim > 0
        ]

    def impact_analysis(self, module: str) -> dict:
        """Impact spread of a module hint plus a high-churn warning."""
        modules = impacted_modules(self._index.modules, module, depth=1)
        return {
            "impacted": [m.id for m in modules],
            "high_churn": [m.id for m in modules if m.churn.commits_last_6mo > 15],
        }

    def similar_effort(self, description: str, limit: int = 3) -> dict:
        """Similar past work items plus a ranged effort estimate."""
        q = tokenize(description)
        ranked = sorted(
            (
                (score(q, tokenize(f"{w.title} {w.description} {w.category or ''}")), w)
                for w in self._items
            ),
            key=lambda pair: pair[0],
            reverse=True,
        )
        top = [w for sim, w in ranked if sim > 0][:limit]
        est = estimate(top, [])
        return {
            "similar": [{"id": w.id, "hours": round(w.effort_seconds / 3600, 1)} for w in top],
            "estimate": {"low": est.low, "high": est.high, "unit": est.unit, "basis": est.basis},
        }

    def baseline_summary(self) -> dict:
        """Summary of the baseline and the code graph."""
        items = self._index.baseline.scope_items
        return {
            "contract_id": self._index.baseline.contract_id,
            "scope_items": len(items),
            "excluded": sum(1 for s in items if s.polarity is Polarity.EXCLUDED),
            "modules": [m.id for m in self._index.modules],
            "dependencies": len(self._index.dependencies),
            "freshness": self._index.freshness,
        }

    def dependency_impact(self, package: str) -> dict:
        """Impact surface of a library add/upgrade: is it declared in a manifest,
        which modules import it, and the one-hop blast radius of those modules.

        Retrieval/evidence only — never a decision. Unknown package → an empty
        but well-formed answer (dynamic imports and undeclared usage exist)."""
        from etki.adapters.manifests import match_packages, normalize_pkg

        wanted = normalize_pkg(package)
        declared = [
            d for d in self._index.dependencies if normalize_pkg(d.name) == wanted
        ]
        usage = match_packages(self._index.dependencies, self._index.modules)
        used_by = sorted(
            {m for d in declared for m in usage.get(d.name, [])}
            | {
                m.id
                for m in self._index.modules
                if wanted in {normalize_pkg(p) for p in m.packages}
            }
        )
        blast: dict[str, CodeModule] = {}
        for module_id in used_by:
            for m in impacted_modules(self._index.modules, module_id, depth=1):
                blast[m.id] = m
        # Call-site surface: which symbols of the package each module touches —
        # the concrete list an upgrade/downgrade must be audited against.
        used_apis = {
            m.id: symbols
            for m in self._index.modules
            if m.id in set(used_by)
            for pkg, symbols in m.package_apis.items()
            if normalize_pkg(pkg) == wanted and symbols
        }
        used_api_paths = {
            m.id: qualified
            for m in self._index.modules
            if m.id in set(used_by)
            for pkg, qualified in m.package_api_paths.items()
            if normalize_pkg(pkg) == wanted and qualified
        }
        # Effort: the SAME surface-based estimator as the engine (engine.estimation) —
        # closes the inconsistency where the tool gave a ~2h base while triage produced
        # 98–173h from LOC.
        surface = DependencySurface(
            modules=len(used_by),
            apis=len({s for symbols in used_apis.values() for s in symbols}),
        )
        est = estimate([], list(blast.values()), dep_surface=surface)
        return {
            "package": package,
            "declared": [
                {"name": d.name, "spec": d.raw_spec, "ecosystem": d.ecosystem,
                 "manifest": d.manifest, "dev": d.dev}
                for d in declared
            ],
            "used_by": used_by,
            "used_apis": used_apis,
            "used_api_paths": used_api_paths,
            "impacted": sorted(blast),
            "high_churn": sorted(
                m.id for m in blast.values() if m.churn.commits_last_6mo > 15
            ),
            "total_loc": sum(
                m.complexity.loc for m in self._index.modules if m.id in set(used_by)
            ),
            "estimate": {
                "low": est.low, "high": est.high, "unit": est.unit, "basis": est.basis,
            },
        }


def _load_index() -> Index:
    """Loads the persisted index from config; falls back to a live AST build (no Joern)."""
    import asyncio

    from etki.adapters.ast_code_index import AstCodeRepositoryProvider
    from etki.adapters.registry import build_documents
    from etki.config import Settings, load_connectors
    from etki.extraction.scope_extractor import build_scope_extractor
    from etki.indexing.engine import IndexingEngine, load_index

    settings = Settings()
    connectors = load_connectors(settings.connectors_path)
    index = load_index(settings.index_path)
    if index is None:
        documents = build_documents(connectors.documents)
        src = connectors.code_repo.options.get("src_root", "samples/demo_project/src")
        engine = IndexingEngine(documents, AstCodeRepositoryProvider(src), build_scope_extractor())
        index = asyncio.run(engine.build())
    return index


def load_index_tools() -> IndexTools:
    """Builds IndexTools from config: uses the persisted (Joern) index if present,
    otherwise indexes with AST (no Joern needed)."""
    from etki.adapters.registry import build_work_items
    from etki.config import Settings, load_connectors

    settings = Settings()
    connectors = load_connectors(settings.connectors_path)
    index = _load_index()
    work_items = build_work_items(connectors.work_items)
    items = work_items.all_items() if hasattr(work_items, "all_items") else []
    return IndexTools(index, items)


def load_graph_query():  # type: ignore[no-untyped-def]  # -> IndexGraphQuery (late import: cycle)
    """Builds the graph-query layer from config, same corpus as load_index_tools.
    Embedder/reranker are env-driven (absent → lexical find_k + BFS packing)."""
    from etki.adapters.registry import build_embedder, build_reranker, build_work_items
    from etki.config import Settings, load_connectors
    from etki.graphquery import IndexGraphQuery

    settings = Settings()
    connectors = load_connectors(settings.connectors_path)
    index = _load_index()
    work_items = build_work_items(connectors.work_items)
    items = work_items.all_items() if hasattr(work_items, "all_items") else []
    return IndexGraphQuery(
        index, items, embedder=build_embedder(settings), reranker=build_reranker(settings)
    )


def load_triage_engine():  # type: ignore[no-untyped-def]  # (late import avoids a cycle)
    """Builds a read-only TriageEngine from config, mirroring the API context — but with
    no DB, no LLM and no persistence: decisions returned by MCP are NOT saved as case
    files and leave no audit trail (the web app owns that workflow)."""
    from etki.adapters.code_index import StaticCodeRepository
    from etki.adapters.registry import build_documents, build_work_items
    from etki.config import Settings, load_connectors
    from etki.engine.estimation import consumed_by_category
    from etki.engine.triage import TriageEngine

    settings = Settings()
    connectors = load_connectors(settings.connectors_path)
    index = _load_index()
    work_items = build_work_items(connectors.work_items)
    consumed = (
        consumed_by_category(work_items.all_items()) if hasattr(work_items, "all_items") else {}
    )
    return TriageEngine(
        work_items,
        StaticCodeRepository(index.modules),
        build_documents(connectors.documents),
        index.baseline,
        model_version=settings.model_version,
        index_freshness=index.freshness,
        consumed_by_category=consumed,
        in_scope_threshold=settings.in_scope_threshold,
        gray_threshold=settings.gray_threshold,
        estimation_params=settings.estimation_params(),
        dependencies=index.dependencies,
    )


def triage_to_dict(case) -> dict:  # type: ignore[no-untyped-def]  # (CaseFile; late import)
    """Serializes a CaseFile into a compact, MCP-friendly dict: decision + confidence +
    effort range + frozen cited clauses + impacted modules per sub-request."""
    decisions = []
    for sub, d in zip(case.sub_requests, case.decisions, strict=False):
        est = d.effort_estimate
        decisions.append(
            {
                "sub_request": sub.item,
                "decision": d.decision.value,
                "confidence": round(d.confidence, 2),
                "effort": {"low": est.low, "high": est.high, "unit": est.unit, "basis": est.basis},
                "risk": {"level": d.risk.level.value, "escalation": d.risk.escalation},
                "cited_clauses": [
                    {
                        "id": s.id,
                        "clause": s.source_clause,
                        "polarity": s.polarity.value,
                        "description": s.description,
                    }
                    for s in d.evidence.cited_clauses
                ],
                "impacted_modules": d.evidence.impacted_modules,
                "reasoning": d.evidence.reasoning,
                "assumptions": d.evidence.assumptions,
                "model_version": d.model_version,
                "index_freshness": d.index_freshness,
            }
        )
    return {"request": case.raw_request, "decisions": decisions}
