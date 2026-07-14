# Demo Request List (for testing)

From the landing screen (`/` = **Projeler**) open a project → **Triyaj** → paste the request → **Triyaj et**. The
decisions/efforts below are **verified live** against the current index (and can serve as a regression
baseline). `demo` and `shop` ship ready in the repo; `warp` is a sample project added through the UI
(English spec/code → an LLM bridge kicks in for Turkish requests).

> **Note on language.** The request strings below are kept **in Turkish on purpose** — the `demo`/`shop`
> demo corpora (contracts and code) are Turkish, so these exact strings reproduce the documented
> decisions. `warp` is an English spec/code project; Turkish requests against it exercise the TR↔EN
> bridge. The UI itself is multilingual (TR/EN/DE) regardless of the request language.

## Decision-type coverage (quick view)

| Decision | Example request | Project |
|---|---|---|
| 🟢 IN-SCOPE | "Aylık satış raporuna tarih filtresi eklensin" | demo |
| 🔴 OUT-OF-SCOPE | "login ekranına SSO entegrasyonu ekle" | demo |
| 🟠 CR CANDIDATE | "Redis önbellek katmanı ekle" | warp |
| ⚪ GRAY AREA | "OpenAPI şemasını katalog meta verisiyle zenginleştir" | warp |
| 🔵 MAINTENANCE | "raporlama modülündeki bir hatayı düzelt" | demo |

---

## demo — Enterprise reporting (CTR-DEMO-001)
*Scope: login/session, reporting (≤5 reports), export, dashboard, ≤2 external integrations, 12 months maintenance. Excluded: SSO, mobile, real-time.*

| Request | Decision | Effort | Basis |
|---|---|---|---|
| Aylık satış raporuna tarih filtresi eklensin | 🟢 IN-SCOPE | 5–7 h | Clause 4.2.1 (Reporting) |
| Üretilen raporları PDF ve Excel olarak dışa aktar | 🟢 IN-SCOPE | 5–7 h | Clause 4.2.2 (Export) |
| Gösterge paneline yeni grafik widget'ı ekle | 🟢 IN-SCOPE | ~10 h | Dashboard |
| raporlama modülündeki bir hatayı düzelt | 🔵 MAINTENANCE | 6–18 h | Clause 8.1 (Maintenance) |
| login ekranına SSO entegrasyonu ekle | 🔴 OUT-OF-SCOPE | 18–25 h | Clause 7.1 (SSO excluded) |
| iOS için mobil uygulama geliştir | 🔴 OUT-OF-SCOPE | — | Clause 7.x (Mobile excluded) |
| gerçek zamanlı veri akışı (websocket) ekle | 🔴 OUT-OF-SCOPE | — | Clause 7.x (Real-time excluded) |
| üçüncü bir dış sisteme daha entegrasyon ekle | 🔴 OUT-OF-SCOPE | 18–25 h | ≤2 integration limit exceeded |

## shop — E-commerce (CTR-SHOP-002)
*Scope: cart/order, card payment, product catalog, 12 months maintenance. Excluded: cryptocurrency, marketplace.*

| Request | Decision | Effort | Basis |
|---|---|---|---|
| ürün kataloğuna marka filtresi ekle | 🟢 IN-SCOPE | 6–7 h | Clause 2.3 (Catalog) |
| sepete indirim kuponu kodu desteği ekle | ⚪ GRAY AREA | ~7 h | LLM-assisted match |
| kripto para (Bitcoin) ile ödeme ekle | 🔴 OUT-OF-SCOPE | 16–24 h | Clause 6.1 (Crypto excluded) |
| pazaryeri satıcı paneli ekle | 🔴 OUT-OF-SCOPE | — | Clause 6.x (Marketplace excluded) |

> The same "crypto payment" request yields a different result in **demo** (which has no such excluded clause) — demonstrating per-project decision behavior.

## warp — Warp Engine (sample, English code/spec)
*Auto-generates a REST CRUD API from a database. For Turkish requests, the TR↔EN bridge + LLM assistance on weak matches kicks in.*

| Request | Decision | Effort | Impact / note |
|---|---|---|---|
| Oracle veritabanı desteği ekle | 🟢 IN-SCOPE | 8–14 h | `database` module (TR↔EN bridge) |
| API uçlarına filtreleme ve sayfalama ekle | ⚪ GRAY AREA | 25–43 h | api, core, database, utils — **[LLM]** |
| çok dilli dokümantasyon üretimi ekle | ⚪ GRAY AREA | 12–21 h | i18n, enrichment, export — **[LLM]** |
| OpenAPI şemasını katalog meta verisiyle zenginleştir | ⚪ GRAY AREA | 41–73 h | catalog, integration, llm, api — **[LLM]** |
| Redis önbellek katmanı ekle | 🟠 CR CANDIDATE | — | not in scope/code → CR |

**[LLM]** = the deterministic match was weak, so Claude performed semantic/cross-lingual matching (the evidence chain shows an "LLM-assisted match" note).

---

## Multi-requirement single request (card splitting + automatic comment)
Write several requirements in one box and hit **Triyaj et** → each requirement becomes a separate card with an assistant comment based on that outcome below it:

> *"Müşteri rapora yeni filtre eklensin, ayrıca login ekranına SSO eklensin, bir de mobil uygulama istedi."* (demo)
> → 3 cards: 🟢 IN-SCOPE (filter) · 🔴 OUT-OF-SCOPE (SSO) · 🔴 OUT-OF-SCOPE (mobile) + a PMO comment.

---

## Settings & roles walkthrough (new screens)

Two extra stops that demo well after the triage flow (both under **Ayarlar / Settings**
in the sidebar — visible to the `pmo` role only):

1. **AI Assistant** — the global LLM provider is configured from the UI: pick
   *off / Anthropic / OpenAI-compatible*, paste a key or an Ollama endpoint, hit
   **Test connection** (a real round-trip). Saving applies immediately — the status
   chip on the Triage screen flips to "active · \<model\>" without a restart. Turn it
   back **off** to show that the decision path stays deterministic: the LLM only adds
   semantic matching on weak matches and pre-analysis prose. (In the Docker demo, a
   host Ollama is reachable as `http://host.docker.internal:11434/v1`.)
2. **Users** — create an `engineer` and a `viewer` right in the UI with a project
   grant, then log in as each in a second browser window: the engineer can run triage
   but gets no approve buttons; the viewer sees a read-only note instead of the triage
   form and only their granted projects in the portfolio. Reset the viewer's password
   while their window is open — their next click lands back on the login screen
   (sessions are token-bound). Approve/reject/CR buttons ask for confirmation before
   committing, since a CR approval bumps the living baseline.

> Efforts are approximate against the current index; they may change with re-indexing / threshold calibration.
