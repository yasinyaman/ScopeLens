"""Redmine + Azure DevOps adapters: pure parsing, capabilities, registry wiring."""

from etki.adapters.azure_devops_work_item import AzureDevOpsWorkItemProvider
from etki.adapters.redmine_work_item import RedmineWorkItemProvider
from etki.adapters.registry import build_work_items
from etki.config import ConnectorConfig

# --- Redmine ---


def test_redmine_spent_hours_convert_to_effort_seconds():
    issue = {
        "id": 1234,
        "subject": "Rapora tarih filtresi",
        "description": "reporting modülü",
        "status": {"name": "Closed"},
        "tracker": {"name": "Feature"},
        "spent_hours": 6.5,
    }
    item = RedmineWorkItemProvider("https://r.example.com", "key")._to_work_item(issue)
    assert item.id == "1234"
    assert item.effort_seconds == 23400  # 6.5h * 3600
    assert item.category == "Feature"
    assert item.status == "Closed"


def test_redmine_missing_spent_hours_default_to_zero():
    item = RedmineWorkItemProvider("https://r.example.com", "key")._to_work_item(
        {"id": 9, "subject": "x"}
    )
    assert item.effort_seconds == 0
    assert item.category is None


def test_redmine_capabilities_honest_about_webhooks():
    caps = RedmineWorkItemProvider("u", "k").capabilities()
    assert caps.supports_effort_tracking is True
    assert caps.supports_webhooks is False  # stock Redmine: plugins only


# --- Azure DevOps ---


def test_azure_devops_completed_work_hours_convert_to_seconds():
    raw = {
        "id": 77,
        "fields": {
            "System.Title": "Add date filter to report",
            "System.State": "Done",
            "System.WorkItemType": "Task",
            "System.Description": "reporting module",
            "Microsoft.VSTS.Scheduling.CompletedWork": 5.5,
        },
    }
    provider = AzureDevOpsWorkItemProvider("org", "Proj", "pat")
    item = provider._to_work_item(raw)
    assert item.id == "77"
    assert item.effort_seconds == 19800  # 5.5h * 3600
    assert item.category == "Task"


def test_azure_devops_missing_completed_work_defaults_to_zero():
    provider = AzureDevOpsWorkItemProvider("org", "Proj", "pat")
    item = provider._to_work_item({"id": 1, "fields": {"System.Title": "x"}})
    assert item.effort_seconds == 0


def test_azure_devops_capabilities():
    caps = AzureDevOpsWorkItemProvider("o", "p", "t").capabilities()
    assert caps.supports_effort_tracking is True
    assert caps.supports_webhooks is True  # service hooks


# --- registry wiring ---


def test_registry_builds_redmine_and_azure(monkeypatch):
    monkeypatch.setenv("REDMINE_API_KEY", "rk")
    monkeypatch.setenv("AZDO_PAT", "ap")
    redmine = build_work_items(
        ConnectorConfig(
            adapter="redmine",
            options={"base_url": "https://r.example.com", "api_key": "env:REDMINE_API_KEY"},
        )
    )
    azure = build_work_items(
        ConnectorConfig(
            adapter="azure_devops",
            options={"organization": "org", "project": "Proj", "pat": "env:AZDO_PAT"},
        )
    )
    assert isinstance(redmine, RedmineWorkItemProvider)
    assert isinstance(azure, AzureDevOpsWorkItemProvider)
