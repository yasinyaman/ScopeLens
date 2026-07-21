"""HITL approval flow + audit trail + RBAC + override KPI (API level, in-memory repo)."""

from etki.api.context import AppContext
from fastapi.testclient import TestClient


def _triage(client: TestClient, text: str) -> str:
    return client.post("/triage", json={"request_text": text}).json()["request_id"]


def test_triage_persists_and_starts_audit_chain(client: TestClient):
    cid = _triage(client, "login ekranına SSO entegrasyonu")
    assert client.get(f"/casefiles/{cid}").status_code == 200
    audit = client.get(f"/casefiles/{cid}/audit").json()
    assert any(e["action"] == "TRIAGED" for e in audit)


def test_convert_to_cr_bumps_living_baseline(client: TestClient, app_context: AppContext):
    cid = _triage(client, "login ekranına SSO entegrasyonu")
    before = app_context.engines["demo"].baseline.version
    resp = client.post(
        f"/casefiles/{cid}/decisions/0/action",
        json={"action": "CONVERT_TO_CR"},
    )
    assert resp.status_code == 200
    assert app_context.engines["demo"].baseline.version == before + 1
    audit = client.get(f"/casefiles/{cid}/audit").json()
    actions = {e["action"] for e in audit}
    assert {"TRIAGED", "CONVERT_TO_CR", "BASELINE_BUMP"} <= actions  # reconstructable


def test_decide_stamps_decided_at_with_ruling_time(
    client: TestClient, app_context: AppContext
):
    """decided_at is None while PENDING and gets the PMO ruling time on a
    terminal action (disputed.md orders by this value)."""
    cid = _triage(client, "login ekranına SSO entegrasyonu")
    assert app_context.repo.get_case(cid).decisions[0].decided_at is None
    client.post(f"/casefiles/{cid}/decisions/0/action", json={"action": "APPROVE"})
    ruled = app_context.repo.get_case(cid).decisions[0]
    assert ruled.decided_at is not None  # ruling time, stamped by decide()


def test_rbac_blocks_non_pmo_approval(client: TestClient, auth_role: dict):
    cid = _triage(client, "rapora yeni filtre eklensin")  # triage happens while role is pmo
    auth_role["role"] = "viewer"  # session role is not PMO → approval must be denied
    resp = client.post(
        f"/casefiles/{cid}/decisions/0/action",
        json={"action": "APPROVE"},
    )
    assert resp.status_code == 403


def test_override_feeds_next_triage_with_precedent_note(client: TestClient):
    """Closed loop end-to-end: a PMO override refreshes the engine's live clause
    memory, so the NEXT triage on the same clause carries the informational note
    in its evidence chain (never changing the decision itself)."""
    cid = _triage(client, "rapora yeni filtre eklensin")
    client.post(
        f"/casefiles/{cid}/decisions/0/action",
        json={"action": "REJECT", "override_decision": "OUT_OF_SCOPE"},
    )
    again = client.post(
        "/triage", json={"request_text": "rapora yeni filtre eklensin"}
    ).json()
    assumptions = again["decisions"][0]["evidence"]["assumptions"]
    assert any("Madde hafızası" in a for a in assumptions)
    assert any("karara etkisiz" in a for a in assumptions)  # the non-signal wording


def test_override_tracked_in_kpi(client: TestClient):
    cid = _triage(client, "rapora yeni filtre eklensin")  # system: IN_SCOPE
    client.post(
        f"/casefiles/{cid}/decisions/0/action",
        json={"action": "APPROVE", "override_decision": "CR_CANDIDATE"},  # PMO corrects it
    )
    kpi = client.get("/kpi").json()
    assert kpi["override_count"] >= 1
    assert kpi["override_rate"] > 0
