"""Port of the built-in Linear mapping tests + plugin-contract checks.

The mapping tests mirror tests/unit/test_linear.py in the etki repo — same
payload, same assertions — proving the extraction changed no behavior."""

from etki_api import PluginManifest, WorkItemProvider, load_manifest
from etki_plugin_linear import PLUGIN, LinearOptions, LinearWorkItemProvider

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


# --- Plugin contract ---------------------------------------------------------


def test_spec_builds_a_conformant_provider():
    factory = PLUGIN.adapters[0]
    assert factory.port == "work_items"
    assert factory.name == "linear"
    provider = factory.build(LinearOptions(api_key="lk", hours_per_point=4.0))
    assert isinstance(provider, LinearWorkItemProvider)
    assert isinstance(provider, WorkItemProvider)  # structural Protocol check


def test_manifest_matches_the_spec():
    manifest: PluginManifest = load_manifest(__file__.rsplit("/tests/", 1)[0])
    assert manifest.name == PLUGIN.name
    assert manifest.api_compat == PLUGIN.api_compat
    assert manifest.capabilities == PLUGIN.capabilities
    assert {a.name for a in manifest.adapters} == {a.name for a in PLUGIN.adapters}
    assert {a.port for a in manifest.adapters} == {a.port for a in PLUGIN.adapters}
