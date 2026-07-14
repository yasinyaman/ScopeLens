"""Normalized 'code index' schema — the contract between any indexer (Joern, AST...)
and the core. Pure and testable: the indexer produces this schema,
`parse_code_index` converts it into a `CodeModule` graph.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from pydantic import BaseModel, Field

from etki.adapters.manifests import NOISE_IMPORTS
from etki.core.models import Churn, CodeModule, Complexity, DeclaredDependency
from etki.core.ports import Capabilities, CodeRepositoryProvider


class FileNode(BaseModel):
    path: str  # root-relative, e.g. "auth/service.py"
    loc: int = 0
    functions: list[str] = Field(default_factory=list)
    control_structures: int = 0
    imports: list[str] = Field(default_factory=list)  # top-level imported names
    # Per-package symbols the file touches (`requests` → ["get", "post"]) — the
    # call-site surface for API-change checks. Filled by the ast producer;
    # joern/graphify leave it empty (defaulted → schema stays compatible).
    api_uses: dict[str, list[str]] = Field(default_factory=dict)
    # QUALIFIED use paths ("faker" → ["faker.providers.credit_card.CreditCard"])
    # — precise version-diff auditing incl. non-exported imports. ast only.
    api_paths: dict[str, list[str]] = Field(default_factory=dict)


class CodeIndex(BaseModel):
    root: str
    producer: str = "unknown"  # "joern" | "ast"
    files: list[FileNode] = Field(default_factory=list)
    # Declared manifest dependencies (filled by parse_manifests; defaulted so
    # existing producers/JSON stay valid).
    dependencies: list[DeclaredDependency] = Field(default_factory=list)


def _module_of(path: str) -> str:
    parts = PurePosixPath(path.replace("\\", "/")).parts
    return parts[0] if parts else path


def parse_code_index(index: CodeIndex) -> list[CodeModule]:
    """Groups files into modules by top-level directory; builds the dependency
    graph from imports and complexity from the metrics."""
    groups: dict[str, list[FileNode]] = {}
    for node in index.files:
        groups.setdefault(_module_of(node.path), []).append(node)
    module_ids = set(groups)

    modules: list[CodeModule] = []
    dep_map: dict[str, list[str]] = {}
    for module_id, files in groups.items():
        loc = sum(f.loc for f in files)
        functions = sorted({fn for f in files for fn in f.functions})
        control = sum(f.control_structures for f in files)
        imports = {imp for f in files for imp in f.imports}
        depends_on = sorted((imports & module_ids) - {module_id})
        # The complement of the internal-module intersection is the EXTERNAL
        # usage surface (third-party packages) — previously discarded here.
        packages = sorted(imports - module_ids - {module_id} - NOISE_IMPORTS)
        package_apis: dict[str, set[str]] = {}
        package_api_paths: dict[str, set[str]] = {}
        for f in files:
            for pkg, symbols in f.api_uses.items():
                if pkg in packages:  # external only — internal/stdlib filtered
                    package_apis.setdefault(pkg, set()).update(symbols)
            for pkg, qualified in f.api_paths.items():
                if pkg in packages:
                    package_api_paths.setdefault(pkg, set()).update(qualified)
        dep_map[module_id] = depends_on
        complexity = Complexity(loc=loc, cyclomatic=control + len(functions), files=len(files))
        modules.append(
            CodeModule(
                id=module_id,
                path=f"{module_id}/",
                responsibilities=functions,
                depends_on=depends_on,
                packages=packages,
                package_apis={p: sorted(s) for p, s in sorted(package_apis.items())},
                package_api_paths={
                    p: sorted(s) for p, s in sorted(package_api_paths.items())
                },
                complexity=complexity,
                churn=Churn(),
            )
        )

    by_id = {m.id: m for m in modules}
    for module_id, deps in dep_map.items():
        for dep in deps:
            if dep in by_id:
                by_id[dep].depended_by.append(module_id)
    for module in modules:
        module.depended_by.sort()
    return sorted(modules, key=lambda m: m.id)


def impacted_modules(
    modules: list[CodeModule], module_hint: str | None, *, depth: int = 1
) -> list[CodeModule]:
    """Module(s) matching the hint + ``depth`` degrees of dependency propagation (BFS)."""
    if not module_hint:
        return []
    hint = module_hint.lower()
    by_id = {m.id: m for m in modules}
    ordered: list[str] = [
        m.id
        for m in modules
        if hint in m.id.lower() or any(hint in r.lower() for r in m.responsibilities)
    ]
    seen = set(ordered)
    frontier = list(ordered)
    for _ in range(max(0, depth)):
        nxt: list[str] = []
        for mid in frontier:
            module = by_id.get(mid)
            if module is None:
                continue
            for dep in (*module.depends_on, *module.depended_by):
                if dep in by_id and dep not in seen:
                    seen.add(dep)
                    ordered.append(dep)
                    nxt.append(dep)
        frontier = nxt
    return [by_id[mid] for mid in ordered]


class StaticCodeRepository:
    """Online CodeRepositoryProvider serving a precomputed module graph
    (read from the persisted Index — no Joern run at triage time)."""

    def __init__(
        self,
        modules: list[CodeModule],
        dependencies: list[DeclaredDependency] | None = None,
    ) -> None:
        self._modules = list(modules)
        self._dependencies = list(dependencies or [])

    async def list_modules(self) -> list[CodeModule]:
        return list(self._modules)

    def list_dependencies(self) -> list[DeclaredDependency]:
        # Structural degradation seam (hasattr, like WorkItemProvider.all_items):
        # the CodeRepositoryProvider Protocol stays untouched.
        return list(self._dependencies)

    async def get_impacted(self, module_hint: str | None) -> list[CodeModule]:
        # depth=1 already yields the seed + its direct dependency/dependent neighbors;
        # preserves risk separation on small graphs (deeper propagation is possible via BFS).
        return impacted_modules(self._modules, module_hint, depth=1)

    def capabilities(self) -> Capabilities:
        return Capabilities(supports_incremental_diff=True)


class MergedCodeRepository:
    """Merges multiple code repos into a single graph (multi-repo impact analysis).

    With ≥2 repos, module ids and dependency edges are namespaced by repo name
    (collisions prevented; intra-repo edges preserved).
    """

    def __init__(self, providers: list[tuple[str, CodeRepositoryProvider]]) -> None:
        self._providers = providers

    async def list_modules(self) -> list[CodeModule]:
        multi = len(self._providers) > 1
        out: list[CodeModule] = []
        for name, provider in self._providers:
            for module in await provider.list_modules():
                if multi:
                    prefix = f"{name}:"
                    module = module.model_copy(
                        update={
                            "id": prefix + module.id,
                            "depends_on": [prefix + d for d in module.depends_on],
                            "depended_by": [prefix + d for d in module.depended_by],
                        }
                    )
                out.append(module)
        return out

    async def get_impacted(self, module_hint: str | None) -> list[CodeModule]:
        return impacted_modules(await self.list_modules(), module_hint, depth=1)

    def list_dependencies(self) -> list[DeclaredDependency]:
        """Union across repos. Package names stay GLOBAL (the same artifact
        everywhere — unlike module ids); only the `manifest` provenance gets
        the repo prefix when there is more than one repo."""
        multi = len(self._providers) > 1
        seen: set[tuple[str, str, str]] = set()
        out: list[DeclaredDependency] = []
        for name, provider in self._providers:
            lister = getattr(provider, "list_dependencies", None)
            for dep in lister() if lister else []:
                key = (dep.ecosystem, dep.name, dep.raw_spec)
                if key in seen:
                    continue
                seen.add(key)
                if multi:
                    dep = dep.model_copy(update={"manifest": f"{name}:{dep.manifest}"})
                out.append(dep)
        return out

    def capabilities(self) -> Capabilities:
        return Capabilities(supports_incremental_diff=True)


class IndexBackedCodeRepository:
    """Common CodeRepositoryProvider base fed from a `CodeIndex`."""

    def __init__(
        self,
        index: CodeIndex,
        churn: dict[str, int] | None = None,
        *,
        supports_incremental_diff: bool = False,
    ) -> None:
        self._modules = parse_code_index(index)
        self._dependencies = list(index.dependencies)
        if churn:
            for module in self._modules:
                module.churn.commits_last_6mo = churn.get(module.id, 0)
        self._incremental = supports_incremental_diff

    async def list_modules(self) -> list[CodeModule]:
        return list(self._modules)

    def list_dependencies(self) -> list[DeclaredDependency]:
        return list(self._dependencies)

    async def get_impacted(self, module_hint: str | None) -> list[CodeModule]:
        return impacted_modules(self._modules, module_hint)

    def capabilities(self) -> Capabilities:
        return Capabilities(
            supports_webhooks=False,
            supports_realtime=False,
            supports_effort_tracking=False,
            supports_incremental_diff=self._incremental,
        )
