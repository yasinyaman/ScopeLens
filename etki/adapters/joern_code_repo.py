"""Joern-based CodeRepositoryProvider (reference code-intelligence engine).

Invokes `scripts/joern_index.sh` → CPG → normalized 'code index' JSON → `CodeModule`
graph (via `parse_code_index`, same schema as the AST producer). Requires Joern/JVM;
hence unit tests use the fast AST path, and live Joern indexing runs separately.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from etki.adapters.code_index import CodeIndex, IndexBackedCodeRepository

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_SCRIPT = _REPO_ROOT / "scripts" / "joern_index.sh"


class JoernIndexError(RuntimeError):
    pass


class JoernCodeRepositoryProvider(IndexBackedCodeRepository):
    def __init__(
        self,
        src_root: str | Path,
        *,
        export_path: str | Path | None = None,
        refresh: bool = True,
        script: str | Path | None = None,
        churn: dict[str, int] | None = None,
    ) -> None:
        index = self._produce(
            Path(src_root), export_path, refresh, Path(script or _DEFAULT_SCRIPT)
        )
        super().__init__(index, churn, supports_incremental_diff=True)

    @staticmethod
    def _produce(
        src_root: Path, export_path: str | Path | None, refresh: bool, script: Path
    ) -> CodeIndex:
        out = Path(export_path) if export_path else src_root.parent / "code_index.json"
        if refresh or not out.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
            try:
                subprocess.run(
                    ["bash", str(script), str(src_root), str(out)],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=900,
                )
            except FileNotFoundError as exc:
                raise JoernIndexError("bash veya joern bulunamadı (PATH?)") from exc
            except subprocess.CalledProcessError as exc:
                raise JoernIndexError(
                    f"Joern indeksleme başarısız (exit {exc.returncode}): {exc.stderr[-500:]}"
                ) from exc
        index = CodeIndex.model_validate_json(out.read_text(encoding="utf-8"))
        if not index.dependencies:
            # Manifests are read Python-side (Joern only sees source code).
            from etki.adapters.manifests import parse_manifests

            index.dependencies = parse_manifests(src_root)
        return index
