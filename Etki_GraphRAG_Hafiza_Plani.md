# Etki — GraphRAG Hafıza Katmanı Planı (v0.2, revize)

> **Hedef:** Triage motoruna kapalı döngü hafıza eklemek — karar gerekçeleri (wiki), çoklu retrieval yolları (query port), HITL geri yazımı (ingest loop) ve subgraph rerank.
>
> **Öncelik sırası:** Faz 1 Wiki → Faz 2 Query Port → Faz 3 Ingest Loop → Faz 4 Subgraph Rerank (ops.)
>
> **Toplam tahmin:** ~5 hafta part-time (akşam/hafta sonu temposu). v0.1'deki 6-8 hafta, depo gerçekleriyle karşılaştırma sonrası küçüldü: rerank port+adapter zaten mevcut, Faz 3 Celery'siz sadeleşti.

## v0.1 → v0.2 değişiklikleri (depo denetimi, 2026-07-09)

| v0.1 varsayımı | Depo gerçeği | v0.2 kararı |
|---|---|---|
| Faz 4: `RerankerPort` + `CrossEncoderReranker` sıfırdan yazılacak | `adapters/rerank_tei.py` (TEI, bge-reranker-v2-m3) + `RerankProvider` portu **zaten motora bağlı** (`rerank_strong=-6.8`, endpoint yoksa sessiz atlama = Noop davranışı) | Faz 4 yalnızca **subgraph packing entegrasyonu + A/B eval** olarak küçüldü (4 g → 1,5 g) |
| 2.2: embedding retrieval yeni yetenek | `EmbeddingProvider` motora bağlı (`embed_strong/embed_weak`); **ölçülmüş ders:** bi-encoder parafraz-IN vs yeni-yetenek-CR ayıramıyor → include tarafında karar değiştiremez | `find_k_nodes` yalnız **aday getirme** yapar, karar sinyali olamaz; bge-m3'e geçişte aynı ölçüm tekrarlanır |
| 2.4: NL → Cypher | Graph DB yok; kod grafiği JSON `Index` + `IndexTools` | `nl_query` = **LLM → IndexTools tool-call** (agent.py deseninin porta adaptasyonu); Cypher yok |
| 3.2: Celery task | workers=1 zorunlu (`_enforce_single_worker`), kuyruk/Redis yok; yerleşik desen `app.py` asyncio background loop'ları | Ingest **senkron çağrı + `asyncio.create_task`**; idempotency (dedup anahtarı) aynen korunur |
| 3.3/3.5: override tespiti + metrik yazılacak | `repo.list_overrides`, `kpi.override_rate`, `calibration_suggestions` **zaten var** | Faz 3'ün yeni kısmı yalnız **geri yazım** (wiki/precedents + embedding refresh) |
| Kesişen iş: "Etki rename bitirilmeli" | Rename tamamlandı (paket `etki/`, `.etki/`, repo `yasinyaman/etki`) | Madde düştü; bekleyen tek şey PyPI trusted publisher |

## Tasarım ilkeleri (fazlar-üstü, ihlal etme)

- **Wiki = DB'nin projeksiyonu, asla ikinci doğruluk kaynağı değil.** Kararlar DB'de kanıt zinciriyle donmuş durumda; wiki tamamı silinip DB'den yeniden üretilebilir olmalı (`etki wiki rebuild`). Tek yazıcı: Faz 1'de triage hook'u, Faz 3'ten itibaren ingest fonksiyonu. Elle edit yok → değişiklik PR ile.
- **Çoklu-proje:** wiki dizini proje-başına — `.etki/wiki-{project_id}/` (index dosyalarının `index-{id}.json` desenine paralel). `delete_project` davranışı Faz 1'de kararlaştırılır (öneri: DB vaka geçmişi gibi wiki de korunur — audit trail tutarlılığı).
- **KVKK:** talep metinleri git-versiyonlanabilir markdown'a düşecek; `docs/KVKK.md` veri-yerleşimi bölümüne wiki eklenir (Faz 1 görevi).
- **Eval disiplini:** Faz 2.6 eval seti `eval/datasets/**` altına **kendi PR'ında, herhangi bir motor/matching değişikliğinden ÖNCE** girer (freeze guard). "Baseline'ı geçer" genelleme iddiası için taze pre-registered held-out set gerekir.
- **CLI deseni:** mevcut `python -m kapsam.*` düzenine uyulur (`python -m etki.wiki search …`); console-script isteniyorsa 1.6 kapsamına ayrıca eklenir.

---

## Faz 1 — Decision Wiki (Hafta 1-2) ✅ TAMAMLANDI (2026-07-09)

> Uygulandı: `core/ports.py` `WikiStore` + `WikiSearchHit`; `adapters/filesystem_wiki.py`
> (PyYAML frontmatter — python-frontmatter bağımlılığı gerekmedi; rg + saf-Python fallback
> arama); hook `ApprovalService.sync_wiki` (record_triage/decide/ön-analiz kayıtları);
> `etki/wiki/` CLI (`search|show|rebuild`); `ETKI_WIKI_DIR` (boş=kapalı);
> `delete_project` wiki'yi korur; KVKK + RUNBOOK + CLAUDE.md güncel; 9 yeni test,
> tüm süit + eval gate yeşil.

**Amaç:** Triage kararlarının gerekçelerini dosya-tabanlı, aranabilir, git-versiyonlanabilir uzun-form hafızaya yazmak. Graph = ilişki, wiki = içerik ayrımı. OSS demo hikâyesi: *"decision memory as code"*.

### Dizin şeması

```
.etki/wiki-{project_id}/
├── index.md                       # otomatik üretilen içindekiler + istatistik
├── decisions/
│   └── DEC-{yyyymmdd}-{slug}.md   # frontmatter: case_id, verdict, scope_ref, confidence
├── entities/
│   ├── contracts/{contract_id}.md # sözleşme özeti, kritik maddeler
│   └── modules/{module}.md        # kod modülü özeti, sahiplik
└── precedents/
    └── PRE-{slug}.md              # sınır vakaları, override'lar, tartışmalı kararlar
```

### Görevler

| # | Görev | Tahmin |
|---|-------|--------|
| 1.1 | `WikiStorePort` (hexagonal port, `core/ports.py`): `write_decision()`, `search()`, `get_entity_page()`, `rebuild()` | 0.5g |
| 1.2 | `FileSystemWikiAdapter` — frontmatter (python-frontmatter) + markdown yazımı, proje-başına dizin | 1g |
| 1.3 | Search backend v1: ripgrep tabanlı arama (`rg --json`); embedding sonrası opsiyonel katman | 1g |
| 1.4 | Triage flow'a hook: karar üretildiğinde otomatik decision dosyası (kanıt zincirinden projeksiyon) | 1g |
| 1.5 | `index.md` regeneration + **`rebuild` komutu** (DB'deki tüm vakalardan wiki'yi sıfırdan üret — projeksiyon garantisi) | 1g |
| 1.6 | CLI: `python -m etki.wiki search <query>` / `show DEC-…` / `rebuild` | 1g |
| 1.7 | `docs/KVKK.md` güncellemesi (wiki veri yerleşimi) + `delete_project` wiki davranışı | 0.5g |

### Kabul kriterleri

- Her triage kararı otomatik olarak ilgili projenin `decisions/` dizinine düşer
- `python -m etki.wiki search "SSO entegrasyonu"` geçmiş emsal kararları döner
- `rebuild` sonrası wiki, silinmeden önceki haliyle bit-düzeyinde eşdeğer içerik üretir (projeksiyon testi)
- Wiki dizini git ile versiyonlanabilir

---

## Faz 2 — Üçlü Retrieval Query Port (Hafta 3-4) ✅ TAMAMLANDI (2026-07-09)

> Uygulandı: `core/ports.py` `GraphQueryPort` + `GraphNode/GraphEdge/Subgraph/QueryResult`;
> `etki/graphquery.py` `IndexGraphQuery` (find_k: embedder varsa kosinüs + hata halinde
> leksik fallback, yoksa `core/text.score`; expand: gerçek kenarlar üzerinde token-bütçeli
> BFS; nl_query: LLM→IndexTools whitelist tool-call, injection-guard'lı, 3 deneme →
> find_k fallback; `choose_strategy` kural tabanlı v1 + `query()` façade — strateji
> `QueryResult.strategy`'de denetlenebilir). **Vektör deposu gerekmedi:** korpus küçük
> (onlarca madde/modül), tam kosinüs bellek-içi; sqlite-vec/pgvector ancak korpus
> büyüyünce gündeme gelir (plan sadeleşmesi). Eval: dataset motor kodundan ÖNCE ayrı
> commit'te; ilk dürüst ölçüm TR find_k 0.82 → combined 1.00, precision 0.36 (~10 node) —
> Faz 4 rerank gerekçesi sayıyla kayıtlı. Gate: `eval/runner`'da TR combined ≥0.9 ve
> combined ≥ find_k. Triyaj karar yolu DEĞİŞMEDİ (golden set korundu).

**Amaç:** Tek `GraphQueryPort` arkasında üç strateji; triage motoru sorgu tipine göre strateji seçer.

### Interface

```python
class GraphQueryPort(Protocol):
    def find_k_nodes(self, text: str, k: int, node_types: list[str] | None) -> list[Node]: ...
    def expand(self, seed_ids: list[str], max_hops: int, token_budget: int) -> Subgraph: ...
    def nl_query(self, question: str) -> QueryResult: ...   # LLM → IndexTools tool-call (Cypher YOK)
```

### Görevler

| # | Görev | Tahmin |
|---|-------|--------|
| 2.1 | Port tanımı + mevcut retrieval kodunun port arkasına taşınması (refactor; `IndexTools` ilk adapter) | 1g |
| 2.2 | **Find K Nodes**: work item embedding → scope + historical effort node'larında ANN. Model: bge-m3 (mevcut `EmbeddingProvider` portu üzerinden, `ETKI_EMBED_*`); storage: **sqlite-vec** (varsayılan, sıfır-infra) / pgvector (Postgres'te). **Sınır:** yalnız aday getirme — include tarafında karar sinyali olamaz (ölçülmüş bi-encoder dersi) | 2g |
| 2.3 | **Expand**: graphify-mcp'deki token-budgeted BFS'in adapter olarak porta bağlanması (freshness bug'ları — untracked files, mtime — bu sırada kapanır) | 1g |
| 2.4 | **NL Query**: LLM → IndexTools tool-call üretimi (agent.py deseni). Guardrail: yalnız read-only tool whitelist + `wrap_untrusted`; 3 retry + fallback → `find_k_nodes` | 1.5g |
| 2.5 | Strateji seçici: triage pipeline'da hangi sorgu tipinde hangi yol (kural tabanlı v1) | 1g |
| 2.6 | Eval seti: 20-30 örnek sorgu + beklenen node'lar, üç yolun recall karşılaştırması. **Set motor değişikliklerinden ÖNCE kendi PR'ında commit'lenir (freeze guard)** | 1g |

### Kabul kriterleri

- Üç strateji aynı port üzerinden değiştirilebilir (mock adapter ile unit test)
- `nl_query` hatalı/whitelist-dışı çağrı üretirse sistem düşmez, fallback çalışır
- Eval setinde find_k + expand kombinasyonu baseline'ı geçer (held-out disipliniyle raporlanır)
- bge-m3 Türkçe recall'u eval setiyle ölçülür; zayıfsa multilingual-e5 denenir

---

## Faz 3 — HITL Ingest Loop (Hafta 4-5) ✅ TAMAMLANDI (2026-07-09)

> Uygulandı: `core/models.py` `FeedbackEvent` + `core/ports.py` `IngestPort` /
> `DisputedClause`; `hitl/ingest.py` (`derive_disputes` saf fonksiyon + `WikiIngest` +
> `reproject_derived` — canlı ingest ve `rebuild` aynı türetmeyi paylaşır);
> `ApprovalService.decide` hook'u (best-effort, onayı asla bloklamaz); adapter'a
> `write_precedent`/`write_disputed` (PRE-*.md + disputed.md, index.md bağlantılı);
> KPI `precedent_count`/`disputed_count` + Raporlar ekranı tile'ları (tr/en/de).
> **Idempotency dedup defteriyle değil projeksiyonla:** aynı event'in yeniden
> işlenmesi bit-eşdeğer dosyalar üretir (testli). **Embedding refresh ertelendi:**
> kalıcı embedding deposu yok (bellek-içi önbellek, süreç başına) — kararlar/emsaller
> retrieval node'u olduğunda gündeme gelir. Celery/kuyruk kullanılmadı (plan v0.2 kararı).

**Amaç:** PM düzeltmelerinin ("hayır, bu out-of-scope") graph + wiki'ye geri yazılması. Kendini besleyen historical effort fusion. Override tespiti ve metriği **zaten var** (`repo.list_overrides`, `kpi.override_rate`, `calibration_suggestions`) — bu faz yalnız **geri yazımı** ekler.

### Akış

```
PM kararı (ApprovalService) → ingest_decision (senkron çağrı; ağır kısım asyncio.create_task)
  ├── Graph write: (WorkItem)-[JUDGED {verdict, by, at}]->(ScopeClause)
  ├── Wiki write: decisions/ güncelleme; override ise precedents/ terfi
  └── Embedding refresh: etkilenen node'ların yeniden indexlenmesi
```

Celery/Redis **yok** — workers=1 mimarisi ve `app.py`'deki asyncio background-loop deseniyle uyumlu kalınır.

### Görevler

| # | Görev | Tahmin |
|---|-------|--------|
| 3.1 | `FeedbackEvent` domain modeli + `IngestPort` | 0.5g |
| 3.2 | `ingest_decision`: idempotent, retry-safe (dedup anahtarı: case_id + revision); `ApprovalService`'ten çağrı | 1g |
| 3.3 | Override → otomatik `precedents/` adayı işaretleme (mevcut override kaydının üstüne wiki projeksiyonu) | 0.5g |
| 3.4 | Conflict handling: aynı scope maddesine çelişen kararlar → wiki'de "disputed" bölümü | 1g |
| 3.5 | Mevcut KPI ekranına precedent/disputed sayaçları (yeni metrik altyapısı YOK — `kpi.py` genişler) | 0.5g |

### Kabul kriterleri

- PM override'ı 1 dk içinde graph'ta ve wiki'de görünür
- Aynı feedback iki kez işlenirse duplicate yazım olmaz (idempotency testi)
- Precedent/disputed sayıları Raporlar ekranından izlenebilir

---

## Faz 4 — Subgraph Rerank (Hafta 5+, opsiyonel) ✅ ALTYAPI TAMAM (2026-07-09) — canlı A/B TEI bekliyor

> Uygulandı: `expand(seed_ids, max_hops, token_budget, query=None)` — toplama (BFS,
> bütçesiz) ile paketleme ayrıldı; `query` + yapılandırılmış `RerankProvider` varsa
> seed'ler sabit kalıp komşular cross-encoder skoruna göre bütçeye paketlenir
> (`Subgraph.packing: "bfs"|"rerank"` — denetlenebilir). Reranker yok / endpoint
> hatası → bit-eşdeğer eski BFS davranışı (testli). A/B kolu `eval/graph_retrieval.py
> ab_pack` (dar bütçe, aynı seed'ler, tek fark paketleme sırası); CI'da reranker
> olmadığından "atlandı" yazar. **Tesisat smoke'u (anahtar-kelime sahte reranker):**
> rerank kolu recall'u hafif DÜŞÜRDÜ (0.99→0.97) — zayıf reranker zarar verebilir;
> gerçek bge-reranker-v2-m3 ile ölçüm (ve <200ms gecikme kriteri) TEI endpoint'i
> olan makinede: `ETKI_RERANK_BASE_URL=http://localhost:8021 uv run python -m
> eval.graph_retrieval`.

**Amaç:** Subgraph → context paketlemede BFS derinliği yerine relevance skoruyla budama. **Port + adapter zaten var** (`RerankProvider`, `adapters/rerank_tei.py`, bge-reranker-v2-m3, `rerank_strong` kalibre edilmiş, endpoint yoksa sessiz atlama) — bu faz yalnız `expand()` çıktısına bağlar.

### Görevler

| # | Görev | Tahmin |
|---|-------|--------|
| 4.1 | Pipeline entegrasyonu: `expand()` çıktısı → mevcut reranker → token budget'a top-K pack | 1g |
| 4.2 | A/B eval: rerank'li vs rerank'siz triage bağlam kalitesi (Faz 2.6 eval seti üzerinde) | 0.5g |

### Kabul kriterleri

- Rerank endpoint'i yokken davranış birebir eski hali (mevcut sessiz-atlama korunur)
- DGX Spark'ta rerank latency < 200ms / subgraph

---

## Kesişen işler

- **Dokümantasyon:** her faz sonunda `docs/` güncelleme (MkDocs nav dahil) — OSS launch roadmap'ine besleme
- **graphify-mcp bağımlılığı:** 2.3'te adapter olarak kullanılır; freshness bug'ları (untracked files, mtime) Faz 2 sırasında kapatılır
- **PyPI trusted publisher:** plandan bağımsız, hâlâ bekliyor (rename tamamlandı)

## Riskler

| Risk | Etki | Önlem |
|------|------|-------|
| NL query hallucination | Yanlış triage bağlamı | Read-only tool whitelist + `wrap_untrusted` + fallback (2.4) |
| Wiki'nin DB ile senkron kopması | Çelişen hafıza | Wiki = projeksiyon + `rebuild` komutu (1.5); tek yazıcı; elle edit yok |
| Embedding modeli Türkçe kalitesi | Zayıf recall | bge-m3 baseline, eval setiyle ölç (2.6), gerekirse multilingual-e5 |
| Bi-encoder karar sinyali sanılması | Yanlış IN_SCOPE kararları | `find_k_nodes` yalnız aday getirir; include tarafında karar değiştiremez (ölçülmüş kural) |
| Eval setinin motorla aynı PR'da değişmesi | Gate'in oyunlaştırılması | Freeze guard CI'da; set önce, motor sonra (ayrı PR'lar) |
| Scope creep (ironik) | Launch gecikir | Faz 4 opsiyonel; Faz 1-2 MVP olarak launch'a yeter |

## Milestone özeti

| Milestone | Tarih (tahmini) | Çıktı |
|-----------|-----------------|-------|
| M1: Wiki live | Ağustos ortası | Decision memory (projeksiyon) + CLI search + rebuild |
| M2: Query port | Ağustos sonu | 3 retrieval yolu + eval seti |
| M3: Kapalı döngü | Eylül başı | HITL ingest + precedents/disputed |
| M4: Subgraph rerank (ops.) | Eylül ortası | Mevcut reranker expand'e bağlı, A/B ölçülmüş |
