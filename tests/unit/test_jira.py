"""Jira adapter (pure parsing) + triage gracefully degrading when the remote PM is unreachable."""

from etki.adapters.fakes.code_repo import FakeCodeRepositoryProvider
from etki.adapters.fakes.document import FakeDocumentSourceProvider
from etki.adapters.fakes.seed import SEED_BASELINE
from etki.adapters.jira_work_item import JiraWorkItemProvider
from etki.core.ports import Capabilities
from etki.engine.triage import TriageEngine


def test_jira_parses_timespent_to_effort_seconds():
    provider = JiraWorkItemProvider("https://x.atlassian.net", "e@x.com", "tok")
    issue = {
        "key": "PROJ-12",
        "fields": {
            "summary": "Rapora filtre",
            "status": {"name": "Done"},
            "timespent": 21600,
            "labels": ["raporlama", "musteri-x"],
        },
    }
    item = provider._to_work_item(issue)
    assert item.id == "PROJ-12"
    assert item.effort_seconds == 21600
    assert item.title == "Rapora filtre"
    assert item.category == "raporlama"  # first label = contract category (effort pool)


def test_jira_without_labels_has_no_category():
    provider = JiraWorkItemProvider("https://x.atlassian.net", "e@x.com", "tok")
    item = provider._to_work_item({"key": "P-1", "fields": {"summary": "x"}})
    assert item.category is None


def test_jira_capabilities_declare_effort_tracking():
    caps = JiraWorkItemProvider("u", "e", "t").capabilities()
    assert caps.supports_effort_tracking is True


class _UnavailablePM:
    """An unreachable remote PM environment (Jira/GLPI down)."""

    async def get_work_item(self, item_id: str):
        raise RuntimeError("PM unavailable")

    async def find_similar(self, description: str, *, limit: int = 5):
        raise RuntimeError("PM unavailable")

    def capabilities(self) -> Capabilities:
        return Capabilities()


async def test_triage_degrades_when_pm_unavailable():
    engine = TriageEngine(
        _UnavailablePM(),
        FakeCodeRepositoryProvider(),
        FakeDocumentSourceProvider(),
        SEED_BASELINE.model_copy(deep=True),
    )
    case = await engine.triage("rapora yeni filtre eklensin")  # must not blow up
    assert case.decisions
    assert case.decisions[0].effort_estimate.high >= case.decisions[0].effort_estimate.low