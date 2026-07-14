"""graphify-based CodeRepositoryProvider (tree-sitter, 165+ languages, no JVM).

Runs `graphify update <src> --no-cluster` (PyPI package `graphifyy`, optional extra
`etki[graphify]`) → `<GRAPHIFY_OUT>/graph.json` → normalized 'code index' JSON →
`CodeModule` graph (via `parse_code_index`, same schema as the AST/Joern producers).
The update path is deterministic and needs no LLM key.

Schema constraints of graph.json (and how we degrade):
- No per-node loc → loc is the file's line count read from disk (0 if unreadable).
- No control-structure counts → `control_structures` stays 0, so cyclomatic
  complexity falls back to the function count in `parse_code_index`.
- Imports are edges (`relation` "imports_from"/"imports"), not node fields; their
  targets are often dangling ids (no node in the graph) — the id is the module name.
- graphify also emits per-file SYMBOL nodes for imported names (label "FastAPI",
  empty `source_file`) but no symbol→package edge — those targets are skipped for
  imports (they are not modules). The symbol surface (`api_uses`/`api_paths`)
  comes from **graphify-mcp's `apis` engine** when it is installed (optional
  seam, `_load_api_scanner`): Python via stdlib ast, JS/TS/Go/Java via its
  `[treesitter]` extra — multi-language by design, same fidelity as the ast
  producer. Not installed → surface stays empty and the estimator's
  unknown-surface widening applies (honest degradation).
- Class names are included alongside functions (deliberate deviation from the AST
  producer): `impacted_modules` hint matching benefits from class names.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

from etki.adapters.code_index import CodeIndex, FileNode, IndexBackedCodeRepository


class GraphifyIndexError(RuntimeError):
    pass


def _rebase(path: str, src_root: Path) -> str:
    """graphify emits `source_file` relative to its working dir (or absolute);
    CodeIndex paths must be src_root-relative. Lexical rebase, tolerant of both."""
    p = PurePosixPath(path.replace("\\", "/"))
    bases = (
        PurePosixPath(str(src_root).replace("\\", "/")),
        PurePosixPath(src_root.resolve().as_posix()),
    )
    for base in bases:
        try:
            return p.relative_to(base).as_posix()
        except ValueError:
            continue
    return p.as_posix()


# graphify-mcp's per-file result shape: (packages, symbols-per-pkg, paths-per-pkg).
_ApiScan = tuple[set[str], dict[str, set[str]], dict[str, set[str]]]


def _load_api_scanner() -> Any:
    """Symbol-capture engine — graphify-mcp's PUBLIC `api_uses_for_source` (optional
    dependency, github.com/yasinyaman/graphify-mcp): Python via stdlib ast,
    JS/TS/Go/Java via its `[treesitter]` extra; parser selected by the file suffix,
    no file IO on their side (we own the bytes). Not installed → None — the surface
    stays empty and the effort estimator applies its "call surface not visible"
    widening (an honest degradation)."""
    try:
        from graphify_mcp import api_uses_for_source
    except ImportError:
        return None

    def scan(raw: bytes, rel: str) -> _ApiScan:
        try:
            return api_uses_for_source(raw, rel)
        except Exception:  # noqa: BLE001 — one file's parse error must not drop the surface
            return set(), {}, {}

    return scan


def map_graph_to_code_index(graph: dict[str, Any], src_root: Path) -> CodeIndex:
    """Pure mapping: graphify graph.json dict → normalized `CodeIndex`."""
    nodes = [
        n
        for n in graph.get("nodes", [])
        if n.get("file_type") == "code" and n.get("source_file")
    ]
    by_id = {n["id"]: n for n in nodes if "id" in n}
    # Imported SYMBOL nodes: the node exists but source_file is empty (not a file).
    # These are NOT module names — leaking into imports produces ghost packages
    # ("src_x_py_fastapi"); the symbol surface is filled by the graphify-mcp engine.
    symbol_ids = {
        n["id"]
        for n in graph.get("nodes", [])
        if "id" in n and not n.get("source_file")
    }

    functions: dict[str, list[str]] = {}
    for node in nodes:
        path = _rebase(str(node["source_file"]), src_root)
        names = functions.setdefault(path, [])
        label = str(node.get("label", ""))
        node_type = node.get("type")
        if label.endswith("()") or node_type in ("function", "method"):
            names.append(label.removesuffix("()"))
        elif node_type == "class":
            names.append(label)

    # NetworkX ≤3.1 exports write "links" instead of "edges".
    edges = graph.get("edges") or graph.get("links") or []
    imports: dict[str, set[str]] = {}
    for edge in edges:
        relation = edge.get("relation") or edge.get("type")
        if relation not in ("imports", "imports_from"):
            continue
        # Import edges carry their own source_file; fall back to the source node's.
        raw_path = edge.get("source_file")
        if not raw_path:
            source = by_id.get(edge.get("source"))
            raw_path = source.get("source_file") if source else None
        if not raw_path:
            continue
        if edge.get("target") in symbol_ids:
            continue  # per-file symbol node (label "FastAPI") — not a module
        # Target resolution, per real graphify output:
        # - in-repo target (node with source_file, e.g. JS relative imports):
        #   the dependency is the target file's top-level dir = its module id;
        # - node without source_file: its label is the imported module name;
        # - dangling id (no node, e.g. Python imports): the id IS the module name.
        target = by_id.get(edge.get("target"))
        if target is not None and target.get("source_file"):
            label = _rebase(str(target["source_file"]), src_root)
            label = PurePosixPath(label).parts[0]
        elif target is not None:
            label = str(target.get("label", "")).removesuffix("()")
        else:
            label = str(edge.get("target") or "")
        if not label:
            continue
        path = _rebase(str(raw_path), src_root)
        names_set = imports.setdefault(path, set())
        names_set.add(label)
        names_set.add(label.split(".")[0])  # top-level name for module-dep matching

    scanner = _load_api_scanner()
    files: list[FileNode] = []
    for path in sorted(set(functions) | set(imports)):
        target_file = src_root / path
        try:
            raw = target_file.read_bytes()
        except OSError:
            raw = b""
        loc = len(raw.decode("utf-8", errors="ignore").splitlines()) if raw else 0
        file_imports = set(imports.get(path, set()))
        api_uses: dict[str, list[str]] = {}
        api_paths: dict[str, list[str]] = {}
        if scanner is not None and raw:
            pkgs, symbols, qualified = scanner(raw, path)
            file_imports |= pkgs  # package names also come from the engine (edges are noisy)
            api_uses = {p: sorted(s) for p, s in sorted(symbols.items())}
            api_paths = {p: sorted(q) for p, q in sorted(qualified.items())}
        files.append(
            FileNode(
                path=path,
                loc=loc,
                functions=sorted(set(functions.get(path, []))),
                control_structures=0,
                imports=sorted(file_imports),
                api_uses=api_uses,
                api_paths=api_paths,
            )
        )
    from etki.adapters.manifests import parse_manifests

    return CodeIndex(
        root=str(src_root), producer="graphify", files=files,
        dependencies=parse_manifests(src_root),
    )


class GraphifyCodeRepositoryProvider(IndexBackedCodeRepository):
    def __init__(
        self,
        src_root: str | Path,
        *,
        export_dir: str | Path | None = None,
        refresh: bool = True,
        churn: dict[str, int] | None = None,
    ) -> None:
        index = self._produce(Path(src_root), export_dir, refresh)
        super().__init__(index, churn, supports_incremental_diff=False)

    @staticmethod
    def _produce(src_root: Path, export_dir: str | Path | None, refresh: bool) -> CodeIndex:
        # Output goes OUTSIDE src_root so cloned customer repos stay pristine.
        out_dir = Path(export_dir) if export_dir else src_root.parent / "graphify-out"
        graph_path = out_dir / "graph.json"
        if refresh or not graph_path.exists():
            out_dir.mkdir(parents=True, exist_ok=True)
            try:
                subprocess.run(
                    ["graphify", "update", str(src_root), "--no-cluster"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=900,
                    env={**os.environ, "GRAPHIFY_OUT": str(out_dir.resolve())},
                )
            except FileNotFoundError as exc:
                raise GraphifyIndexError(
                    "graphify CLI bulunamadı — `uv sync --extra graphify` "
                    "(graphifyy paketi) ile kurun"
                ) from exc
            except subprocess.CalledProcessError as exc:
                raise GraphifyIndexError(
                    f"graphify indeksleme başarısız (exit {exc.returncode}): "
                    f"{exc.stderr[-500:]}"
                ) from exc
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        return map_graph_to_code_index(graph, src_root)
