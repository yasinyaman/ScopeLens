"""Dependency-free Python-AST code indexer (CodeRepositoryProvider).

Real static analysis via the stdlib `ast`: imports → dependencies, functions +
control structures → complexity. Produces the same normalized schema as Joern;
lets the demo run without Joern too (for Python sources only).
"""

from __future__ import annotations

import ast
from pathlib import Path

from etki.adapters.code_index import CodeIndex, FileNode, IndexBackedCodeRepository
from etki.adapters.manifests import parse_manifests

_CONTROL = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith)


def _imports(tree: ast.AST) -> list[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return sorted(names)


def _api_uses(tree: ast.AST) -> dict[str, list[str]]:
    """Which SYMBOLS of each imported package the file actually touches — the
    call-site surface a version change must be audited against.

    Two capture paths: `from pkg import name` (the name itself) and attribute
    access on an imported alias (`requests.get`, `np.array` → numpy.array).
    Keys are TOP-LEVEL package names (alias-resolved); internal/stdlib keys are
    filtered later in parse_code_index, same as plain imports."""
    alias_to_pkg: dict[str, str] = {}
    uses: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                alias_to_pkg[(alias.asname or alias.name).split(".")[0]] = top
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            top = node.module.split(".")[0]
            for alias in node.names:
                if alias.name != "*":
                    uses.setdefault(top, set()).add(alias.name)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in alias_to_pkg
        ):
            uses.setdefault(alias_to_pkg[node.value.id], set()).add(node.attr)
    return {pkg: sorted(symbols) for pkg, symbols in sorted(uses.items())}


def _dotted_chain(node: ast.Attribute) -> list[str] | None:
    """`np.linalg.norm` → ["np", "linalg", "norm"]; None if the base isn't a Name."""
    parts: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return list(reversed(parts))
    return None


def _api_paths(tree: ast.AST) -> dict[str, list[str]]:
    """QUALIFIED use paths per package — the precise audit input for version
    diffs (`from faker.providers.credit_card import CreditCard` →
    "faker.providers.credit_card.CreditCard"; `np.linalg.norm` →
    "numpy.linalg.norm", alias-resolved). Keys = top-level package; only
    absolute imports (level == 0) — relative imports are internal."""
    alias_to_module: dict[str, str] = {}
    paths: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                alias_to_module[(alias.asname or alias.name).split(".")[0]] = (
                    alias.name if alias.asname else alias.name.split(".")[0]
                )
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            top = node.module.split(".")[0]
            for alias in node.names:
                if alias.name != "*":  # original name, never the asname
                    paths.setdefault(top, set()).add(f"{node.module}.{alias.name}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            chain = _dotted_chain(node)
            if chain and chain[0] in alias_to_module:
                resolved = [*alias_to_module[chain[0]].split("."), *chain[1:]]
                paths.setdefault(resolved[0], set()).add(".".join(resolved))
    return {pkg: sorted(qualified) for pkg, qualified in sorted(paths.items())}


def build_ast_index(src_root: str | Path) -> CodeIndex:
    root = Path(src_root)
    files: list[FileNode] = []
    for py in sorted(root.rglob("*.py")):
        source = py.read_text(encoding="utf-8")
        tree = ast.parse(source)
        functions = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        ]
        control = sum(1 for node in ast.walk(tree) if isinstance(node, _CONTROL))
        files.append(
            FileNode(
                path=str(py.relative_to(root)),
                loc=len(source.splitlines()),
                functions=functions,
                control_structures=control,
                imports=_imports(tree),
                api_uses=_api_uses(tree),
                api_paths=_api_paths(tree),
            )
        )
    return CodeIndex(
        root=str(root), producer="ast", files=files, dependencies=parse_manifests(root)
    )


class AstCodeRepositoryProvider(IndexBackedCodeRepository):
    def __init__(self, src_root: str | Path, churn: dict[str, int] | None = None) -> None:
        super().__init__(build_ast_index(src_root), churn, supports_incremental_diff=False)
