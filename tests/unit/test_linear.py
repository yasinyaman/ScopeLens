"""Linear adapter: points→hours convention, zero-effort honesty, registry wiring."""

from etki.adapters.linear_work_item import LinearWorkItemProvider
from etki.adapters.registry import build_work_items
from etki.config import ConnectorConfig

_ISSUE = {
    "identifier": "ENG-42",
    "title": "Add CSV export",
    "description": "export orders as csv",
    "estimate": 3,
    "state": {"name": "Done"},
    "labels": {"nodes": [{"name": "Feature"}]},
}


def test_estimate_converts_via_declared_hours_per_point():
    item = LinearWorkItemProvider("key", hours_per_point=4.0)._to_work_item(_ISSUE)
    assert item.id == "ENG-42"
    assert item.effort_seconds == 43200  # 3 points * 4h * 3600
    assert item.category == "Feature"
    assert item.status == "Done"


def test_no_convention_means_zero_effort():
    item = LinearWorkItemProvider("key")._to_work_item(_ISSUE)
    assert item.effort_seconds == 0


def test_missing_estimate_defaults_to_zero():
    issue = {**_ISSUE, "estimate": None}
    item = LinearWorkItemProvider("key", hours_per_point=4.0)._to_work_item(issue)
    assert item.effort_seconds == 0


def test_capabilities_reflect_the_convention():
    assert LinearWorkItemProvider("k").capabilities().supports_effort_tracking is False
    assert (
        LinearWorkItemProvider("k", hours_per_point=4.0)
        .capabilities()
        .supports_effort_tracking
        is True
    )


def test_registry_builds_linear(monkeypatch):
    monkeypatch.setenv("LINEAR_API_KEY", "lk")
    provider = build_work_items(
        ConnectorConfig(
            adapter="linear",
            options={"api_key": "env:LINEAR_API_KEY", "hours_per_point": 4},
        )
    )
    assert isinstance(provider, LinearWorkItemProvider)
