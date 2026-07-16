#!/usr/bin/env python
"""Build a verified-marketplace submission bundle for a plugin — one command.

Produces, under ``<out>/<plugin>/`` (mirroring the ``etki-plugins`` repo layout):

    artifacts/<wheel>                     the built wheel
    reports/<plugin>-<version>.report.json  the conformance report (must be green)
    index-entry.json                      the schema-validated ``IndexPlugin`` entry
    README.md                             where each file goes in the PR

These are exactly the three things a marketplace PR needs
(``docs/writing-an-adapter.md`` §"Distributing your plugin"). The index entry is
validated through the SAME ``parse_index`` the ``etki-plugins`` CI and the app
use, so a bundle that builds here is schema-correct there.

Plugins are distributed on GitHub only (signed index / git), never PyPI — this
just assembles the pieces; the actual PR + signing happens in ``etki-plugins``.

Usage:
    uv run python scripts/build_plugin_submission.py etki-plugin-jira
    uv run python scripts/build_plugin_submission.py etki-plugin-jira \\
        --out dist/submission --source-repo https://github.com/yasinyaman/etki
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from importlib import metadata
from pathlib import Path

from etki.plugin.index_schema import (
    IndexArtifact,
    IndexFile,
    IndexPlugin,
    IndexVersion,
    parse_index,
)

from etki_api.conformance.runner import _load_spec
from etki_api.conformance.runner import run as conformance_run

_DEFAULT_SOURCE_REPO = "https://github.com/yasinyaman/etki"


def _build_wheel(dist_name: str) -> None:
    proc = subprocess.run(
        ["uv", "build", "--package", dist_name], capture_output=True, text=True
    )
    if proc.returncode != 0:
        sys.exit(f"uv build başarısız:\n{proc.stderr.strip()}")


def _find_wheel(dist_name: str, version: str) -> Path:
    stem = f"{dist_name.replace('-', '_')}-{version}-"
    matches = sorted(Path("dist").glob(f"{dist_name.replace('-', '_')}-{version}-*.whl"))
    if not matches:
        sys.exit(f"wheel bulunamadı: dist/{stem}*.whl (önce build edildi mi?)")
    return matches[-1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _metadata_summary(dist_name: str) -> tuple[str, str]:
    """(summary, source_repo) from the package's own metadata — the summary is the
    pyproject ``description``; the source repo comes from a Project-URL if declared."""
    md = metadata.metadata(dist_name)
    summary = md.get("Summary", "") or ""
    source = _DEFAULT_SOURCE_REPO
    for url in md.get_all("Project-URL") or []:
        label, _, value = url.partition(",")
        if label.strip().lower() in ("source", "repository", "homepage"):
            source = value.strip()
            break
    if md.get("Home-page"):
        source = md["Home-page"]
    return summary, source


def build_submission(
    dist_name: str, out_dir: Path, *, source_repo: str | None, released_at: str
) -> Path:
    print(f"[1/4] wheel derleniyor: {dist_name}")
    _build_wheel(dist_name)

    print("[2/4] conformance çalıştırılıyor")
    with tempfile.TemporaryDirectory() as tmp:
        report_tmp = Path(tmp) / "report.json"
        code = conformance_run(dist_name, str(report_tmp))
        if code != 0:
            sys.exit(f"conformance GEÇMEDİ (exit {code}) — market girdisi üretilmez")
        report = json.loads(report_tmp.read_text(encoding="utf-8"))

    version = report["version"]
    api_compat = report["api_compat"]
    wheel = _find_wheel(dist_name, version)
    sha = _sha256(wheel)

    print("[3/4] index girdisi oluşturuluyor + şema doğrulaması")
    spec = _load_spec(dist_name)  # authoritative ports + capability declaration
    summary, meta_source = _metadata_summary(dist_name)
    report_name = f"{dist_name}-{version}.report.json"
    entry = IndexPlugin(
        name=dist_name,
        summary=summary,
        source_repo=source_repo or meta_source,
        ports=[a.port for a in spec.adapters],
        capabilities=spec.capabilities,
        versions=[
            IndexVersion(
                version=version,
                api_compat=api_compat,
                artifact=IndexArtifact(url=f"artifacts/{wheel.name}", sha256=sha),
                conformance_report=f"reports/{report_name}",
                released_at=released_at,
            )
        ],
    )
    # Round-trip through the real validator (the same one etki-plugins CI uses).
    idx = IndexFile(schema_version=1, generated_at="", plugins=[entry])
    reparsed = parse_index(idx.model_dump_json().encode())
    assert reparsed.get(dist_name) is not None, "girdi şema doğrulamasından geçmedi"

    print(f"[4/4] bundle yazılıyor: {out_dir / dist_name}")
    bundle = out_dir / dist_name
    (bundle / "artifacts").mkdir(parents=True, exist_ok=True)
    (bundle / "reports").mkdir(parents=True, exist_ok=True)
    shutil.copy(wheel, bundle / "artifacts" / wheel.name)
    (bundle / "reports" / report_name).write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (bundle / "index-entry.json").write_text(
        entry.model_dump_json(indent=2), encoding="utf-8"
    )
    _write_readme(bundle, dist_name, version, wheel.name, report_name, sha)
    return bundle


def _write_readme(
    bundle: Path, dist_name: str, version: str, wheel: str, report: str, sha: str
) -> None:
    (bundle / "README.md").write_text(
        f"""# {dist_name} {version} → doğrulanmış market teslimi

`scripts/build_plugin_submission.py` ile üretildi. Üçü de şemaya karşı
doğrulandı ve conformance yeşil. `yasinyaman/etki-plugins` reposuna PR için:

| Buradaki dosya | etki-plugins'teki yol |
|---|---|
| `artifacts/{wheel}` | `artifacts/` |
| `reports/{report}` | `reports/` |
| `index-entry.json` | `index.json` → `plugins` dizisine YENİ eleman |

- wheel sha256: `{sha}`
- `artifact.url` index'e görelidir (`artifacts/…whl`) — marketplace onu index
  URL'ine göre `urljoin` ile çözer.
- Merge'de etki-plugins CI şemayı + hash'leri yeniden doğrular, index'i sigstore
  keyless ile yeniden imzalar ve Pages'i yayınlar. PyPI devrede değil.
""",
        encoding="utf-8",
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Plugin market teslim bundle'ı üret")
    ap.add_argument("plugin", help="dağıtım adı, örn. etki-plugin-jira")
    ap.add_argument("--out", default="dist/submission", help="çıktı kök dizini")
    ap.add_argument(
        "--source-repo", default=None, help="index source_repo (varsayılan: paket metadata)"
    )
    ap.add_argument(
        "--released-at",
        default=datetime.date.today().isoformat(),
        help="index released_at (varsayılan: bugün)",
    )
    args = ap.parse_args()
    bundle = build_submission(
        args.plugin, Path(args.out), source_repo=args.source_repo, released_at=args.released_at
    )
    print(f"\n✓ hazır: {bundle}")


if __name__ == "__main__":
    main()
