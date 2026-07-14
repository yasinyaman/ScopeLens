import pytest
from etki.adapters.fakes.code_repo import FakeCodeRepositoryProvider
from etki.adapters.fakes.work_item import FakeWorkItemProvider


async def test_find_similar_returns_relevant_items():
    provider = FakeWorkItemProvider()
    results = await provider.find_similar("rapora yeni filtre eklensin")
    assert results
    assert any("filtre" in w.title.lower() for w in results)


async def test_get_work_item_unknown_raises():
    provider = FakeWorkItemProvider()
    with pytest.raises(KeyError):
        await provider.get_work_item("YOK-1")


def test_work_item_capabilities_declare_effort_tracking():
    assert FakeWorkItemProvider().capabilities().supports_effort_tracking is True


async def test_impacted_spreads_to_dependencies():
    repo = FakeCodeRepositoryProvider()
    modules = await repo.get_impacted("auth")
    ids = {m.id for m in modules}
    assert "auth_module" in ids
    assert len(ids) >= 2  # spreads to first-degree neighbors (broad impact)


async def test_impacted_empty_hint_returns_empty():
    assert await FakeCodeRepositoryProvider().get_impacted(None) == []
