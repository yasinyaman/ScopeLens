"""graphify graph.json → CodeIndex mapping (pure; no graphify install needed).

Mirrors test_code_index.py: a fixture matching the real graphify v0.9 schema
(file-level nodes, `imports_from` edges with dangling targets, edge-level
source_file) proves the mapper handles it, and `parse_code_index` builds the same
module graph as ast/joern. The live test at the bottom needs
`uv sync --extra graphify` + ETKI_TEST_GRAPHIFY=1.
"""

import importlib.util
import json
import os
from pathlib import Path

import pytest
from etki.adapters.code_index import parse_code_index
from etki.adapters.graphify_code_repo import map_graph_to_code_index

FIXTURE = Path(__file__).parent.parent / "fixtures" / "graphify_graph.json"


def _graph():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _index(graph=None):
    return map_graph_to_code_index(graph or _graph(), Path("/nonexistent-src"))


def _file(index, path):
    return next(f for f in index.files if f.path == path)


def test_maps_code_nodes_and_drops_concepts():
    index = _index()
    assert index.producer == "graphify"
    assert [f.path for f in index.files] == ["auth/service.py", "db/models.py", "pkg/util.py"]


def test_functions_include_classes_and_untyped_call_labels():
    auth = _file(_index(), "auth/service.py")
    # "login()" has no type field (label-suffix route); AuthService via type=class;
    # the file-level node ("service.py") is not a symbol and must be excluded.
    assert auth.functions == ["AuthService", "login"]


def test_imports_from_dangling_target_uses_edge_id_and_source_file():
    # Real graphify emits imports_from edges whose targets have no node — the
    # target id IS the module name, and the file comes from the edge itself.
    auth = _file(_index(), "auth/service.py")
    assert "db" in auth.imports


def test_imports_with_in_repo_target_uses_target_files_module():
    # JS-style relative imports resolve to a real node with source_file — the
    # dependency is that file's top-level dir (its module id), not its label.
    auth = _file(_index(), "auth/service.py")
    assert "pkg" in auth.imports


def test_missing_source_files_tolerated_as_zero_loc():
    assert all(f.loc == 0 for f in _index().files)


def test_parse_builds_module_graph_with_cyclomatic_fallback():
    mods = {m.id: m for m in parse_code_index(_index())}
    assert set(mods) == {"auth", "db", "pkg"}
    assert mods["auth"].depends_on == ["db", "pkg"]
    assert mods["db"].depended_by == ["auth"]
    # control_structures is always 0 for graphify → cyclomatic falls back to fn count
    assert mods["auth"].complexity.cyclomatic == 2


def test_cwd_relative_source_files_rebased_to_src_root():
    # graphify emits paths relative to its working dir, e.g. "samples/.../src/auth/x.py"
    graph = _graph()
    for item in (*graph["nodes"], *graph["edges"]):
        if item.get("source_file"):
            item["source_file"] = f"samples/demo/src/{item['source_file']}"
    index = map_graph_to_code_index(graph, Path("samples/demo/src"))
    assert [f.path for f in index.files] == ["auth/service.py", "db/models.py", "pkg/util.py"]
    assert "db" in _file(index, "auth/service.py").imports


def test_networkx_links_key_tolerated():
    graph = _graph()
    graph["links"] = graph.pop("edges")
    auth = _file(_index(graph), "auth/service.py")
    assert "db" in auth.imports


LIVE = os.environ.get("ETKI_TEST_GRAPHIFY")


@pytest.mark.skipif(not LIVE, reason="live graphify not enabled (ETKI_TEST_GRAPHIFY=1)")
async def test_graphify_live_index(tmp_path):  # pragma: no cover — live integration
    from etki.adapters.graphify_code_repo import GraphifyCodeRepositoryProvider

    provider = GraphifyCodeRepositoryProvider(
        "samples/demo_project/src", export_dir=tmp_path / "graphify-out"
    )
    modules = {m.id: m for m in await provider.list_modules()}
    assert "auth" in modules
    assert "db" in modules["auth"].depends_on
    assert (tmp_path / "graphify-out" / "graph.json").exists()


def test_symbol_nodes_do_not_become_phantom_packages(tmp_path):
    """graphify emits SYMBOL nodes without a source_file for imported names
    (label "FastAPI") — these are not module names; if they leak into imports,
    phantom packages like 'src_x_py_fastapi' are born (happened on warp)."""
    (tmp_path / "api.py").write_text("from fastapi import Depends\n", encoding="utf-8")
    graph = {
        "nodes": [
            {"id": "api", "label": "api.py", "file_type": "code", "source_file": "api.py"},
            {"id": "api_py_depends", "label": "Depends", "file_type": "code", "source_file": ""},
        ],
        "edges": [
            {"source": "api", "target": "fastapi", "relation": "imports_from",
             "source_file": "api.py"},
            {"source": "api", "target": "api_py_depends", "relation": "imports_from",
             "source_file": "api.py"},
        ],
    }
    index = map_graph_to_code_index(graph, tmp_path)
    api = _file(index, "api.py")
    assert "fastapi" in api.imports
    assert not any("depends" in imp.lower() for imp in api.imports)  # symbol ≠ module


@pytest.mark.skipif(
    importlib.util.find_spec("graphify_mcp") is None,
    reason="graphify-mcp kurulu değil (opsiyonel sembol motoru)",
)
def test_scanner_fills_multilanguage_api_surface(tmp_path):
    """The symbol surface from the graphify-mcp engine, multi-language: .py via
    stdlib-ast, .ts via tree-sitter — same fidelity under graphify as the ast
    engine."""
    (tmp_path / "api.py").write_text(
        "from fastapi import Depends\nimport numpy as np\nnp.array([1])\n",
        encoding="utf-8",
    )
    (tmp_path / "ui.ts").write_text(
        "import { useState } from 'react';\n", encoding="utf-8",
    )
    graph = {
        "nodes": [
            {"id": "a", "label": "api.py", "file_type": "code", "source_file": "api.py"},
            {"id": "u", "label": "ui.ts", "file_type": "code", "source_file": "ui.ts"},
        ],
        "edges": [],
    }
    index = map_graph_to_code_index(graph, tmp_path)
    api = _file(index, "api.py")
    assert api.api_uses["fastapi"] == ["Depends"]
    assert api.api_uses["numpy"] == ["array"]  # usage via the alias
    assert "numpy.array" in api.api_paths["numpy"]
    assert {"fastapi", "numpy"} <= set(api.imports)  # packages fed from the engine too
    ui = _file(index, "ui.ts")
    assert ui.api_uses.get("react") == ["useState"]  # tree-sitter language
