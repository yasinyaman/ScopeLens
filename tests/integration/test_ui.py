"""Regained HTMX flows: Triage, Analysis, Approvals (case-file review+approve), Reports.

Covers both the happy path and graceful degradation (large/corrupt uploads) as well as
RBAC (approval requires pmo).
"""

import etki.api.web as web
from fastapi.testclient import TestClient


def test_ui_triage_survives_llm_failure(client: TestClient, monkeypatch) -> None:
    # LLM is "configured" but the call blows up → cards must still render, no 500.
    monkeypatch.setattr(web, "build_llm_client", lambda settings: object())

    async def _boom(*args, **kwargs):
        raise RuntimeError("LLM erişilemiyor")

    monkeypatch.setattr(web, "agent_ask", _boom)
    r = client.post("/ui/triage", data={"request_text": "rapora yeni filtre", "project_id": "demo"})
    assert r.status_code == 200
    assert "card" in r.text  # cards rendered even without commentary


def test_ui_case_chat_survives_llm_failure(client: TestClient, monkeypatch) -> None:
    async def _boom(*args, **kwargs):
        raise RuntimeError("LLM erişilemiyor")

    monkeypatch.setattr(web, "agent_ask", _boom)
    r = client.post(
        "/ui/case-chat", data={"question": "neden CR?", "project_id": "demo", "context": "özet"}
    )
    assert r.status_code == 200
    assert "yanıt veremedi" in r.text  # Turkish error fragment, not a 500


def test_projects_list_renders(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "demo" in r.text or "Demo" in r.text  # landing page = project list


def test_project_subpages_render(client: TestClient) -> None:
    # Project-centric subpages (replacing the old global /triyaj, /onaylar, /raporlar).
    assert client.get("/projeler/demo").status_code == 200  # Summary
    assert client.get("/projeler/demo/triyaj").status_code == 200
    assert client.get("/projeler/demo/raporlar").status_code == 200
    assert client.get("/projeler/demo/onaylar").status_code == 200
    assert client.get("/projeler/demo/gecmis").status_code == 200
    assert client.get("/projeler/demo/gecmis?filtre=analiz").status_code == 200
    # The old Analyses page is now a History tab; the old URL redirects to it.
    r = client.get("/projeler/demo/analizler")
    assert r.status_code == 200 and r.url.path.endswith("/gecmis")
    assert client.get("/projeler/demo/akis").status_code == 200
    files = client.get("/projeler/demo/dosyalar")
    assert files.status_code == 200  # file/settings management
    assert "Alan profili" in files.text  # LLM / language & domain profile card


def test_sankey_data_has_request_node(client: TestClient) -> None:
    client.post("/triage", json={"request_text": "login ekranına SSO entegrasyonu"})
    r = client.get("/projeler/demo/akis")
    assert r.status_code == 200
    assert '"nodes"' in r.text and '"links"' in r.text  # embedded sankey data
    assert '"layer": 0' in r.text  # at least one request node


def test_approved_case_appears_in_analyses_tab(client: TestClient) -> None:
    cid = client.post("/triage", json={"request_text": "rapora yeni filtre"}).json()["request_id"]
    # While pending, the case sits in the approval queue.
    assert cid in client.get("/projeler/demo/onaylar").text
    # Approve all decisions → case.status APPROVE → analysis tab, out of the queue.
    case = client.get(f"/ui/casefiles/{cid}")
    n = case.text.count("/approve")
    for i in range(max(n, 1)):
        client.post(f"/ui/casefiles/{cid}/decisions/{i}/approve")
    r = client.get("/projeler/demo/gecmis?filtre=analiz")
    assert r.status_code == 200
    assert cid in r.text  # approved case listed as an analysis
    assert cid not in client.get("/projeler/demo/onaylar").text  # decided → left the queue
    assert cid in client.get("/projeler/demo/gecmis").text  # but stays in history


def test_override_shows_clause_memory_strip(client: TestClient) -> None:
    cid = client.post("/triage", json={"request_text": "rapora yeni filtre"}).json()["request_id"]
    before = client.get(f"/ui/casefiles/{cid}")
    assert "cf-memory" not in before.text  # no memory yet — the strip stays silent
    # PMO corrects the system's recommendation → override recorded → memory speaks.
    r = client.post(
        f"/casefiles/{cid}/decisions/0/action",
        json={"action": "REJECT", "override_decision": "OUT_OF_SCOPE"},
    )
    assert r.status_code == 200
    detail = client.get(f"/ui/casefiles/{cid}")
    assert "cf-memory" in detail.text  # the strip rendered
    assert "→OUT_OF_SCOPE" in detail.text  # the system→human correction summary


def test_memory_screen_lists_precedents_from_db(client: TestClient) -> None:
    cid = client.post("/triage", json={"request_text": "rapora yeni filtre"}).json()["request_id"]
    client.post(
        f"/casefiles/{cid}/decisions/0/action",
        json={"action": "REJECT", "override_decision": "OUT_OF_SCOPE"},
    )
    r = client.get("/projeler/demo/hafiza")
    assert r.status_code == 200
    assert cid in r.text  # precedent card links back to the case
    # Test context has no wiki configured → the DB-backed cards still render.
    assert "ETKI_WIKI_DIR" in r.text


def test_deps_compare_fragment_is_online_gated(client: TestClient) -> None:
    r = client.get(
        "/projeler/demo/bagimliliklar/karsilastir",
        params={"package": "requests", "old": "1.0", "new": "2.0"},
    )
    assert r.status_code == 200
    assert "ETKI_DEPS_ONLINE" in r.text  # off in tests → explanatory message


def test_unknown_project_redirects_home(client: TestClient) -> None:
    r = client.get("/projeler/yok/triyaj", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"


def test_chat_turn_persists_to_case(client: TestClient, monkeypatch) -> None:
    # A successful pre-analysis chat turn must be saved to the case and shown in the casefile.
    async def _answer(*args, **kwargs):
        return "**Yanıt:** efor düşük."

    monkeypatch.setattr(web, "agent_ask", _answer)
    cid = client.post("/triage", json={"request_text": "rapora yeni filtre"}).json()["request_id"]
    r = client.post(
        "/ui/case-chat",
        data={"question": "neden kapsam içi?", "project_id": "demo",
              "context": "özet", "case_id": cid},
    )
    assert r.status_code == 200
    detail = client.get(f"/ui/casefiles/{cid}")
    assert "Ön Analiz Sohbeti" in detail.text
    assert "neden kapsam içi?" in detail.text  # question saved
    assert "efor düşük" in detail.text  # assistant answer saved


def test_pre_analysis_persists(client: TestClient) -> None:
    cid = client.post("/triage", json={"request_text": "rapora yeni filtre"}).json()["request_id"]
    r = client.post(
        f"/projeler/demo/triyaj/{cid}/on-analiz", data={"pre_analysis": "ön analiz özeti metni"}
    )
    assert r.status_code == 200
    # The pre-analysis is visible when the case is reopened (JSON payload round-trip).
    detail = client.get(f"/ui/casefiles/{cid}")
    assert detail.status_code == 200
    assert "ön analiz özeti metni" in detail.text
    assert "Ön Analiz" in detail.text


def test_casefile_shows_decisions_before_pre_analysis(client: TestClient) -> None:
    # PMO persona: the approval screen opens with the decision cards; the developer
    # pre-analysis sits below in a collapsed accordion.
    cid = client.post("/triage", json={"request_text": "rapora yeni filtre"}).json()["request_id"]
    client.post(
        f"/projeler/demo/triyaj/{cid}/on-analiz", data={"pre_analysis": "ön analiz özeti metni"}
    )
    body = client.get(f"/ui/casefiles/{cid}").text
    # The decision band ('summary sum-…') renders before the pre-analysis accordion.
    assert body.index("summary sum-") < body.index("Ön Analiz")


def test_single_decision_case_flow_is_collapsed(client: TestClient) -> None:
    # A one-decision, one-clause triage renders the flow graph inside a closed accordion.
    r = client.post("/ui/triage", data={"request_text": "rapora yeni filtre", "project_id": "demo"})
    assert r.status_code == 200
    if '"layer": 1' in r.text and r.text.count('"layer": 1') < 2:
        assert 'id="case-flow-acc"' in r.text


def test_fmt_hours_filter() -> None:
    assert web.fmt_hours(None) == "—"
    assert web.fmt_hours(0.03) == "≈2 dk"
    assert web.fmt_hours(12) == "12 sa"


def test_clause_detail_screen(client: TestClient) -> None:
    import re

    # The Özet scope list links every clause to its detail page.
    detail = client.get("/projeler/demo").text
    m = re.search(r'href="(/projeler/demo/madde/[^"]+)"', detail)
    assert m is not None
    r = client.get(m.group(1))
    assert r.status_code == 200
    assert "Madde Detayı" in r.text
    # Unknown clause degrades to the summary, not a 500.
    r = client.get("/projeler/demo/madde/YOK-999")
    assert r.status_code == 200 and r.url.path == "/projeler/demo"


def test_clause_detail_lists_citing_case(client: TestClient) -> None:
    cid = client.post("/triage", json={"request_text": "rapora yeni filtre"}).json()["request_id"]
    case = client.get(f"/casefiles/{cid}").json()
    cited = case["decisions"][0]["evidence"].get("cited_clauses") or []
    if cited:  # deterministic corpus cites a clause → its detail lists the case
        r = client.get(f"/projeler/demo/madde/{cited[0]['id']}")
        assert r.status_code == 200
        assert cid in r.text


def test_module_table_screen(client: TestClient) -> None:
    cid = client.post("/triage", json={"request_text": "rapora yeni filtre"}).json()["request_id"]
    r = client.get("/projeler/demo/moduller")
    assert r.status_code == 200
    assert "Kod Modülleri" in r.text
    assert cid in r.text  # the triaged case shows under its impacted module(s)


def test_history_decision_type_filter(client: TestClient) -> None:
    cid = client.post("/triage", json={"request_text": "rapora yeni filtre"}).json()["request_id"]
    case = client.get(f"/casefiles/{cid}").json()
    decision = case["decisions"][0]["decision"]
    r = client.get(f"/projeler/demo/gecmis?karar={decision}")
    assert r.status_code == 200
    assert cid in r.text  # matching case listed
    # A decision type this case does NOT have filters it out; bogus values are ignored.
    other = "MAINTENANCE" if decision != "MAINTENANCE" else "OUT_OF_SCOPE"
    if all(d["decision"] != other for d in case["decisions"]):
        assert cid not in client.get(f"/projeler/demo/gecmis?karar={other}").text
    assert client.get("/projeler/demo/gecmis?karar=SAÇMA").status_code == 200


def test_pool_breakdown_fragment(client: TestClient) -> None:
    detail = client.get("/projeler/demo").text
    import re

    m = re.search(r'hx-get="(/projeler/demo/havuz/[^"]+)"', detail)
    if m:  # a pool exists in the corpus → the fragment lists items or the empty message
        r = client.get(m.group(1))
        assert r.status_code == 200
        assert ("sa" in r.text) or ("iş kaydı" in r.text)
    # Unknown category is a graceful empty fragment, not a 500.
    assert client.get("/projeler/demo/havuz/yok-kategori").status_code == 200


def test_baseline_timeline_records_cr_bump(client: TestClient) -> None:
    r = client.get("/projeler/demo/baseline")
    assert r.status_code == 200
    assert "Baseline Sürüm Geçmişi" in r.text
    # Approve a CR → the timeline gains a version entry linking back to the case.
    cid = client.post("/triage", json={"request_text": "rapora yeni filtre"}).json()["request_id"]
    client.post(f"/casefiles/{cid}/decisions/0/action", json={"action": "CONVERT_TO_CR"})
    after = client.get("/projeler/demo/baseline").text
    assert cid in after  # source-case link rendered


def test_ask_screen_and_graph_query(client: TestClient) -> None:
    r = client.get("/projeler/demo/sor")
    assert r.status_code == 200
    assert "ask-thread" in r.text  # single chat-style input
    r = client.post("/ui/ask", data={"question": "rapor filtresi", "project_id": "demo"})
    assert r.status_code == 200
    assert "BİLGİ GRAFİĞİ" in r.text  # deterministic answer labeled with its source
    assert "Strateji" in r.text
    # LLM off in tests → no auto-loading AI stub in the turn.
    assert "/ui/ask-llm" not in r.text
    # The turn is recorded in the process log (question → strategy → nodes).
    from etki.process_log import read_events

    asks = [e for e in read_events() if e.get("kind") == "ask"]
    assert asks and asks[-1]["question"] == "rapor filtresi"
    assert "strategy" in asks[-1] and "nodes" in asks[-1]


def test_ask_llm_fragment_is_labeled_and_grounded(client: TestClient, monkeypatch) -> None:
    prompts: list[str] = []

    async def _answer(prompt, *args, **kwargs):
        prompts.append(prompt)
        return "**Yanıt:** kapsam içi."

    monkeypatch.setattr(web, "agent_ask", _answer)
    r = client.post(
        "/ui/ask-llm",
        data={"question": "SSO kapsamda mı?", "project_id": "demo",
              "context": "strategy: find_k\n- scope:SCOPE-006: SSO hariç"},
    )
    assert r.status_code == 200
    assert "YAPAY ZEKÂ" in r.text  # AI answer labeled with its source
    assert "kapsam içi" in r.text
    assert "deterministik yanıt bağlam olarak verildi" in r.text  # grounding note
    assert "SCOPE-006" in prompts[0]  # the graph answer reached the model as context


def test_ui_triage_renders_cards(client: TestClient) -> None:
    r = client.post("/ui/triage", data={"request_text": "rapora yeni filtre", "project_id": "demo"})
    assert r.status_code == 200
    assert "card" in r.text  # decision cards rendered
    assert "/ui/casefiles/" in r.text  # link to the case file


def test_auto_pre_analysis_on_triage(client: TestClient) -> None:
    # LLM off (hermetic) → triage must auto-generate a DETERMINISTIC pre-analysis and save it.
    r = client.post("/ui/triage", data={"request_text": "rapora yeni filtre", "project_id": "demo"})
    assert r.status_code == 200
    assert "Ön Analiz (otomatik)" in r.text
    cid = r.text.split('/triyaj/')[1].split('/on-analiz')[0]
    detail = client.get(f"/ui/casefiles/{cid}")
    assert "Otomatik ön analiz" in detail.text  # deterministic heading saved to the case


def test_document_preview(client: TestClient) -> None:
    import re
    import urllib.parse

    page = client.get("/projeler/demo/dosyalar").text
    m = re.search(r'onizle\?doc=([^"&]+)', page)
    assert m is not None  # demo has source documents → Preview button
    doc = urllib.parse.unquote(m.group(1))
    r = client.get("/projeler/demo/dosyalar/onizle", params={"doc": doc})
    assert r.status_code == 200
    assert "önizleme" in r.text  # preview fragment (content shown)


def test_document_preview_unknown_is_graceful(client: TestClient) -> None:
    r = client.get("/projeler/demo/dosyalar/onizle", params={"doc": "yok.md"})
    assert r.status_code == 200  # not a 500
    assert "bulunamadı" in r.text


def test_ui_analyze_rejects_too_large(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("ETKI_MAX_UPLOAD_MB", "0")  # every file exceeds the limit
    files = {"file": ("buyuk.txt", b"x" * 2048, "text/plain")}
    r = client.post("/ui/analyze", data={"project_id": "demo", "mode": "triage"}, files=files)
    assert r.status_code == 200
    assert "çok büyük" in r.text


def test_ui_analyze_corrupt_upload_is_graceful(client: TestClient) -> None:
    files = {"file": ("bozuk.pdf", b"%PDF-1.4 not really a pdf", "application/pdf")}
    r = client.post("/ui/analyze", data={"project_id": "demo", "mode": "triage"}, files=files)
    assert r.status_code == 200  # not a 500, Turkish error fragment


def test_casefile_review_and_pmo_approve(client: TestClient) -> None:
    cid = client.post("/triage", json={"request_text": "login ekranına SSO entegrasyonu"}).json()[
        "request_id"
    ]
    assert client.get(f"/ui/casefiles/{cid}").status_code == 200
    r = client.post(f"/ui/casefiles/{cid}/decisions/0/approve")
    assert r.status_code == 200
    assert "Onayland" in r.text or "card" in r.text  # updated body returned


def test_ui_approve_requires_pmo(client: TestClient, auth_role: dict) -> None:
    cid = client.post("/triage", json={"request_text": "rapora yeni filtre"}).json()["request_id"]
    auth_role["role"] = "viewer"  # not PMO → approval denied
    r = client.post(f"/ui/casefiles/{cid}/decisions/0/approve")
    assert r.status_code == 403


def test_search_matches_case(client: TestClient) -> None:
    client.post("/triage", json={"request_text": "login ekranına SSO entegrasyonu"})
    r = client.get("/ara", params={"q": "SSO"})
    assert r.status_code == 200
    assert "/ui/casefiles/" in r.text  # matching request linked


def test_search_empty_query_renders(client: TestClient) -> None:
    assert client.get("/ara").status_code == 200


def test_new_project_form_for_pmo(client: TestClient) -> None:
    assert client.get("/yeni-proje").status_code == 200


def test_new_project_form_requires_pmo(client: TestClient, auth_role: dict) -> None:
    auth_role["role"] = "viewer"
    assert client.get("/yeni-proje").status_code == 403


def test_report_docx_download(client: TestClient) -> None:
    cid = client.post("/triage", json={"request_text": "rapora yeni filtre"}).json()["request_id"]
    r = client.get(f"/ui/casefiles/{cid}/report.docx")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument"
    )


def test_corrupt_docx_upload_is_a_helpful_400_not_500(client: TestClient) -> None:
    r = client.post(
        "/projeler/demo/dosyalar/upload",
        files={"files": ("bozuk.docx", b"this is not a zip container", "application/octet-stream")},
    )
    assert r.status_code == 400  # DocumentUnreadable → form error, not a bare 500


def test_workitem_form_never_echoes_stored_secrets(client: TestClient, monkeypatch) -> None:
    # projects_store.get is monkeypatched: the REAL config/projects.yaml must
    # never be written by a test (it is the developer's live config).
    from etki import projects_store

    hacked = projects_store.get("demo").model_copy(deep=True)
    hacked.connectors.work_items.adapter = "jira"
    hacked.connectors.work_items.options = {
        "base_url": "https://x.atlassian.net", "email": "a@b.c",
        "api_token": "SUPER-SECRET-TOKEN", "jql": "project=X",
    }
    monkeypatch.setattr(projects_store, "get", lambda pid: hacked if pid == "demo" else None)
    r = client.get("/projeler/demo/ayarlar/work-items/form", params={"adapter": "jira"})
    assert r.status_code == 200
    assert "SUPER-SECRET-TOKEN" not in r.text  # masked in typed fields
    raw = client.get(
        "/projeler/demo/ayarlar/work-items/form", params={"adapter": "jira", "mode": "raw"}
    )
    assert "SUPER-SECRET-TOKEN" not in raw.text  # and in the raw textarea
