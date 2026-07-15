# Etki — Plugin Sistemi Detaylı Geliştirme Planı

| | |
|---|---|
| **Versiyon** | 0.1 |
| **Tarih** | 2026-07-15 |
| **İlgili doküman** | `Etki_Plugin_Marketplace_Plani.md` (faz-seviyesi plan + ön analiz kararları) |
| **Kapsam** | Faz 1–5'in iş-kalemi/dosya seviyesinde kırılımı; Faz 6 (sandbox) backlog'da kalır |
| **Toplam süre** | ~8–10 hafta part-time (revize — gerekçe §D) |

> Bu doküman marketplace planındaki fazları **uygulanabilir** hale getirir. Tüm dosya yolları ve satır referansları koda karşı doğrulanmıştır (2026-07-15 keşfi). Kilitli kararlar (dar API yüzeyi, env-only policy, `uv pip`, air-gapped hash yolu, adapters/-altında-loader) marketplace planından gelir ve burada yeniden tartışılmaz.

---

## A. Kesişen Tasarım Kararları

Fazlara girmeden önce bir kez verilen, birden çok fazı bağlayan kararlar.

### A1. uv workspace yerleşimi ve import yolu

```
ScopeGuard/
├── pyproject.toml                  # etki (kök üye, adı değişmez)
├── uv.lock                         # tek paylaşılan lockfile (uv workspace)
├── packages/
│   ├── etki-api/
│   │   ├── pyproject.toml          # name = "etki-api", hatchling, deps = ["pydantic>=2.7"] YALNIZCA
│   │   ├── CHANGELOG.md            # zorunlu (semver sözü)
│   │   └── src/etki_api/
│   │       ├── __init__.py         # düz public yüzey: `from etki_api import WorkItemProvider`
│   │       ├── ports.py            # 7 dış Protocol + Capabilities
│   │       ├── models.py           # WorkItem, CodeModule, Complexity, Churn, DocumentRef, PackageMetadata
│   │       ├── plugin.py           # PluginSpec, AdapterFactory, SecurityCapabilities
│   │       ├── manifest.py         # PluginManifest + load_manifest() (tomllib)
│   │       └── conformance/        # Faz 4 (extra: etki-api[conformance])
│   └── etki-plugin-linear/         # birinci-parti out-of-tree plugin (dogfood, workspace üyesi)
│       ├── pyproject.toml          # YALNIZCA etki-api + httpx'e depend eder; entry point burada
│       ├── etki-plugin.toml
│       └── src/etki_plugin_linear/
```

- Üyelerde **src layout** (kurulmamış ağacın kazara import edilmesini önler, uv geleneği); kök `etki` paketi düz kalır (sıfır churn).
- Kök pyproject eklemeleri: `[tool.uv.workspace] members = ["packages/*"]`; `etki-api` `[project.dependencies]`'e; `[tool.uv.sources] etki-api = { workspace = true }`. `etki-plugin-linear` **dev group'a** girer (runtime dep DEĞİL) — CI entry-point keşfini gerçekten çalıştırır.
- **Import yolu:** `etki_api`. Plugin'ler `from etki_api import WorkItemProvider, WorkItem, Capabilities` yazar.
- **Geri uyumluluk (sıfır motor churn'ü):** `etki/core/ports.py` + `etki/core/models.py` taşınan semboller için **re-export shim** olur (açık `__all__`). Aynı class objeleri → mevcut `from etki.core.ports import …` importları VE `isinstance` kontrolleri aynen çalışır. İki dosya da freeze guard dışında (guard yalnız `etki/engine/`, `etki/extraction/`, `etki/core/text.py` izler — `scripts/freeze_guard.py` `ENGINE_PREFIXES` doğrulandı).
- Taşınan model kümesi **enum'suz ve kapalı** (doğrulandı): `WorkItem`/`DocumentRef` bağımsız, `CodeModule → Complexity + Churn`; `Capabilities` + `PackageMetadata` ports.py'den gelir (PackageMetadata model olduğu için `etki_api/models.py`'ye konur, shim ports'tan re-export eder).
- **Build/release:** `uv build --all-packages` iki wheel/sdist'i `dist/`'e üretir; release.yml pypi job'u buna + `skip-existing: true`'ya geçer (etki-api yalnız versiyonu değiştiğinde gerçekten yüklenir — ayrı tag şeması gerekmez). Tek seferlik ops: PyPI'da `etki-api` için **ikinci trusted-publisher** kaydı (aynı repo, release.yml, environment `pypi`).
- Araç konfigi: ruff `src`'ye + mypy hedeflerine + `--cov=etki_api`'ye workspace yolları eklenir; src-layout çift-modül tuzağına karşı `mypy_path` açıkça set edilir.

### A2. Entry-point sözleşmesi

- **Grup `etki.adapters`** → modül-seviyesi **`PluginSpec` instance'ına** çözümlenir: `linear = "etki_plugin_linear:PLUGIN"`. Bir spec birden çok port/adaptör sağlayabilir. **`etki.mcp_tools`** ikinci, daha basit grup (düz callable; `mcp_server.py` iterasyonla `mcp.tool()(fn)` sarar). `etki.domains` / `etki.reports` kılavuzda rezerve ad olarak kalır (kilitli karar: content pack sonra).
- `etki_api/plugin.py` (taslak):

```python
PortName = Literal["work_items", "code_repo", "documents",
                   "llm", "embedding", "rerank", "registry_metadata"]

class SecurityCapabilities(BaseModel):        # KVKK beyanı — işlevsel Capabilities'ten AYRI
    network: bool = False
    filesystem: Literal["none", "read", "write"] = "none"
    endpoints: list[str] = []                 # beyan edilen dış host'lar (dokümantasyon; Faz 6 dikişi)
    notes: str = ""

@dataclass(frozen=True)
class AdapterFactory:
    port: PortName
    name: str                                  # config'teki `adapter:` string'i, örn. "linear"
    options_model: type[BaseModel]             # build() çağrılmadan ÖNCE doğrulanır
    build: Callable[[BaseModel], object]       # secret'lar core tarafından zaten çözülmüş gelir

@dataclass(frozen=True)
class PluginSpec:
    name: str                                  # dağıtım adı, örn. "etki-plugin-linear"
    api_compat: str                            # PEP 440 specifier: ">=0.3,<0.4"
    capabilities: SecurityCapabilities
    adapters: tuple[AdapterFactory, ...]
    conformance: Callable[[], dict[PortName, object]] | None = None   # Faz 4: offline provider'lar
```

- **Manifest ikiliği:** çalışma zamanının doğruluk kaynağı kod içi `PluginSpec`; **`etki-plugin.toml` onun statik ikizi** — plugin kodu *import edilmeden/çalıştırılmadan* okunabilir. Onay ekranı ve marketplace index'i bunu okur. İçeriği: name, type, ports, api_compat, capabilities + `options_model = "etki_plugin_linear.options:LinearOptions"` noktalı referansı (Pydantic sınıfı TOML'de yaşayamaz). `etki plugin verify` (Faz 4) toml ⟷ spec tutarlılığını kontrol eder, sapmada fail.
- **Uyum kontrolü** loader (etki) tarafında: `packaging.specifiers.SpecifierSet(spec).contains(version("etki-api"))`. `packaging>=24` etki'ye **açık bağımlılık** olarak eklenir (bugün yalnızca transitif — ona güvenilmez). etki-api'nin packaging dep'i yoktur.

### A3. Registry v2 ve hata izolasyonu

- Yeni modül **`etki/adapters/plugins.py`** (İlke 6: adapters/ altında, guard dışı):

```python
@dataclass
class PluginStatus:
    name: str; version: str; source: str            # "plugin" (builtin'ler burada listelenmez)
    ports: list[str]; api_compat: str
    state: Literal["active", "failed", "incompatible", "blocked", "disabled"]
    error: str | None = None
    commit: str | None = None                        # git kurulumda direct_url.json'dan

class PluginRegistry:
    def load(self) -> None: ...                      # entry_points(group="etki.adapters"); EP başına try/except
    def find(self, port: str, name: str) -> AdapterFactory | None: ...
    def statuses(self) -> list[PluginStatus]: ...
    def stamp(self) -> list[str]: ...                # AKTİF plugin'lerin sıralı ["etki-plugin-linear@1.2.0+gabc1234"]

def get_plugin_registry() -> PluginRegistry: ...     # modül-seviyesi singleton (lru_cache), get_context gibi
```

  `load()` asla raise etmez: import hatası / bozuk spec / uyumsuz aralık → `failed`/`incompatible` durumu + yüksek sesli log (**sessiz düşme yok**). `verified_only` policy'de lockfile'da `verified=true` olmayan dağıtımların EP'leri `blocked` (CLI kapısının arkasında defense-in-depth).
- **Builder fall-through** ([registry.py](etki/adapters/registry.py)): builtin if/elif zincirleri AYNEN kalır; her `raise _unknown(...)`'dan hemen önce:

```python
provider = _try_plugin("work_items", cfg)
if provider is not None:
    return provider
raise _unknown("work_items", cfg.adapter, known + get_plugin_registry().names("work_items"))
```

  `_try_plugin` = registry lookup → `resolve_secret_refs(cfg.options)` (mevcut `_secret()`'ın dict/list üzerinde recursive genellemesi — **registry.py'de KALIR, export edilmez**) → `factory.options_model.model_validate(...)` (bugünkü çıplak `KeyError` yerine düzgün Pydantic mesajı) → `factory.build(options)`. LLM/embed/rerank builder'ları da builtin olmayan provider adında aynı `find()`'a danışır.
- **Per-proje izolasyon:** bugün `get_context()`'te yalnız `_load_or_build_index` try/except'te ([context.py](etki/api/context.py) ~274–278, izolasyon birimi = tüm proje). `build_work_items` (~283) ve `build_documents` (~312) da kendi try/except'ine sarılır: `work_items` → `FakeWorkItemProvider([])` ("geçmiş yok → efor kod metriğine düşer" yerleşik semantiği), `documents` → `FakeDocumentSourceProvider([])`; hata log'lanır + `PluginStatus`'a işlenir, **proje servis etmeye devam eder**. Kod-repo plugin hatası zaten indeksleme try/except'iyle degrade olur (değişmez). Bu, `_safe_find_similar` felsefesinin aynısı: bozuk zenginleştirme triyajı asla öldürmez.

### A4. Plugin-set audit damgası

- **`TriageDecision.plugin_set: list[str] = Field(default_factory=list)`** — `model_version`/`index_freshness`'ın yanına ([models.py](etki/core/models.py) ~238; damganın gerçek yeri TriageDecision'dır, EvidenceChain değil — keşifle doğrulandı). Liste, birleştirilmiş string değil: audit tüketicisi parse etmesin. Eleman formatı `"<dist>@<ver>"`, git kurulumda `+g<sha7>`; sıralı → deterministik.
- Akış `model_version`'ı birebir kopyalar: `TriageEngine.__init__` `plugin_set: list[str] | None = None` alır (default → `[]`), [triage.py](etki/engine/triage.py) ~537'de karara damgalanır; `get_context()` `get_plugin_registry().stamp()`'i bir kez hesaplar; [service.py](etki/hitl/service.py) `record_triage` TRIAGED `AuditEvent.detail`'ine `"plugin_set"` ekler.
- Plugin'siz kurulum `[]` damgalar → **dondurulmuş vakalar, golden set ve mevcut testler bayt-aynı** (yüklemede eksik alan → default).
- **Freeze-guard disiplini:** triage.py düzenlemesi tek başına serbesttir; o PR `eval/datasets/*.json`'a DOKUNMAZ (guard yalnız kombinasyonda patlar).

### A5. CLI tasarımı

Yeni paket **`etki/plugin/`** (guard dışı), stil [etki/wiki/\_\_main\_\_.py](etki/wiki/__main__.py)'den kopyalanır: argparse subparsers, `main(argv) -> int`, `raise SystemExit(main())`, çağrı `python -m etki.plugin` (**console script YOK** — repo geleneği tüm CLI'larda `python -m`).

| Alt komut | Faz | Not |
|---|---|---|
| `list [--json]` | 2 | durum + versiyon + port + uyum + lockfile'a karşı drift uyarısı |
| `install git+URL@ref` / `install ./x.whl --sha256 H` | 3 | policy-kapılı, onay ekranı, `--yes`, testler için `--python <venv>` |
| `sync [--python]` | 3 | lockfile'dan birebir kurulum (bare-metal + image build anı) |
| `remove <ad>` | 3 | kaldır + lockfile güncelle |
| `verify <dist> [--report out.json]` | 4 | `python -m etki_api.conformance`'a ince delegasyon (A6) |
| `search <terim>` / `install <ad>` (verified) / `mirror <dir>` | 5 | index-güdümlü |

Kilit kararlar:
- **Policy uygulama noktası:** `etki/plugin/policy.py::current_policy()` **doğrudan `os.environ["ETKI_PLUGIN_POLICY"]`** okur (default `verified_only`). Bilinçli olarak `Settings` alanı DEĞİL — `.etki/llm.json` JSON kaynağı yapısal olarak dokunamaz; ters-öncelik gereksinimi istisna hack'iyle değil yapıyla sağlanır. `install`'da ilk iş (ağdan önce) + `PluginRegistry.load()`'da tekrar kontrol edilir.
- **uv subprocess:** `uv pip install <spec>` **bağımlılıklarla** (plugin'lerin httpx vb. meşru ihtiyacı var; `--no-deps` kırar), ardından `uv pip check` — çakışma plugin adıyla yüksek sesli uyarı basar. Tekrarlanabilir otorite yol konteyner build'i (lockfile'dan image build anında sync; `Dockerfile.plugins` overlay dokümante).
- **Branch reddi:** `git ls-remote <url> <ref>` sınıflar; `refs/heads/*` → sert hata, `refs/tags/*` → commit SHA'ya çözümlenir, ≥7 hex commit-ish olduğu gibi kabul. Kurulan ve kilitlenen şey **tam SHA'dır** (`git+URL@<sha>`) — tag oynayabilir, SHA oynamaz.
- **Kod çalıştırmadan onay ekranı:** çözülen SHA scratch dizinine sığ klonlanır, yalnızca `etki-plugin.toml` okunur; ekran: ad, versiyon, portlar, `SecurityCapabilities` ("Bu plugin doğrulanmamış. Bildirdiği yetenekler: ağ erişimi, dosya okuma… Devam? [y/N]").
- **Lockfile `etki-plugins.lock`: TOML** (manifest'le aynı format; insan-okunur diff — wiki'yle aynı "git-versiyonlanabilir" felsefe). Okuma stdlib `tomllib`, yazma yeni küçük dep **`tomli-w`**. Şema: `version = 1` başlığı + `[[plugin]]` girdileri: `name, source(git|local|verified), url, ref, commit, sha256, api_compat, capabilities, installed_at, verified: bool`.

### A6. Conformance suite paketleme

**Karar: etki-api İÇİNDE, `etki_api.conformance` + extra `etki-api[conformance] = ["pytest>=8", "pytest-asyncio>=0.23"]`.** Gerekçe: conformance suite tanımı gereği test ettiği API versiyonuna bağlıdır — ayrı paket etki-api'ye karşı kendi uyum matrisini gerektirirdi; üçüncü-parti CI tam bir satır kurar. pytest asla etki-api'nin base dep'lerine sızmaz.

- Şekil: port başına bir contract sınıfı (`WorkItemProviderContract`, `DocumentSourceProviderContract`, …) — dokümante semantiğe karşı yazılır (limit'e uyum, eşleşme-yok → boş liste (exception değil), unicode/TR metin, `capabilities()` `Capabilities` döner, `embed`/`rerank` çıktısı girdiyle hizalı, `complete_json` dict döner). Plugin yazarı subclass'lar + `provider` fixture'ı sağlar. Küçük bağımsız korpus `etki_api/conformance/data.py`'de (**etki'nin `adapters/fakes/seed`'ine bağımlı DEĞİL** — suite etki'siz çalışmalı).
- **Runner etki'de değil etki-api'de:** `python -m etki_api.conformance <dist> [--report out.json]` — dağıtımın `PluginSpec`'ini çözer, `spec.conformance` factory'sini ister (offline, hazır-verili provider instance'ları; örn. httpx `MockTransport` — verify kimlik-bilgisisiz ve CI'lanabilir kalır), pytest koşusunu junitxml → `conformance-report.json`'a çevirir (`{plugin, version, etki_api_version, api_compat, results[], passed, failed}`). `etki plugin verify` ince delegasyondur.
- Reusable workflow `.github/workflows/plugin-conformance.yml` (`on: workflow_call`; input: paket yolu, python-version): plugin + `etki-api[conformance]` kur, runner'ı koş, raporu artifact yükle.

### A7. Marketplace index ve imza

- `index.json` (harici `etki-plugins` reposunda; pydantic şeması **bu repoda** `etki/plugin/index_schema.py` — CLI ile index-repo CI'ı paylaşır):

```json
{ "schema_version": 1, "generated_at": "...",
  "plugins": [ { "name": "etki-plugin-linear", "summary": "...", "source_repo": "...",
    "ports": ["work_items"], "capabilities": {"network": true, "filesystem": "none"},
    "versions": [ { "version": "1.2.0", "api_compat": ">=0.3,<0.4",
      "artifact": {"url": ".../*.whl", "sha256": "..."},
      "conformance_report": "https://...", "released_at": "..." } ] } ] }
```

- **İmza: `sigstore` (sigstore-python), cosign binary'si DEĞİL.** pip'lenebilir (mirror host'a harici binary provision derdi yok), bundle-tabanlı verify, kimlik `etki-plugins` release workflow'una pinlenir (GitHub OIDC). Opsiyonel extra **`etki[plugins]`** olarak gemiye alınır — base/air-gapped image sigstore çekmez. Doğrulama kodu: `etki/plugin/signing.py::verify_index(index_path, bundle_path)`.
- **Mirror akışı** (`etki plugin mirror <dir>`): `index.json` + `.sigstore.json` bundle indir → **imzayı online tarafta doğrula** → wheel'leri indir → her birinin SHA-256'sını kontrol et → doğrulamayı kaydeden `mirror-manifest.json` yaz. İç (air-gapped) taraf: `etki plugin install <ad> --index <dir>` → **SHA-256 zorunlu, imza opsiyonel** — kilitli uzlaşının kendisi.
- **Verified kurulum yolu:** index'i getir/doğrula → kurulu `etki-api`'yi kapsayan en yüksek `api_compat` versiyonunu seç → wheel indir → sha256 → yetenek onayı (index'ten, hâlâ import öncesi) → `uv pip install wheel` → lockfile'a `verified = true`.

---

## B. Faz Bazında İş Kırılımı

### Faz 1 — Stabil Plugin API (`etki-api`) · **2–2,5 hafta**

**Hedef:** Sözleşme 0.x'te donar; iki builtin + çıkarılmış Linear plugin'i yalnızca `etki-api`'ye karşı derlenir.

| # | İş kalemi | Dosyalar (Y=yeni, D=değişir) | Testler |
|---|---|---|---|
| 1.1 | Ops: PyPI'da `etki-api` adını rezerve et + trusted publisher kaydı (**İLK iş** — ad kapatma riski) | — | — |
| 1.2 | Workspace iskeleti + paket taşıma: `packages/etki-api/` (pyproject, src layout); 7 Protocol + `Capabilities` → `etki_api/ports.py`; `WorkItem, CodeModule, Complexity, Churn, DocumentRef, PackageMetadata` → `etki_api/models.py`; `__init__`'te düz re-export; `__version__` importlib.metadata ile (api/web.py emsali) | Y `packages/etki-api/pyproject.toml`, Y `src/etki_api/{__init__,ports,models}.py`; D kök `pyproject.toml` (workspace + dep + ruff/mypy yolları); D `uv.lock` | mevcut suite DOKUNULMADAN yeşil kalmalı |
| 1.3 | Uyumluluk shim'leri: `etki/core/ports.py` / `models.py` taşınan sembolleri re-export eder (açık `__all__`) | D `etki/core/ports.py`, D `etki/core/models.py` | Y `tests/unit/test_api_surface.py`: identity assert'leri (`etki.core.ports.WorkItemProvider is etki_api.WorkItemProvider`), taşınan modellerde enum-free kontrolü, `__init__.__all__` tam-içerik sözleşme testi |
| 1.4 | `PluginSpec`/`AdapterFactory`/`SecurityCapabilities` + `PluginManifest`/`load_manifest()` (A2) | Y `src/etki_api/plugin.py`, Y `src/etki_api/manifest.py` | Y `packages/etki-api/tests/test_manifest.py` (geçerli/bozuk toml, yetenek default'ları) |
| 1.5 | Dogfood çıkarımı: `packages/etki-plugin-linear/` — `linear_work_item.py`'nin yalnız `etki_api` import eden kopyası; `PLUGIN: PluginSpec` + `LinearOptions(BaseModel)` (api_key, hours_per_point); entry point + `etki-plugin.toml`. **Builtin `linear` branch'i Faz 2'ye kadar kalır** | Y paket ağacı; D kök `pyproject.toml` (dev group üyesi) | Y `packages/etki-plugin-linear/tests/` (`tests/unit/test_linear.py` eşleme testlerinin portu) |
| 1.6 | ≥2 builtin adaptörün (glpi + ast; linear zaten) importlarını `from etki_api import …`'a çevir — mekanik | D `etki/adapters/{glpi_work_item,ast_code_index,linear_work_item}.py` | `test_api_surface.py`: bu modüllerin import grafında `etki.core` yok assert'i |
| 1.7 | CI/release: mypy+ruff+cov `etki_api`'yi kapsar; release.yml pypi job'u → `uv build --all-packages` + `skip-existing: true` | D `.github/workflows/ci.yml`, D `.github/workflows/release.yml` | CI'nın kendisi |
| 1.8 | Doküman: `docs/writing-an-adapter.md` → Plugin Geliştirme Kılavuzu'na terfi (manifest + paketleme + semver politikası bölümleri); etki-api CHANGELOG tohumu; `LLMClient` tek-metod kararı kaydedilir | D `docs/writing-an-adapter.md`, Y `packages/etki-api/CHANGELOG.md`, D `mkdocs.yml` | — |

**Gate (CI'da koşulabilir):** (a) shim'lerle tam suite yeşil; (b) `test_api_surface.py` ≥2 builtin + linear plugin'in sıfır `etki.*` import ettiğini kanıtlar; (c) `uv build --package etki-api` CI'da geçer; (d) etki-api 0.1.0 gerçekten PyPI'da.

**Riskler:** trusted-publisher kurulumu release job'unu bloklar (1.1 önce); mypy src-layout çift-modül tuzağı (`mypy_path` açık set edilir); API yüzeyinin kazara genişlemesi (koruma: `__all__` sözleşmedir, test tam içeriğini assert eder).

---

### Faz 2 — Runtime Keşif ve Yükleme · **1–1,5 hafta**

**Hedef:** `pip install plugin` + restart = config'den seçilebilir; hatalar izole; audit damgalı.

| # | İş kalemi | Dosyalar | Testler |
|---|---|---|---|
| 2.1 | `PluginRegistry` (A3): load/find/statuses/stamp, `packaging.specifiers` uyum kontrolü, git commit `direct_url.json`'dan; `packaging>=24` açık dep | Y `etki/adapters/plugins.py`; D `pyproject.toml` | Y `tests/unit/test_plugin_registry.py` — fabrikasyon `EntryPoint`'ler (monkeypatch `entry_points`): sağlam spec, import'ta raise, uyumsuz aralık, çift adaptör adı (ilk kazanır + uyarı) |
| 2.2 | `resolve_secret_refs(options)` recursive ön-çözüm; plugin build yolu option'ları Pydantic ile doğrular | D `etki/adapters/registry.py` | unit: iç içe `env:VAR` model'e ulaşmadan çözülür; tanımsız var → net ValueError |
| 2.3 | Üç builder'da `_unknown` öncesi fall-through + LLM/embed/rerank plugin kancası; `_unknown` mesajı plugin adlarını da listeler; **builtin `linear` branch'i SİLİNİR** (çıkarım tamamlanır; `adapter: linear` config değişmeden plugin yoluna geçer) | D `etki/adapters/registry.py` | D `tests/unit/test_linear.py` → çözümleme artık plugin yolundan assert edilir |
| 2.4 | Context izolasyonu: `build_work_items` (~283) ve `build_documents` (~312) try/except → `FakeWorkItemProvider([])` / `FakeDocumentSourceProvider([])` fallback + log | D `etki/api/context.py` | Y `tests/integration/test_plugin_isolation.py`: raise eden factory → context kurulur, proje servis eder, durum `failed` |
| 2.5 | Plugin-set damgası (A4): model alanı + motor ctor arg + context bağlantısı + audit detayı | D `etki/core/models.py`, D `etki/engine/triage.py` (**bu PR'da dataset düzenlemesi YOK**), D `etki/api/context.py`, D `etki/hitl/service.py` | unit: default `[]`; entegrasyon: TRIAGED `AuditEvent.detail` `plugin_set` taşır |
| 2.6 | `python -m etki.plugin list [--json]` (wiki CLI kalıbı) | Y `etki/plugin/{__init__,__main__}.py` | Y `tests/unit/test_plugin_cli.py` (list çıktısı, exit code'lar) |
| 2.7 | `etki.mcp_tools` entry-point grubu: iterasyon + `mcp.tool()(fn)`, tool başına try/except | D `etki/mcp_server.py` | fabrikasyon entry point ile unit |
| 2.8 | KVKK envanteri: kurulu plugin seti + yetenek beyanları bölümü (`list --json` besler) | D `docs/KVKK.md` | — |

**Gate:** entegrasyon testi — `etki-plugin-linear` kuruluyken (dev group) `adapter: linear` config'li proje plugin yolundan uçtan uca triyaj yapar (MockTransport); kasıtlı-bozuk fabrikasyon plugin `get_context()`'i engellemez; o triyajın TRIAGED audit event'i `["etki-plugin-linear@<ver>"]` içerir. **Üç assert de CI'da yaşar.**

**Riskler:** builtin/plugin ad çakışması (kural: builtin kazanır + uyarı loglanır — dokümante); `@lru_cache get_context` → plugin değişikliği restart ister (dokümante; plan zaten "restart ile" der).

---

### Faz 3 — Git Dağıtımı: pin + lockfile · **1–1,5 hafta**

| # | İş kalemi | Dosyalar | Testler |
|---|---|---|---|
| 3.1 | `policy.py` — yalnız env okuma (A5), default `verified_only` | Y `etki/plugin/policy.py` | unit + **ters-öncelik kanıtı**: `.etki/llm.json`'a policy anahtarı yaz → yok sayıldığı assert edilir |
| 3.2 | `lockfile.py` — TOML modelleri + oku/yaz (`tomli-w` dep) | Y `etki/plugin/lockfile.py`; D `pyproject.toml` | round-trip, bilinmeyen `version` reddedilir, kararlı sıralama (diff-dostu) |
| 3.3 | `installer.py` — `resolve_git_ref` (ls-remote, branch → sert hata), `fetch_manifest` (SHA'da sığ klon → toml oku), `install_git`/`install_wheel(path, sha256=zorunlu)`, `uv pip` subprocess + `uv pip check` uyarısı, testler için `--python` hedefi | Y `etki/plugin/installer.py` | mock'lu subprocess unit'leri: branch reddi, tag→SHA çözümü, sha256 uyuşmazlığı kurulumdan ÖNCE iptal |
| 3.4 | CLI `install`/`sync`/`remove` + yetenek onay ekranı + `--yes`; policy kontrolü ilk iş | D `etki/plugin/__main__.py` | CLI testleri: `verified_only` → exit≠0 + net mesaj, ağ denemesi yok; prompt beyan edilen yetenekleri gösterir |
| 3.5 | Konteyner yolu: `Dockerfile.plugins` overlay örneği (COPY lockfile → `RUN python -m etki.plugin sync`) + RUNBOOK bölümü; runtime sync = yalnız bare-metal (dokümante) | Y `Dockerfile.plugins` (örnek), D `docs/RUNBOOK.md` | — |

**Gate (CI, ağsız):** CI linear plugin wheel'ini build eder → `install ./dist/*.whl --sha256 <h> --python <atılabilir uv venv>` → lockfile yazılır → venv silinir → `sync` → venv'de `uv pip freeze` ilk kuruluma **bayt-aynı**; `ETKI_PLUGIN_POLICY=verified_only` aynı komutu engeller; branch ref reddedilir (mock ls-remote).

**Riskler:** plugin bağımlılıkları core pin'lerini yükseltir (önlem: `uv pip check` + tekrarlanabilir yol = konteyner build'i; drift `list`'te loglanır); git protokol tuhaflıkları (private host'a ls-remote — token git credential helper ile, ASLA URL içinde; dokümante).

---

### Faz 4 — Conformance Suite ("AdapterBench") · **1,5–2 hafta** · F1 biter bitmez başlar, F3'e paralel (öne-çekme kararı)

| # | İş kalemi | Dosyalar | Testler |
|---|---|---|---|
| 4.1 | `etki_api.conformance` paketi: 7 port için contract sınıfları + bağımsız mini korpus + `[conformance]` extra | Y `packages/etki-api/src/etki_api/conformance/{__init__,base,data,work_items,code_repo,documents,llm,embedding,rerank,registry_metadata}.py`; D etki-api pyproject | suite'in kendisi |
| 4.2 | **Yazılı port sözleşmeleri** (testlerin kodlayacağı semantik) kılavuza — asıl tasarım işi: hata davranışı, boş-sonuç davranışı, unicode/TR, hizalama garantileri. **ÖNCE yazılır, ≥3 mevcut adaptöre (glpi, jira, linear) karşı gözden geçirilir, SONRA test kodlanır** | D `docs/writing-an-adapter.md` | — |
| 4.3 | Ana CI'da self-test: suite `etki/adapters/fakes/*`'a ve linear plugin'in `spec.conformance` factory'sine karşı koşar — builtin'lere anında regresyon ağı (öne-çekmenin getirisi) | Y `tests/unit/test_conformance_selfcheck.py` | — |
| 4.4 | Runner `python -m etki_api.conformance <dist> --report out.json` (junitxml → JSON + insan-okunur özet); `PluginSpec.conformance` alanı (Faz 1'de eklendi, şimdi çalıştırılır) | Y `.../conformance/__main__.py`, Y `runner.py`, `report.py` | unit: rapor şeması, hatada sıfır-olmayan exit |
| 4.5 | `etki plugin verify <dist>` ince delegasyon | D `etki/plugin/__main__.py` | CLI testi |
| 4.6 | Reusable GH workflow (`workflow_call`) + raporda versiyon-uyum matrisi alanları (Faz 5 index'ini besler) | Y `.github/workflows/plugin-conformance.yml` | 4.7 çalıştırır |
| 4.7 | Linear plugin CI'ının reusable workflow'dan geçirilmesi (repo-içi caller job) | D `.github/workflows/ci.yml` (caller job) | CI'nın kendisi |

**Gate:** linear plugin, yayınlanan reusable workflow üzerinden CI'da conformance'ı geçer ve `conformance-report.json` artifact'i üretir; fakes aynı suite'i geçer (suite ↔ motor beklentileri tutarlı).

**Riskler:** sözleşmeleri fazla-spesifikleştirmek kazara davranışı dondurur (önlem: 4.2 önce + çoklu-adaptör gözden geçirme); üçüncü-parti repolarda async fixture / pytest-asyncio `auto` mod uyumsuzluğu (kılavuza `conftest.py` parçası konur).

---

### Faz 5 — Verified Marketplace · **2–2,5 hafta**

| # | İş kalemi | Dosyalar | Testler |
|---|---|---|---|
| 5.1 | Index şeması (pydantic, CLI + index-repo CI paylaşır); harici `etki-plugins` reposu bootstrap (index.json, sigstore-imzalı release workflow, `PROCESS.md` küration dokümanı: PR + conformance raporu + spot check, tek küratör) | Y `etki/plugin/index_schema.py`; harici repo | şema round-trip unit'leri |
| 5.2 | `signing.py::verify_index` (sigstore-python, kimlik index reposunun workflow'una pinli); `etki[plugins]` extra | Y `etki/plugin/signing.py`; D `pyproject.toml` | kayıtlı bundle fixture'ı ile unit (tamper → fail); canlı doğrulama ayrı scheduled workflow'da (başta non-blocking) |
| 5.3 | Marketplace istemcisi + CLI: `search`, verified `install <ad>` (index → imza → uyum çözümü → sha256 → onay → uv pip → lockfile `verified=true`) | Y `etki/plugin/marketplace.py`; D `__main__.py` | lokal fixture index dizinine karşı entegrasyon |
| 5.4 | `mirror <dir>` + `mirror-manifest.json`; `install --index <dir>` offline (hash zorunlu, imza opsiyonel) | D `etki/plugin/{marketplace,installer}.py` | entegrasyon: mirror → ağ kesilir (httpx mock) → mirror'dan kurulum geçer; kurcalanmış wheel iptal |
| 5.5 | Salt-okunur UI: Ayarlar → "Plugins" ekranı — durumlar (verified rozeti / failed), versiyonlar, **policy salt-okunur gösterilir**, yalnız KURULU plugin'e aktif/pasif toggle (disable-only UI'dan güvenlidir; `.etki/plugins.json`'a yazılır, `PluginRegistry.load()` okur → `state: disabled`) + i18n (tr/en/de) | D `etki/api/web.py` (veya settings router'ı), Y `etki/api/templates/plugins.html`, D `etki/i18n/catalog.py`, D `etki/adapters/plugins.py` | entegrasyon (TestClient): ekran durumları render eder; policy değiştiren POST YOKTUR; toggle round-trip |
| 5.6 | Uçtan uca gate montajı (aşağıda) | Y `tests/integration/test_marketplace_flow.py` | — |

**Gate:** CI entegrasyon testi lokal fixture index'e karşı tam zinciri sürer: `install <ad> --index <fixture>` → hash doğrulandı → atılabilir venv'e kuruldu → lockfile `verified=true`; aynı test (a) bozuk sha256 ve (b) bozuk imza bundle'ı ile **ayrı ayrı** exit≠0 verir ve lockfile'a dokunulmamıştır. Gerçek imzalı index'e karşı doğrulama scheduled online workflow'da koşar (index reposu canlanınca blocking'e çevrilir).

**Riskler:** sigstore-python API churn'ü (pin `sigstore>=3,<4`; `signing.py` arkasına izole); tek küratör darboğazı (süreç dokümanı + otomasyon insan adımını spot-check'e indirir); **UI toggle asla kurulum vektörü olamaz** (route incelemesi: kod-edinme endpoint'i yok, yalnız CSRF-korumalı toggle).

---

## C. Sıralama

```
F1 (2–2,5h) ──> F2 (1–1,5h) ──> F3 (1–1,5h) ──┐
          └───> F4 (1,5–2h, F1'den hemen sonra) ──┴──> F5 (2–2,5h)
```

## D. Süre Revizyonu

Toplam **~8–10 hafta part-time** (marketplace planının taslağı 6–9 demişti). Delta üç yerden: **F1** — CI/packaging/trusted-publisher işleri (workspace greenfield, iki paketin release entegrasyonu); **F4** — sözleşme semantiğini yazma işi (4.2) test kodlamadan ayrı ve önce gelen gerçek tasarım işi; **F5** — UI ekranı + harici repo bootstrap. **Minimum değerli teslim F1+F2 değişmedi** — registry v2, izolasyon ve audit damgası sıfır dış plugin'le bile kendini öder.
