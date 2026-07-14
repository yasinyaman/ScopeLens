import pytest
from etki.adapters.file_work_item import FileWorkItemProvider

PATH = "samples/demo_project/work_items.json"


async def test_loads_and_normalizes_effort_seconds():
    provider = FileWorkItemProvider(PATH)
    item = await provider.get_work_item("WI-101")
    assert item.effort_seconds == 21600


async def test_find_similar_matches_keywords():
    provider = FileWorkItemProvider(PATH)
    results = await provider.find_similar("rapora filtre")
    assert results
    assert any("rapor" in f"{w.title} {w.description}".lower() for w in results)


async def test_unknown_work_item_raises():
    with pytest.raises(KeyError):
        await FileWorkItemProvider(PATH).get_work_item("YOK-999")


def test_capabilities_declare_effort_tracking():
    assert FileWorkItemProvider(PATH).capabilities().supports_effort_tracking is True
