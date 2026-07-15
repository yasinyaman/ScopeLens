# Etki — Plugin Sistemi ve Marketplace Planı

> **Durum:** Taslak — ön analiz yapıldı (2026-07-15), detaylı iş kırılımı çıkarıldı, uygulanmadı
> **Tarih:** 2026-07-15
> **Detaylı iş kırılımı:** `Etki_Plugin_Gelistirme_Plani.md` — kesişen tasarım kararları (workspace yerleşimi, entry-point sözleşmesi, registry v2, damga formatı, CLI, conformance paketleme, imza) + faz bazında dosya/test/gate tabloları. Uygulamada o doküman esas alınır.
> **Bağımlılık:** Faz 0–4 tamamlandı, GraphRAG karar-hafıza katmanı canlı. Bu plan mevcut hexagonal mimarinin (ports & adapters) üzerine inşa edilir.
> **Tahmini toplam süre:** ~8–10 hafta part-time (detaylı kırılımla revize — delta: F1 packaging/trusted-publisher, F4 sözleşme-semantiği tasarımı, F5 UI + harici repo bootstrap; fazlar bağımsız teslim edilebilir)

---

## 0. Amaç ve İlkeler

**Amaç:** Üçüncü tarafların Etki'ye adaptör (WorkItemProvider, CodeRepositoryProvider, DocumentSourceProvider, LLMClient, EmbeddingProvider), domain profili, rapor şablonu ve MCP tool'u ekleyebilmesini core'a dokunmadan sağlamak; bunları iki güven modeliyle dağıtmak.

**İlkeler (pazarlık yok):**

1. **Adaptör seçimi config'dir, kod değil** — mevcut felsefe plugin'lere de aynen uzanır.
2. **Air-gapped birinci sınıf vatandaş** — her dağıtım yolu offline bundle ile de çalışmalı.
3. **Kanıt zinciri delinemez** — hangi plugin'in hangi versiyonunun (commit hash) hangi kararda kullanıldığı audit chain'e yazılır.
4. **UI'dan asla pip install yok** — kod kurulumu daima operatör/CLI seviyesinde, açık onayla.
5. **Wiki gibi: marketplace index'i de bir projeksiyondur** — tek doğruluk kaynağı imzalı `index.json`, UI onun görünümü.
6. **Plugin yükleme kodu `adapters/` altında kalır, `engine/`'e sızmaz** — aksi halde her plugin PR'ı freeze guard'la çakışır. (Ön analiz eki.)

**Güven modeli — iki katman + policy anahtarı:**

| Katman | Kaynak | Doğrulama | Hedef kullanıcı |
|---|---|---|---|
| **Verified** | Resmi marketplace index | Conformance suite + imza + pinned hash | Kurumsal / KVKK deployment |
| **Community** | git+URL @tag/commit | Kullanıcı inisiyatifi, lockfile'a hash | Geliştirici / pilot |

```
ETKI_PLUGIN_POLICY = verified_only | allow_git | allow_local   # deployment sahibi karar verir
```

**Policy anahtarı YALNIZCA env/config'ten okunur, UI'dan asla yazılamaz** (salt-okunur gösterim). LLM ayarlarındaki öncelik sırasının (`.etki/llm.json` > env) TERSİ: bu bir güvenlik kilidi, pmo kullanıcısı UI'dan `verified_only`'yi açamamalı.

---

## Faz 1 — Stabil Plugin API (`etki-api` paketi)

**Süre:** ~1,5–2 hafta · **Önkoşul:** yok · **Bu faz olmadan hiçbir şey olmaz.**

Plugin ekosistemi kurmadan önce sözleşmeyi dondurmak gerekir; breaking change maliyeti plugin sayısıyla çarpılır.

**Kapsam kararı (ön analiz, 2026-07-15):** `etki/core/` kendi dışından hiçbir şey import etmiyor — kesim temiz. AMA ports.py'deki 11 portun tamamı DEĞİL, yalnızca **dış-entegrasyon portları** public API'ye girer:

- **Girer:** `WorkItemProvider`, `CodeRepositoryProvider`, `DocumentSourceProvider`, `LLMClient`, `EmbeddingProvider`, `RerankProvider`, `RegistryMetadataProvider` + sadece bunların dokunduğu modeller (`WorkItem`, `CodeModule`, `DocumentRef`, `Capabilities`, `PackageMetadata`).
- **Girmez (iç port):** `CaseFileRepository`, `WikiStore`, `IngestPort`, `GraphQueryPort` — bunları dondurmak domain modelinin (`CaseFile`, `Baseline`…) evrimini kilitler, gereksiz risk.

### İşler

- [ ] Dış-entegrasyon portları + dokundukları modelleri ayrı `etki-api` paketine çıkar (aynı monorepo, **uv workspace**, ayrı pyproject; PyPI'a bağımsız yayınlanır). PyPI'da `etki-api` adının müsaitliğini ERKEN kontrol et (ana paketin trusted publisher işiyle birlikte).
- [ ] Port arayüzlerine **semver garantisi**: `etki-api` major bump = breaking, minor = yeni opsiyonel metod. `CHANGELOG` zorunlu. İlk dış plugin'e kadar `0.x` (breaking serbest, duyurulu).
- [ ] `LLMClient` bilinçli olarak tek metod (`complete_json`) dondurulur; agent tool-loop ihtiyacı ileride minor bump ile eklenir — karar CHANGELOG'a yazılır.
- [ ] Plugin manifest şeması tanımla (`etki-plugin.toml`): ad, tip (adapter/domain/report/mcp-tool), sağladığı port(lar), `etki-api` uyumluluk aralığı, **güvenlik yetenek bildirimi** (ağ erişimi? dosya sistemi? — KVKK dokümantasyonu için) ve **options şeması** (Pydantic modeli: config hataları düzgün mesaj verir, ileride UI form render edebilir). Güvenlik yetenekleri mevcut `Capabilities` modeline (webhook/incremental-diff = işlevsel yetenek) SIKIŞTIRILMAZ — ayrı model.
- [ ] Mevcut yerleşik adaptörleri (jira/glpi/joern/ast/git/llm…) bu API'ye karşı derlenen "birinci parti plugin" olarak yeniden konumlandır — dogfooding: API yeterli mi ilk biz görürüz.
- [ ] `docs/writing-an-adapter.md` → resmi **Plugin Geliştirme Kılavuzu**'na terfi (manifest, test, yayınlama bölümleri eklenir).

### Kabul kriteri

Yerleşik en az 2 adaptör (örn. GLPI + AST) yalnızca `etki-api`'ye depend ederek çalışıyor; core'dan import yok.

---

## Faz 2 — Runtime Keşif ve Yükleme (entry points + registry v2)

**Süre:** ~1 hafta · **Önkoşul:** Faz 1

**Ön analiz notu:** mevcut `adapters/registry.py` if/elif zinciri + elle option sökme (`opt["base_url"]`, eksik anahtar → çıplak `KeyError`). Entry-point keşfi bir **factory sözleşmesi** ister: plugin `build(options) -> Provider` sunar, options manifest'teki Pydantic şemasıyla doğrulanır.

### İşler

- [ ] `importlib.metadata.entry_points(group="etki.adapters")` (+ `etki.domains`, `etki.reports`, `etki.mcp_tools` grupları) ile keşif; mevcut registry'ye `source: builtin | plugin` alanı.
- [ ] **Secret çözümü core'da kalır:** `env:VAR` referansları (`registry._secret`) option'lar plugin'e verilmeden ÖNCE çözülür — plugin config'deki ham referansı hiç görmez, `_secret` public API'ye taşınmaz.
- [ ] Yükleme sırasında **manifest doğrulama**: `etki-api` versiyon uyumu tutmuyorsa plugin reddedilir, log'a net hata (sessiz düşme yok).
- [ ] `etki plugin list` CLI komutu: kurulu plugin'ler, versiyonlar, kaynak, uyumluluk durumu.
- [ ] Audit chain genişletme: triage kararının damgasına **aktif plugin seti + versiyonları** eklenir — mevcut `EvidenceChain.model_version` / `index_freshness` kalıbının aynısı (dondurulmuş eski vakalar etkilenmez). Git kurulumlarında versiyon = lockfile'daki commit SHA (`direct_url.json`'dan da okunabilir).
- [ ] Hata izolasyonu: plugin `__init__` exception'ı uygulamayı düşürmez; plugin "failed" durumuna alınır, UI/CLI'da görünür.
- [ ] **KVKK veri envanteri güncellemesi:** kurulu plugin seti + yetenek beyanları `docs/KVKK.md` envanterine girer (process-log kaydıyla aynı kalıp).

### Kabul kriteri

`pip install <örnek-plugin>` sonrası restart ile plugin config'den seçilebilir; hatalı plugin sistemi çökertmez; kararın kanıt zincirinde plugin versiyonu görünür.

---

## Faz 3 — Git Dağıtımı: pin + lockfile (Community katmanı)

**Süre:** ~1 hafta · **Önkoşul:** Faz 2

### İşler

- [ ] `etki plugin install git+https://…@v1.2.0` — arkada **`uv pip install`** (proje uv-managed; düz pip lockfile–environment drift'ini ilk günden yaratır); **branch referansı reddedilir**, yalnızca tag/commit.
- [ ] `etki-plugins.lock`: kurulan her plugin için kaynak URL, tag, çözümlenmiş commit SHA, kurulum tarihi. Git-versiyonlanabilir (karar wiki'siyle aynı felsefe).
- [ ] `etki plugin sync` — lockfile'dan birebir yeniden kurulum (yeni makine / CI / DR senaryosu). **Konteyner dağıtımında plugin kurulumu image build zamanında lockfile'dan yapılır** (Dockerfile overlay); çalışan konteynerde sync kalıcı olmaz — runtime sync yalnızca bare-metal/venv kurulumları için.
- [ ] Kurulum onay ekranı: "Bu plugin doğrulanmamış. Bildirdiği yetenekler: [ağ erişimi, dosya okuma]. Sözleşme verinize erişebilir. Devam? [y/N]" — manifest'teki yetenek bildirimi burada gösterilir.
- [ ] `ETKI_PLUGIN_POLICY` enforcement: `verified_only` modda bu komut tamamen kapalı (admin kilidi, yalnızca env/config).
- [ ] Offline bundle yolu: `etki plugin install ./plugin.whl --sha256 <hash>` — air-gapped kurulum, hash zorunlu.

### Kabul kriteri

Lockfile'dan sync edilen ortam bit-bit aynı plugin setini verir; `verified_only` policy'de git kurulumu engellenir.

---

## Faz 4 — Conformance Suite ("AdapterBench")

**Süre:** ~1,5 hafta · **Önkoşul:** Faz 1 · **Faz 3 ile paralel yürüyebilir — hatta ÖNE alınabilir** (yerleşik adaptörlerin regresyon ağı olarak hemen değer üretir; git dağıtımının ilk dış kullanıcıya kadar müşterisi yok).

EtkiBench karar kalitesini ölçüyor; bu suite adaptör sözleşme uyumunu ölçer. Verified katmanının teknik temeli. **Zorunluluğu ön analizle netleşti:** portlar `runtime_checkable Protocol` — `isinstance` yalnızca metod VARLIĞINI kontrol eder, imzayı etmez; sözleşme uyumunu yalnızca bu suite kanıtlar.

### İşler

- [ ] Her port için contract test paketi: mevcut `adapters/fakes` altyapısından türetilir, pytest-asyncio ile (portlar async). Örn. `WorkItemProvider` için: sayfalama, boş sonuç, unicode/TR karakter, tarih formatı, hata durumu davranışları.
- [ ] `etki plugin verify <paket>` — suite'i hedef plugin'e karşı çalıştırır, makine-okunur rapor üretir (JSON + insan-okunur özet).
- [ ] GitHub Actions **reusable workflow** yayınla: plugin geliştirici kendi CI'ına tek satırla ekler, her PR'da conformance koşar.
- [ ] Versiyon uyumluluk matrisi: hangi plugin versiyonu hangi `etki-api` aralığıyla test edildi — index metadata'sına girer.
- [ ] (Opsiyonel, zaman kalırsa) Adaptör kalite skoru: contract uyumu ötesinde performans/doğruluk metrikleri — EtkiBench metodolojisi (frozen set, Wilson aralıkları) buraya taşınabilir. **v1 kapsamı dışı, not olarak dursun.**

### Kabul kriteri

Örnek bir üçüncü-parti plugin, yayınlanan workflow ile kendi CI'ında verify'dan geçiyor ve rapor üretebiliyor.

---

## Faz 5 — Verified Marketplace (küratörlü katalog + imza)

**Süre:** ~1,5–2 hafta · **Önkoşul:** Faz 3 + 4

**Air-gapped uzlaşısı (ön analiz):** keyless cosign doğrulaması Rekor/Fulcio erişimi ister — kapalı ortamda çalışmaz. Çözüm: **imza doğrulaması mirror alınırken (online tarafta) yapılır; iç ortamda SHA-256 zorunlu, imza opsiyonel.** İlke 2 böyle korunur.

### İşler

- [ ] `etki-plugins` reposu: `index.json` — her giriş: ad, açıklama, kaynak repo, versiyonlar, her versiyon için **SHA-256 + conformance rapor linki + uyumluluk aralığı**.
- [ ] Index imzalama: v1'de **sigstore/cosign** (keyless, GitHub OIDC ile — GPG anahtar yönetimi derdi yok). CLI kurulumda imza + hash doğrular (online); air-gapped'de hash tek başına yeter.
- [ ] `etki plugin search <terim>` ve `etki plugin install <ad>` (verified yol) — index'ten çözümler, doğrular, kurar, lockfile'a yazar.
- [ ] Kabul süreci dokümanı: bir plugin'in verified olması için PR + conformance raporu + manuel inceleme. Küratör: tek kişi (başlangıçta yeterli, süreç şeffaf olsun).
- [ ] Air-gapped senaryo: `index.json` + wheel'lerin offline mirror'ı için `etki plugin mirror` komutu — imza doğrulamasını mirror sırasında yapar (kurumsal ortam kendi iç mirror'ını kurar).
- [ ] UI tarafı (**salt-okunur**): Settings altında "Plugins" ekranı — kurulu plugin'ler, versiyonlar, verified rozeti, failed durumlar, policy'nin mevcut değeri (değiştirilemez). Kurulum yok, sadece görünürlük + aktif/pasif toggle (kurulu olanlar için).

### Kabul kriteri

`etki plugin install <verified-ad>` uçtan uca: index → imza doğrulama → hash doğrulama → kurulum → lockfile. Bozuk imza/hash kurulumu durdurur.

---

## Faz 6 — (İleri tarih / backlog) Sandbox ve İzolasyon

**Şimdi yapılmaz; tasarım kararlarında kapı açık bırakılır ("leaving seams").**

- Plugin'lerin ayrı process'te çalıştırılması (mevcut MCP altyapısı doğal aday: adaptör = MCP server modeli).
- Yetenek bildirimi → gerçek enforcement'a terfi (network/fs kısıtı).
- Çok-müşterili DB izolasyonu geldiğinde plugin-başına tenant erişim kontrolü.

**Şimdiden yapılacak tek şey:** manifest'teki yetenek bildirimini Faz 1'de zorunlu tutmak — enforcement sonra gelir ama veri baştan toplanır.

---

## Riskler ve Kararlar

| Risk | Etki | Önlem |
|---|---|---|
| Port API'si erken donarsa yanlış soyutlama kilitlenir | Yüksek | Faz 1'de yerleşik adaptörlerle dogfooding; ilk dış plugin'e kadar `0.x` semver (breaking serbest, duyurulu); iç portlar public API dışında |
| Plugin kodu sözleşme verisine erişir (güvenlik) | Yüksek | Policy anahtarı (yalnızca env) + yetenek bildirimi + onay ekranı; sandbox Faz 6 |
| Tek küratör darboğazı | Orta | Süreç şeffaf + otomatik conformance; manuel iş sadece son inceleme |
| Lockfile ile environment'ın ayrışması | Orta | `uv pip` + `etki plugin sync` tek doğruluk kaynağı; `etki plugin list` drift uyarısı verir; konteynerde build-time kurulum |
| Plugin PR'ları freeze guard'la çakışır | Orta | Plugin yükleme kodu `adapters/` altında kalır, `engine/`'e sızmaz (İlke 6) |
| Ekosistem oluşmazsa bakım yükü boşa | Düşük | Faz 1–2 zaten iç mimariyi iyileştirir (registry v2, audit genişletme, hata izolasyonu) — plugin gelmese de kayıp değil |

## Açık Sorular → Kararlar (ön analiz, 2026-07-15)

1. ~~`etki-api` aynı repoda mı?~~ **Karar: monorepo + uv workspace + ayrı PyPI paketi** — sync derdi yok. PyPI ad müsaitliği erken kontrol edilir.
2. ~~Domain profilleri plugin mi?~~ **Karar: v1'de dosya paylaşımı** (`config/domains/*.md`); marketplace'e "content pack" olarak sonra girer.
3. ~~Verified inceleme kapsamı?~~ **Karar: conformance + yetenek beyanı + spot check** — kod incelemesi tek küratörle ölçeklenmez.
4. İlk hedef plugin: **önce mevcut bir birinci-parti adaptör (aday: Linear — en küçüğü) dışarı çıkarılıp döngü uçtan uca kanıtlanır**; ilk gerçek dış aday Monday/ClickUp (`WorkItemProvider` en dar port). GTech iç ihtiyacı çıkarsa öncelik onundur — gerçek kullanıcı, gerçek geri bildirim.

## Sıralama Özeti

```
Faz 1 (API dondur) ──> Faz 2 (runtime yükleme) ──> Faz 3 (git+lockfile)
                  └──> Faz 4 (conformance) ──────────┬──> Faz 5 (verified marketplace)
                                                     └──> Faz 6 (sandbox, backlog)
```

Minimum değerli teslim: **Faz 1+2** (mimari kazanım, dış bağımlılık yok). Community dağıtım: **+Faz 3**. Kurumsal güven hikayesi: **+Faz 4+5**. Faz 4, Faz 3'ün önüne çekilebilir (yukarıdaki not).

---

## Ek — Ön Analiz Kayıtları (2026-07-15, koda karşı doğrulama)

Plandaki varsayımların kod tabanına karşı kontrolü; yukarıdaki fazlara işlenmiş kararların gerekçeleri:

- **`etki/core/` bağımlılık yüzeyi temiz:** paket kendi dışından hiçbir şey import etmiyor (grep ile doğrulandı) — `etki-api` çıkarımı mekanik olarak sorunsuz. Risk kapsamda: ports.py 11 port içeriyor ve tüm domain modelini (`CaseFile`, `Baseline`, `Override`; models.py 321 satır) çekiyor → iç portlar dışarıda bırakıldı.
- **Audit çapası hazır:** `EvidenceChain.model_version` + `index_freshness` (models.py) mevcut; plugin-set damgası aynı kalıp.
- **Registry bugünkü hali:** if/elif + elle option sökme + `_secret()` env-çözümü (registry.py). Factory sözleşmesi + options şeması + pre-resolve secret kararlarının kaynağı.
- **Protocol sınırı:** `runtime_checkable` imza kontrolü yapmaz → conformance suite zorunlu.
- **Deployment gerçeği:** uv-managed proje + immutable konteyner → `uv pip` + build-time plugin kurulumu.
- **Sigstore/air-gapped gerilimi:** keyless doğrulama online ister → mirror-anında-imza / iç-ortamda-hash uzlaşısı.
