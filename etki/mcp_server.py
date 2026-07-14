"""MCP stdio server — exposes the Etki index to an LLM as tools (Epic I).

Run: `python -m etki.mcp_server` (stdio). An MCP client (Claude Desktop,
Claude Code, or any MCP-compatible agent) can call: scope_lookup, impact_analysis,
similar_effort, baseline_summary, triage_request (the full decision tree),
graph_query (strategy-routed retrieval) and wiki_search (decision memory).
Setup guide: docs/MCP.md. The tool logic lives in `index_tools` (deterministic,
also unit tested); this module is only the MCP transport wrapper.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from etki.index_tools import (
    load_graph_query,
    load_index_tools,
    load_triage_engine,
    triage_to_dict,
)

mcp = FastMCP("etki")
_tools = load_index_tools()
_engine = None  # TriageEngine, built lazily on the first triage_request call
_graph = None  # IndexGraphQuery, built lazily on the first graph_query call


@mcp.tool()
def scope_lookup(query: str) -> list[dict]:
    """Returns the contract scope clauses (included/excluded) closest to the request."""
    return _tools.scope_lookup(query)


@mcp.tool()
def impact_analysis(module: str) -> dict:
    """Returns the impacted code regions for a module, with a high-churn warning."""
    return _tools.impact_analysis(module)


@mcp.tool()
def similar_effort(description: str) -> dict:
    """Returns similar past work items and a range-based effort estimate."""
    return _tools.similar_effort(description)


@mcp.tool()
def baseline_summary() -> dict:
    """Returns a summary of the contract baseline and the code graph."""
    return _tools.baseline_summary()


@mcp.tool()
async def dependency_impact(package: str) -> dict:
    """Measures the impact surface of adding or upgrading a library: whether it
    is declared in a manifest (requirements.txt / pyproject / package.json /
    pom.xml / go.mod / Cargo.toml), which modules import it, the one-hop blast
    radius of those modules, high-churn warnings and total LOC. Evidence only —
    the scope decision still comes from triage_request. With ETKI_DEPS_ONLINE
    the declared rows also carry the registry's latest version/release date
    (display data — never compared against the raw spec)."""
    from etki.adapters.registry import build_package_registry
    from etki.config import Settings

    result = _tools.dependency_impact(package)
    provider = build_package_registry(Settings())
    if provider is not None:
        for row in result["declared"]:
            meta = await provider.latest(row["ecosystem"], row["name"])
            if meta is not None:
                row["latest"] = meta.latest_version
                row["released_at"] = meta.released_at
    return result


@mcp.tool()
async def triage_request(text: str) -> dict:
    """Runs the full Etki decision tree on a request and returns the real,
    evidence-backed decision: in scope / out of scope / CR candidate / gray area /
    maintenance, with confidence, an effort RANGE, the cited contract clauses
    (including explicit exclusions), impacted code modules and reasoning.

    Read-only: the decision is NOT persisted as a case file and leaves no audit
    trail — the Etki web app owns the approval workflow."""
    global _engine
    if _engine is None:
        _engine = load_triage_engine()
    case = await _engine.triage(text)
    return triage_to_dict(case)


@mcp.tool()
async def graph_query(question: str) -> dict:
    """Retrieves related knowledge-graph nodes (scope clauses, code modules, past
    work items) for a question. Picks the strategy itself — top-k, token-budgeted
    graph expansion, or a guarded read-only NL query — and records the chosen
    path in `strategy`. Retrieval only: results are context, never a decision."""
    global _graph
    if _graph is None:
        _graph = load_graph_query()
    return (await _graph.query(question)).model_dump()


@mcp.tool()
def wiki_search(query: str, project_id: str = "demo") -> list[dict]:
    """Searches the decision wiki (past decisions, precedents from PMO overrides,
    disputed clauses) with token-AND matching. The wiki is a projection of the
    decision database — see `python -m etki.wiki`."""
    from etki.adapters.registry import build_wiki_store
    from etki.config import Settings

    store = build_wiki_store(Settings())
    if store is None:
        return [{"info": "Karar wiki'si kapalı (ETKI_WIKI_DIR boş)."}]
    return [h.model_dump() for h in store.search(project_id, query)]


@mcp.tool()
async def dependency_api_check(package: str) -> dict:
    """API-level check for a library add/upgrade/downgrade: which SYMBOLS of the
    package the code actually calls (per module — the concrete audit list), and
    with ETKI_DEPS_ONLINE, which recent GitHub release notes MENTION those
    symbols (deterministic word-boundary intersection — the releases to read
    before changing the version; no LLM interpretation). Offline it returns the
    call-site surface alone."""
    from etki.adapters.package_registries import api_change_mentions
    from etki.adapters.registry import build_package_registry
    from etki.config import Settings

    impact = _tools.dependency_impact(package)
    used_symbols = sorted({s for symbols in impact["used_apis"].values() for s in symbols})
    result: dict = {
        "package": package,
        "declared": impact["declared"],
        "used_apis": impact["used_apis"],
        "used_api_paths": impact["used_api_paths"],
        "used_symbols": used_symbols,
        "online": False,
        "releases_checked": 0,
        "api_mentions": [],
    }
    provider = build_package_registry(Settings())
    if provider is not None and impact["declared"]:
        ecosystem = impact["declared"][0]["ecosystem"]
        name = impact["declared"][0]["name"]
        releases = await provider.release_notes(ecosystem, name)
        result["online"] = True
        result["releases_checked"] = len(releases)
        result["api_mentions"] = api_change_mentions(used_symbols, releases)
        # Security evidence: exact "==x.y.z" spec → version-precise OSV answer,
        # otherwise the package's known advisories (capped).
        spec = impact["declared"][0]["spec"]
        exact = spec[2:] if spec.startswith("==") and spec[2:] else None
        result["vulnerabilities"] = await provider.known_vulnerabilities(
            ecosystem, name, exact
        )
    return result


@mcp.tool()
async def dependency_version_diff(
    package: str, old_version: str, new_version: str, level: str = "api"
) -> dict:
    """Downloads TWO exact versions of a pypi package (user supplies name +
    versions), extracts their surfaces (parse-only — nothing is installed or
    executed) and reports the diff: removed / added / signature-changed
    symbols. `level="api"` (default) summarizes the EXPORTED API — what a
    consumer imports; `level="full"` every definition. REGARDLESS of level,
    the `your_code` section checks THIS codebase's qualified import paths
    against the FULL definition surface — Python doesn't enforce privacy, so
    a non-exported import breaking is still a break; dynamic/getattr access
    lands in `unresolved` (the honest bucket), never silently in "ok".
    Requires ETKI_DEPS_ONLINE. Example:
    dependency_version_diff("faker", "24.0.0", "25.0.0")."""
    from etki.adapters.package_download import PackageFetcher, version_diff_report
    from etki.adapters.registry import build_package_registry
    from etki.config import Settings

    settings = Settings()
    if not settings.deps_online:
        return {"error": "Çevrimiçi paket indirme kapalı — ETKI_DEPS_ONLINE=true gerekli."}
    impact = _tools.dependency_impact(package)
    return await version_diff_report(
        package, old_version, new_version,
        used_paths=sorted({p for ps in impact["used_api_paths"].values() for p in ps}),
        used_symbols=sorted({s for ss in impact["used_apis"].values() for s in ss}),
        fetcher=PackageFetcher(
            pypi_base_url=settings.pypi_base_url,
            timeout=settings.deps_download_timeout,
            max_download_mb=settings.deps_max_download_mb,
        ),
        registry=build_package_registry(settings),
        level=level,
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
