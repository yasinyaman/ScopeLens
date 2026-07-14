"""A1: the living baseline is NOT lost on restart/reindex (DB ↔ index.json reconciliation).

Scenario: a CR approval writes baseline v+1 to the DB. After a restart (reloading the
index from disk) and a reindex (fresh extraction from documents) the approved CR item +
version must survive — otherwise the audit trail would say "BASELINE_BUMP vN" while the
engine reverted to v1.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from etki.api.context import AppContext, index_project, merge_db_baseline
from etki.config import ProjectConfig, Settings
from etki.core.models import Index, ScopeItem
from etki.engine.triage import TriageEngine
from etki.hitl.service import ApprovalService
from etki.indexing.engine import load_index, save_index
from etki.persistence.db import build_repository
from etki.persistence.memory_repo import InMemoryCaseFileRepository


@pytest.fixture
def project(tmp_path: Path) -> ProjectConfig:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "contract.md").write_text(
        "## Madde 1.1 — Raporlama\n\n"
        "Raporlama ekranı ve tarih filtreleri kapsam dahilindedir.\n",
        encoding="utf-8",
    )
    return ProjectConfig(
        id="t1",
        name="Test Projesi",
        contract_id="CTR-T1",
        index_path=str(tmp_path / "index-{id}.json"),
        doc_root=str(docs),
    )


def _cr_item(contract_id: str) -> ScopeItem:
    return ScopeItem(
        id="CR-REQ-t1-abc-0",
        contract_id=contract_id,
        description="(CR onayı) Kripto ödeme entegrasyonu eklenecek.",
        category="cr",
        source_clause="CR-REQ-t1-abc",
    )


def test_baseline_survives_restart_and_reindex(project: ProjectConfig, tmp_path: Path):
    settings = Settings(db_url=f"sqlite:///{tmp_path}/db.sqlite")
    repo = build_repository(settings.db_url)

    # 1) First indexing: v1 baseline from the document.
    index = asyncio.run(index_project(project, settings, repo))
    assert index.baseline.version == 1
    doc_item_ids = {i.id for i in index.baseline.scope_items}
    assert doc_item_ids  # at least one item was extracted from the document

    # 2) CR approval → v2 is written to the DB (the DB leg of the flow in hitl/service.py).
    item = _cr_item(project.contract_id)
    bumped = index.baseline.model_copy(deep=True)
    bumped.scope_items.append(item)
    bumped.version += 1
    bumped.locked_at = datetime.now(UTC)
    repo.save_baseline_version(bumped, source_case_id="REQ-t1-abc")

    # 3) RESTART simulation: the index is loaded from disk (v1), reconciled with DB → v2 + CR.
    restored = load_index(project.resolved_index_path())
    assert restored is not None
    assert restored.baseline.version == 1  # disk is still stale
    changed = merge_db_baseline(restored, repo.latest_baseline(project.contract_id))
    assert changed
    assert restored.baseline.version == 2
    assert item.id in {i.id for i in restored.baseline.scope_items}

    # 4) REINDEX: fresh extraction from documents; the approved CR in the DB is still kept.
    reindexed = asyncio.run(index_project(project, settings, repo))
    ids = {i.id for i in reindexed.baseline.scope_items}
    assert item.id in ids  # approved CR not clobbered
    assert doc_item_ids <= ids  # fresh document items are in place too
    assert reindexed.baseline.version == 2
    # Disk is in sync too (the next restart sees the correct version).
    on_disk = load_index(project.resolved_index_path())
    assert on_disk is not None and on_disk.baseline.version == 2


def test_merge_db_baseline_noop_when_db_not_newer(project: ProjectConfig):
    idx = Index(baseline=_baseline(project.contract_id, version=3))
    assert merge_db_baseline(idx, None) is False
    assert merge_db_baseline(idx, _baseline(project.contract_id, version=3)) is False
    assert idx.baseline.version == 3


def _baseline(contract_id: str, *, version: int):
    from etki.core.models import Baseline

    return Baseline(contract_id=contract_id, version=version, scope_items=[])


def test_apply_baseline_bump_syncs_index_json(
    engine: TriageEngine, tmp_path: Path
) -> None:
    """A CR approval bumps the engine + index.json TOGETHER (single AppContext method)."""
    path = tmp_path / "index-demo.json"
    index = Index(baseline=engine.baseline, indexed_at=datetime.now(UTC), freshness="test")
    save_index(index, path)
    repo = InMemoryCaseFileRepository()
    ctx = AppContext(
        engines={"demo": engine},
        consumed={"demo": {}},
        projects=[{"id": "demo", "name": "Demo"}],
        repo=repo,
        approval=ApprovalService(repo),
        default_project="demo",
        user_store=None,  # type: ignore[arg-type] — unused in this test
        indexes={"demo": index},
        index_paths={"demo": str(path)},
    )
    before = engine.baseline.version
    version = ctx.apply_baseline_bump("demo", _cr_item(engine.baseline.contract_id))
    assert version == before + 1
    on_disk = load_index(path)
    assert on_disk is not None
    assert on_disk.baseline.version == before + 1
    assert "CR-REQ-t1-abc-0" in {i.id for i in on_disk.baseline.scope_items}
