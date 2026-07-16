# Güvenlik & KVKK Uyum Notları (Faz 3)

> Bu belge, Etki'nin veri koruma ve denetlenebilirlik tasarımını özetler.
> Konsept aşamasıdır; üretim dağıtımında hukuk/uyum ekibiyle doğrulanmalıdır.

## Veri ikametgâhı (data residency)
- **LLM varsayılan kapalıdır** — anahtar yoksa sistem deterministik/sezgisel çalışır ve **hiçbir veri dışa gitmez** (sözleşme, kod ve efor verisi kurum içinde kalır). LLM açıkken (Anthropic Claude API) triyaj/sohbet için ilgili veri LLM sağlayıcısına gider; bu bir **bulut LLM** olduğundan veri **sınır-ötesi aktarımı KVKK m.9** kapsamında değerlendirilmeli ve gerekli aydınlatma/onam/aktarım şartları sağlanmalıdır.
- **Proje özelinde LLM profili / dil / pivot:** triyaj LLM yolunda talep + ilgili kapsam maddeleri + kod modül kimlikleri yapılandırılmış LLM sağlayıcısına gönderilir; proje **çıktı dili** ve **alan profili** istemi şekillendirir. **Pivot çeviri** açıksa girdi/çıktı ek bir çeviri çağrısıyla da işlenir (daha fazla LLM teması) — bulut LLM'de bu da sınır-ötesi aktarım sayılır.
- **Arayüz dili (TR/EN/DE)** salt sunum metnidir; veri işleme/aktarımı değiştirmez.
- Kalıcılık (Postgres) kurum içi ağda tutulur.

## VERBİS & DPIA
- **VERBİS**: Kişisel veri işleniyorsa (ör. ticket atayan/atanan kullanıcı adları) veri sorumlusu sicil kaydı gerekebilir.
- **DPIA (etki değerlendirmesi)**: Sistem profilleme/otomatik karar önerisi ürettiğinden GDPR-tarzı DPIA önerilir. **Ancak karar otomatik DEĞİLDİR** — nihai karar PMO'dadır (insan-yetkilendirmesi), bu da otomatik-karar riskini azaltır.

## Denetlenebilirlik (audit)
- Her triyaj + insan aksiyonu `audit_events` tablosuna tutarlı kimlik, aktör, zaman damgası, model/prompt sürümü ve kanıtla yazılır → **her karar sözleşmesel ihtilaf için yeniden kurgulanabilir** (`GET /casefiles/{id}/audit`).
- Model/prompt sürümü ve indeks tazeliği her kararda saklanır.
- **Aktif plugin seti** de her kararda saklanır (`plugin_set`: `ad@versiyon[+gcommit]`,
  git kurulumlarında commit hash'i dahil) — hangi adaptör kodunun kanıtı ürettiği
  sonradan kanıtlanabilir. Plugin'siz kurulumda boş listedir.

## Plugin envanteri (üçüncü-taraf adaptörler)
- Kurulu plugin'ler, sürümleri ve durumları `python -m etki.plugin list --json` ile
  makine-okunur alınır — VERBİS/DPIA envanterine bu çıktı eklenmelidir.
- Her plugin, manifest'inde (`etki-plugin.toml`) **güvenlik yetenek beyanı** taşır:
  ağ erişimi, dosya-sistemi erişimi ve beyan edilen dış uçlar (endpoints). Bir plugin
  sözleşme/talep verisine adaptör olarak erişebilir → kuruma alınmadan önce bu beyan
  incelenmeli, beyan edilen dış uçların veri ikametgâhı kurallarına uygunluğu
  doğrulanmalıdır. (Beyanın teknik olarak zorlanması — sandbox — plan Faz 6'dadır;
  bugünkü kontrol kurulum onayı + envanterdir.)
- **Tedarik zinciri:** varsayılan politika `verified_only` — yalnızca imzalı
  marketplace index'inden doğrulanan plugin'ler kurulur/yüklenir (uzak index'te
  sigstore imzası zorunlu, artifact SHA-256 kurulumdan ÖNCE doğrulanır; lockfile
  girdisi `verified = true` işaretlenir). Hava-boşluklu ortamda imza çevrimiçi
  tarafta mirror anında doğrulanır, içeride karma doğrulaması zorunlu kalır
  (`docs/RUNBOOK.md` §Plugins). Git/wheel kurulumu bilinçli operatör kararıdır
  (`ETKI_PLUGIN_POLICY` env — UI'dan değiştirilemez). Arayüzden kurulum varsayılan
  kapalıdır; operatör `ETKI_PLUGIN_UI_INSTALL=true` (yalnızca ortam değişkeni) ile
  açarsa pmo kullanıcısı SADECE imzalı index yolundan kurabilir — kaynak env-pinli,
  her kurulum süreç günlüğüne `plugin_install` olayı olarak (kullanıcı + plugin +
  SHA-256) yazılır.
- **Süreç günlüğü** (`.etki/process-log.jsonl`, gitignore'da): Sor ekranı soruları
  (soru → strateji → eşleşen düğümler → asistan yanıtı) ve indeksleme koşuları buraya
  eklenir. Sorular serbest metin olduğundan **kişisel veri içerebilir** — dosya
  veritabanıyla aynı ikametgâh/erişim kurallarına tabidir; KVKK silme talebinde
  dosyadan ilgili satırlar ayıklanmalıdır.

## Karar wiki'si (dosya-tabanlı karar hafızası)
- Her triyaj kararı `.etki/wiki-{proje}/decisions/` altına markdown olarak **projeksiyon** edilir (tek doğruluk kaynağı veritabanıdır; wiki `python -m etki.wiki rebuild` ile her an yeniden üretilebilir).
- Bu dosyalar **talep metnini ve karar gerekçesini** içerir → talep metinlerinde kişisel veri geçiyorsa wiki dizini de kişisel veri barındırır. Dizin veritabanıyla **aynı ikametgâh/erişim kurallarına** tabi tutulmalıdır: kurum içi disk, git'e gönderilecekse yalnız kurum içi depo.
- Proje silindiğinde wiki dizini (DB'deki vaka geçmişi gibi) **korunur** — denetim izinin okunur projeksiyonudur. KVKK silme talebi (m.7) gelirse ilgili vaka DB'den silindikten sonra `rebuild` çalıştırmak wiki'den de düşürür.

## Erişim kontrolü (RBAC)
- Kimlik doğrulama **gerçek login** (pbkdf2-hash'li parola + imzalı session cookie); eski self-asserted `X-Role` header **kaldırıldı** → rol artık doğrulanmış oturumdan okunur.
- Roller: `pmo` (onaylar + kullanıcı/ayar yönetimi), `engineer` (triyaj/analiz çalıştırır), `viewer` (**salt-okur** — tüm yazma uçları 403 döner). Onay endpoint'leri yalnızca `pmo`.
- **Proje izolasyonu:** kullanıcı yalnız grant verilen projeleri görür (`user_projects` tablosu); erişimsiz proje 404 döner (projenin varlığı sızdırılmaz); portföy sayacı yalnız `pmo`'ya görünür. Kullanıcı/grant yönetimi arayüzden yapılır (**Ayarlar → Kullanıcılar**, pmo; kendini silme ve son PMO'yu silme/düşürme engellidir).
- **Oturum güvenliği:** login denemesi sınırlı (IP+kullanıcı başına 15 dk'da 5 hata → 15 dk kilit); login sonrası yönlendirme yalnız site-içi yollara izinli (open-redirect koruması); oturumlar parola hash'ine **token ile bağlıdır** — parola sıfırlama/kullanıcı silme açık oturumları bir sonraki istekte düşürür, rol değişikliği anında etkir; "beni hatırla" sunucu tarafında zorlanır (işaretli 30 gün / işaretsiz 8 saat).
- **LLM anahtarları:** arayüzden (Ayarlar → Yapay Zekâ Asistanı) kaydedilirse `.etki/llm.json` dosyasında tutulur (yalnız dosya sahibi okur, git dışıdır) ve forma asla geri yazılmaz; üretimde önerilen yol ortam değişkenidir.
- **Plugin adaptör anahtarları:** eklenti detay sayfasından (Ayarlar → Eklentiler → eklenti) girilen varsayılan seçenekler `.etki/plugin-options.json` dosyasında tutulur (0600, git dışı); api_key/token gibi gizli alanlar forma **asla geri yazılmaz** ve boş bırakılan gizli alan kayıtlı değeri korur. Değerler `env:DEĞİŞKEN` referansı olarak da girilebilir — üretimde önerilen yol budur.
- **Üretim sertleştirmesi (yapılacak)**: uygulama önüne kimlik-doğrulamalı reverse-proxy + iç ağ izolasyonu + merkezi kimlik (OAuth/SSO). Uygulama-katmanı RBAC bunun sınırıdır.

## Aşırı-güven (over-reliance) kontrolü
- PMO'nun önerileri yalnızca "onaylamadığını" (rubber-stamping) ölçmek için **override/düzeltme oranı** izlenir (proje Raporlar ekranı, `GET /projeler/{id}/raporlar`). Yüksek oran → eşik kalibrasyonu (geri besleme döngüsü).

## İdari para cezaları
- KVKK idari para cezaları yıllık yeniden değerlenir; veri güvenliği ihlali bandı yüksektir → "by-design" uyum (LLM varsayılan kapalı, audit, RBAC) zorunludur.
