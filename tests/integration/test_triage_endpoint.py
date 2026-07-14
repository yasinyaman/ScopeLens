"""PHASE 0 EXIT GATE.

With fake data, POST /triage returns a valid CaseFile end-to-end: 2 sub-requests,
one IN-SCOPE and one OUT-OF-SCOPE, each decision carrying evidence + a range estimate.
"""

from fastapi.testclient import TestClient

from tests.fixtures.sample_request import FILTER_AND_SSO


def test_health_ok(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_triage_endpoint_returns_full_casefile(client: TestClient):
    response = client.post("/triage", json={"request_text": FILTER_AND_SSO})
    assert response.status_code == 200
    case = response.json()

    assert len(case["sub_requests"]) == 2
    assert len(case["decisions"]) == 2

    decisions = {d["decision"] for d in case["decisions"]}
    assert "IN_SCOPE" in decisions
    assert "OUT_OF_SCOPE" in decisions

    assert case["status"] == "PENDING"  # the decision rests with PMO (copilot, not autopilot)

    for d in case["decisions"]:
        est = d["effort_estimate"]
        assert est["low"] <= est["high"]  # always a range
        assert d["evidence"]["checked_against"]  # evidence chain is populated
        assert d["index_freshness"]  # freshness stamp


def test_triage_validation_rejects_empty_text(client: TestClient):
    response = client.post("/triage", json={"request_text": ""})
    assert response.status_code == 422
