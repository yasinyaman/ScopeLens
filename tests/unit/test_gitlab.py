"""GitLab adapter: pure parsing (no network) + capability declaration + registry wiring."""

import os

import pytest
from etki.adapters.gitlab_work_item import GitlabWorkItemProvider
from etki.adapters.registry import build_work_items
from etki.config import ConnectorConfig


def _provider() -> GitlabWorkItemProvider:
    return GitlabWorkItemProvider("https://gitlab.example.com", "grp/repo", "tok")


def test_gitlab_time_stats_map_to_effort_seconds():
    issue = {
        "iid": 42,
        "title": "Rapora tarih filtresi",
        "description": "reporting modülüne filtre",
        "state": "closed",
        "labels": ["reporting", "backend"],
        "time_stats": {"total_time_spent": 21600, "time_estimate": 28800},
    }
    item = _provider()._to_work_item(issue)
    assert item.id == "42"
    assert item.effort_seconds == 21600  # GitLab is already seconds — identity mapping
    assert item.category == "reporting"  # first label
    assert item.status == "closed"


def test_gitlab_missing_time_stats_default_to_zero():
    item = _provider()._to_work_item({"iid": 7, "title": "x"})
    assert item.effort_seconds == 0
    assert item.category is None


def test_gitlab_project_path_is_url_encoded():
    provider = GitlabWorkItemProvider("https://gitlab.example.com/", "my group/repo", "t")
    assert provider._project == "my%20group%2Frepo"


def test_gitlab_capabilities_declare_effort_tracking():
    caps = _provider().capabilities()
    assert caps.supports_effort_tracking is True
    assert caps.supports_webhooks is True


def test_gitlab_search_params_default_and_narrowed():
    plain = GitlabWorkItemProvider("https://g.example.com", "g/r", "t")
    assert plain._search_params("rapor filtre", 5) == {
        "search": "rapor filtre", "per_page": 5, "state": "closed",
    }
    narrowed = GitlabWorkItemProvider(
        "https://g.example.com", "g/r", "t",
        labels=["efor", "musteri-x"], issue_type="task",
    )
    params = narrowed._search_params("rapor filtre", 3)
    assert params["labels"] == "efor,musteri-x"  # list normalized to GitLab CSV form
    assert params["issue_type"] == "task"


def test_registry_builds_gitlab_from_config(monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "secret-token")
    cfg = ConnectorConfig(
        adapter="gitlab",
        options={
            "base_url": "https://gitlab.example.com",
            "project": "grp/repo",
            "token": "env:GITLAB_TOKEN",
        },
    )
    provider = build_work_items(cfg)
    assert isinstance(provider, GitlabWorkItemProvider)
    assert provider._token == "secret-token"  # env: reference resolved


LIVE = os.environ.get("ETKI_TEST_GITLAB_URL")


@pytest.mark.skipif(not LIVE, reason="live GitLab not configured (ETKI_TEST_GITLAB_URL)")
async def test_gitlab_live_find_similar():  # pragma: no cover — live integration
    provider = GitlabWorkItemProvider(
        LIVE,
        os.environ["ETKI_TEST_GITLAB_PROJECT"],
        os.environ["ETKI_TEST_GITLAB_TOKEN"],
    )
    items = await provider.find_similar("report", limit=3)
    assert isinstance(items, list)
