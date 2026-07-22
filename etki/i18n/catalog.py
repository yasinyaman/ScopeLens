"""Translation catalog — flat dot-key → {tr, en, de}.

Faz A: enum/role labels (filters + highest traffic). Faz B/C keys
(nav, buttons, error messages, engine prose, prompts) get added here.
Parameterized values via `str.format(**params)` (e.g. "{n} modül").
"""

from __future__ import annotations

MESSAGES: dict[str, dict[str, str]] = {
    # --- Decision types (Decision) ---
    "decision.IN_SCOPE": {"tr": "Kapsam içi", "en": "In scope", "de": "Im Umfang"},
    "decision.OUT_OF_SCOPE": {
        "tr": "Kapsam dışı", "en": "Out of scope", "de": "Außerhalb des Umfangs",
    },
    "decision.CR_CANDIDATE": {
        "tr": "CR adayı", "en": "CR candidate", "de": "CR-Kandidat",
    },
    "decision.GRAY_AREA": {"tr": "Gri alan", "en": "Gray area", "de": "Graubereich"},
    "decision.MAINTENANCE": {"tr": "Bakım", "en": "Maintenance", "de": "Wartung"},
    # --- Risk levels ---
    "risk.LOW": {"tr": "Düşük", "en": "Low", "de": "Niedrig"},
    "risk.MEDIUM": {"tr": "Orta", "en": "Medium", "de": "Mittel"},
    "risk.HIGH": {"tr": "Yüksek", "en": "High", "de": "Hoch"},
    "risk.CRITICAL": {"tr": "Kritik", "en": "Critical", "de": "Kritisch"},
    # --- PMO decision statuses (status) ---
    "status.PENDING": {"tr": "Beklemede", "en": "Pending", "de": "Ausstehend"},
    "status.APPROVE": {"tr": "Onaylandı", "en": "Approved", "de": "Genehmigt"},
    "status.REJECT": {"tr": "Reddedildi", "en": "Rejected", "de": "Abgelehnt"},
    "status.CONVERT_TO_CR": {
        "tr": "CR'a dönüştürüldü", "en": "Converted to CR", "de": "In CR umgewandelt",
    },
    # --- User roles ---
    "role.pmo": {"tr": "PMO Direktörü", "en": "PMO Director", "de": "PMO-Leiter"},
    "role.engineer": {"tr": "Mühendis", "en": "Engineer", "de": "Ingenieur"},
    "role.viewer": {"tr": "İzleyici", "en": "Viewer", "de": "Betrachter"},
    # --- Brand / shell ---
    "lang.language": {"tr": "Dil", "en": "Language", "de": "Sprache"},
    # --- Left menu (navigation) ---
    "nav.menu": {"tr": "MENÜ", "en": "MENU", "de": "MENÜ"},
    "nav.projects": {"tr": "Projeler", "en": "Projects", "de": "Projekte"},
    "nav.summary": {"tr": "Özet", "en": "Overview", "de": "Übersicht"},
    "nav.files": {"tr": "Dosyalar", "en": "Files", "de": "Dateien"},
    "nav.triage": {"tr": "Triyaj", "en": "Triage", "de": "Triage"},
    "nav.history": {"tr": "Geçmiş", "en": "History", "de": "Verlauf"},
    "nav.approvals": {"tr": "Onaylar", "en": "Approvals", "de": "Freigaben"},
    "nav.reports": {"tr": "Raporlar", "en": "Reports", "de": "Berichte"},
    "nav.flow": {"tr": "Akış", "en": "Flow", "de": "Fluss"},
    # --- Top bar ---
    "topbar.search_ph": {
        "tr": "Proje, sözleşme veya talep ara…",
        "en": "Search project, contract or request…",
        "de": "Projekt, Vertrag oder Anfrage suchen…",
    },
    "topbar.monitoring": {
        "tr": "{n} proje izleniyor", "en": "{n} projects monitored",
        "de": "{n} Projekte überwacht",
    },
    "topbar.live": {"tr": "Canlı izleme", "en": "Live monitoring", "de": "Live-Überwachung"},
    "topbar.new_project": {"tr": "Yeni Proje", "en": "New Project", "de": "Neues Projekt"},
    "topbar.logout": {"tr": "Çıkış", "en": "Log out", "de": "Abmelden"},
    "topbar.logout_confirm": {
        "tr": "Oturum kapatılsın mı? Kaydedilmemiş form içeriği kaybolur.",
        "en": "Log out? Unsaved form content will be lost.",
        "de": "Abmelden? Nicht gespeicherte Formularinhalte gehen verloren.",
    },
    # --- Sankey / impact flow ---
    "sankey.kind_request": {
        "tr": "Talep/Analiz", "en": "Request/Analysis", "de": "Anfrage/Analyse",
    },
    "sankey.kind_clause": {"tr": "İster", "en": "Requirement", "de": "Anforderung"},
    "sankey.kind_module": {"tr": "Kod modülü", "en": "Code module", "de": "Codemodul"},
    "sankey.connections": {"tr": "bağlantı", "en": "connections", "de": "Verbindungen"},
    "sankey.affected_clauses": {
        "tr": "Etkilediği isterler", "en": "Affected requirements",
        "de": "Betroffene Anforderungen",
    },
    "sankey.open_case": {"tr": "Vakayı aç →", "en": "Open case →", "de": "Fall öffnen →"},
    "sankey.related_requests": {
        "tr": "İlgili talepler", "en": "Related requests", "de": "Zugehörige Anfragen",
    },
    "sankey.affected_modules": {
        "tr": "Etkilenen kod modülleri", "en": "Affected code modules",
        "de": "Betroffene Codemodule",
    },
    "sankey.module_clauses": {
        "tr": "Bu modülü etkileyen isterler", "en": "Requirements affecting this module",
        "de": "Anforderungen, die dieses Modul betreffen",
    },
    "sankey.empty": {
        "tr": "Bu kapsamda akış için yeterli veri yok.",
        "en": "Not enough data for a flow here.",
        "de": "Nicht genügend Daten für einen Fluss.",
    },
    # --- Login screen ---
    "login.page_title": {
        "tr": "Giriş — Etki", "en": "Sign in — Etki", "de": "Anmelden — Etki",
    },
    "login.hero_title": {
        "tr": "Müşteri görüşmelerinde elinizi kanıtla güçlendirin.",
        "en": "Strengthen your hand with evidence in client meetings.",
        "de": "Stärken Sie Ihre Position in Kundengesprächen mit Belegen.",
    },
    "login.hero_desc": {
        "tr": "Her talep için <b style=\"color:#B7D8C8;\">kapsam içi / dışı / CR</b> kararını "
              "sözleşme, kod ve geçmiş eforu birleştirip <b style=\"color:#B7D8C8;\">kanıt "
              "zinciriyle</b> verir. Analistin kopiloti, müzakerede dayanağınız.",
        "en": "For every request it decides <b style=\"color:#B7D8C8;\">in scope / out of "
              "scope / CR</b> by fusing the contract, code and past effort, backed by an "
              "<b style=\"color:#B7D8C8;\">evidence chain</b>. The analyst's copilot, your "
              "leverage at the table.",
        "de": "Für jede Anfrage entscheidet es <b style=\"color:#B7D8C8;\">im Umfang / "
              "außerhalb / CR</b>, indem Vertrag, Code und bisheriger Aufwand mit einer "
              "<b style=\"color:#B7D8C8;\">Beweiskette</b> verbunden werden. Der Copilot des "
              "Analysten, Ihr Verhandlungsvorteil.",
    },
    "login.kpi_evidence": {"tr": "Kanıt zinciri", "en": "Evidence chain", "de": "Beweiskette"},
    "login.kpi_evidence_sub": {
        "tr": "madde · modül · efor", "en": "clause · module · effort",
        "de": "Klausel · Modul · Aufwand",
    },
    "login.kpi_triage": {
        "tr": "Triyaj → analiz", "en": "Triage → analysis", "de": "Triage → Analyse",
    },
    "login.kpi_triage_sub": {
        "tr": "otomatik ön analiz", "en": "automatic pre-analysis",
        "de": "automatische Voranalyse",
    },
    "login.kpi_flow": {"tr": "Akış", "en": "Flow", "de": "Fluss"},
    "login.kpi_flow_sub": {
        "tr": "talep → ister → kod", "en": "request → requirement → code",
        "de": "Anfrage → Anforderung → Code",
    },
    "login.welcome": {
        "tr": "Tekrar hoş geldiniz", "en": "Welcome back", "de": "Willkommen zurück",
    },
    "login.subtitle": {
        "tr": "Hesabınıza giriş yaparak devam edin.",
        "en": "Sign in to your account to continue.",
        "de": "Melden Sie sich an, um fortzufahren.",
    },
    "login.username": {"tr": "Kullanıcı adı", "en": "Username", "de": "Benutzername"},
    "login.password": {"tr": "Parola", "en": "Password", "de": "Passwort"},
    "login.forgot": {"tr": "Unuttum?", "en": "Forgot?", "de": "Vergessen?"},
    "login.forgot_hint": {
        "tr": "Parola sıfırlama için sistem yöneticinize başvurun.",
        "en": "Contact your system administrator to reset your password.",
        "de": "Wenden Sie sich zum Zurücksetzen des Passworts an Ihren Administrator.",
    },
    "login.soon": {"tr": "YAKINDA", "en": "SOON", "de": "BALD"},
    "login.remember": {"tr": "Beni hatırla", "en": "Remember me", "de": "Angemeldet bleiben"},
    "login.submit": {"tr": "Giriş yap", "en": "Sign in", "de": "Anmelden"},
    "login.or": {"tr": "veya", "en": "or", "de": "oder"},
    "login.sso": {
        "tr": "Kurumsal SSO ile devam et", "en": "Continue with corporate SSO",
        "de": "Mit Unternehmens-SSO fortfahren",
    },
    "login.sso_title": {
        "tr": "Kurumsal SSO bu kurulumda yapılandırılmamış",
        "en": "Corporate SSO is not configured in this setup",
        "de": "Unternehmens-SSO ist in dieser Installation nicht konfiguriert",
    },
    "login.support": {
        "tr": "Sorun mu yaşıyorsunuz? BT destek ile iletişime geçin.",
        "en": "Having trouble? Contact IT support.",
        "de": "Probleme? Kontaktieren Sie den IT-Support.",
    },
    "login.error_bad_credentials": {
        "tr": "Kullanıcı adı veya parola hatalı.",
        "en": "Incorrect username or password.",
        "de": "Benutzername oder Passwort falsch.",
    },
    # --- Error messages (routes) ---
    "err.file_too_large": {
        "tr": "Dosya çok büyük (sınır: {mb}MB). Daha küçük bir dosya yükleyin.",
        "en": "File too large (limit: {mb}MB). Upload a smaller file.",
        "de": "Datei zu groß (Limit: {mb} MB). Laden Sie eine kleinere Datei hoch.",
    },
    "err.too_many_files": {
        "tr": "Tek seferde en fazla {n} dosya yükleyebilirsiniz.",
        "en": "You can upload at most {n} files at once.",
        "de": "Sie können höchstens {n} Dateien auf einmal hochladen.",
    },
    "err.assistant_unavailable": {
        "tr": "Asistan şu an yanıt veremedi (LLM erişilemiyor olabilir). Triyaj kartları ve "
              "kanıt zinciri geçerlidir; lütfen sonra tekrar deneyin.",
        "en": "The assistant could not respond right now (the LLM may be unreachable). The "
              "triage cards and evidence chain are valid; please try again later.",
        "de": "Der Assistent konnte gerade nicht antworten (LLM evtl. nicht erreichbar). Die "
              "Triage-Karten und die Beweiskette sind gültig; bitte später erneut versuchen.",
    },
    "err.file_unreadable": {
        "tr": "Dosya okunamadı veya çözümlenemedi. Desteklenen biçim mi (Word/Excel/PDF/CSV/"
              "TXT), parola korumalı/bozuk olmadığından emin olun.",
        "en": "The file could not be read or parsed. Make sure it's a supported format "
              "(Word/Excel/PDF/CSV/TXT) and not password-protected or corrupt.",
        "de": "Die Datei konnte nicht gelesen oder verarbeitet werden. Stellen Sie sicher, "
              "dass es ein unterstütztes Format (Word/Excel/PDF/CSV/TXT) und nicht "
              "passwortgeschützt oder beschädigt ist.",
    },
    "err.batch_triage": {
        "tr": "Toplu triyaj sırasında bir hata oluştu. Lütfen tekrar deneyin.",
        "en": "An error occurred during batch triage. Please try again.",
        "de": "Bei der Stapel-Triage ist ein Fehler aufgetreten. Bitte erneut versuchen.",
    },
    "err.case_not_found": {
        "tr": "Vaka dosyası bulunamadı", "en": "Case file not found", "de": "Fallakte nicht gefunden",
    },
    "err.invalid_action": {"tr": "Geçersiz aksiyon", "en": "Invalid action", "de": "Ungültige Aktion"},
    "login.rate_limited": {
        "tr": "Çok fazla başarısız deneme. Lütfen yaklaşık {min} dakika sonra tekrar deneyin.",
        "en": "Too many failed attempts. Please try again in about {min} minute(s).",
        "de": "Zu viele Fehlversuche. Bitte in etwa {min} Minute(n) erneut versuchen.",
    },
    "err.pmo_required": {
        "tr": "Bu işlem için PMO rolü gerekir.",
        "en": "This action requires the PMO role.",
        "de": "Diese Aktion erfordert die PMO-Rolle.",
    },
    "err.writer_required": {
        "tr": "Bu işlem için yazma yetkili bir rol gerekir (PMO veya mühendis); izleyici rolü salt-okurdur.",
        "en": "This action requires a writing role (PMO or engineer); the viewer role is read-only.",
        "de": "Diese Aktion erfordert eine schreibberechtigte Rolle (PMO oder Engineer); die Viewer-Rolle ist schreibgeschützt.",
    },
    "triage.viewer_readonly": {
        "tr": "İzleyici rolüyle triyaj çalıştırılamaz — bu ekran salt-okurdur. Mevcut vakaları Geçmiş ve Onaylar ekranlarından inceleyebilirsiniz.",
        "en": "The viewer role cannot run triage — this screen is read-only. You can review existing cases on the History and Approvals screens.",
        "de": "Mit der Viewer-Rolle kann keine Triage ausgeführt werden — dieser Bildschirm ist schreibgeschützt. Bestehende Fälle finden Sie unter Verlauf und Freigaben.",
    },
    "err.project_not_found": {
        "tr": "Proje bulunamadı.", "en": "Project not found.", "de": "Projekt nicht gefunden.",
    },
    "err.doc_not_found": {
        "tr": "Belge bulunamadı.", "en": "Document not found.", "de": "Dokument nicht gefunden.",
    },
    "err.doc_unreadable": {
        "tr": "Belge okunamadı.", "en": "Document could not be read.",
        "de": "Dokument konnte nicht gelesen werden.",
    },
    "err.repo_add_failed": {
        "tr": "Repo eklenemedi: {exc}", "en": "Could not add repository: {exc}",
        "de": "Repository konnte nicht hinzugefügt werden: {exc}",
    },
    # --- Common terms ---
    "common.indexed": {"tr": "İndeksli", "en": "Indexed", "de": "Indexiert"},
    "common.indexed_full": {"tr": "İndekslendi", "en": "Indexed", "de": "Indexiert"},
    "common.no_index": {"tr": "İndeks yok", "en": "No index", "de": "Kein Index"},
    "common.module": {"tr": "modül", "en": "modules", "de": "Module"},
    "common.clause": {"tr": "madde", "en": "clauses", "de": "Klauseln"},
    "common.request": {"tr": "talep", "en": "requests", "de": "Anfragen"},
    "common.baseline": {"tr": "baseline", "en": "baseline", "de": "Baseline"},
    "common.documents": {"tr": "doküman", "en": "documents", "de": "Dokumente"},
    "common.repos": {"tr": "repo", "en": "repos", "de": "Repos"},
    "common.work_items": {"tr": "iş-takip", "en": "work items", "de": "Aufgaben"},
    "common.open_arrow": {"tr": "Aç →", "en": "Open →", "de": "Öffnen →"},
    "common.delete": {"tr": "Sil", "en": "Delete", "de": "Löschen"},
    "common.save": {"tr": "Kaydet", "en": "Save", "de": "Speichern"},
    "common.back_projects": {
        "tr": "Projeler", "en": "Projects", "de": "Projekte",
    },
    # --- Projects (landing page) ---
    "projects.title": {"tr": "Projeler", "en": "Projects", "de": "Projekte"},
    "projects.subtitle": {
        "tr": "Portföydeki projeler — bir projeye girin; talepleri <b>triyaj</b> edin, "
              "geliştirici <b>ön analizini</b> hazırlayın, bilgi grafiğine anında <b>soru sorun</b>.",
        "en": "Portfolio projects — open one; <b>triage</b> requests, prepare the developer "
              "<b>pre-analysis</b>, and <b>ask</b> the knowledge graph instantly.",
        "de": "Projekte im Portfolio — öffnen Sie eines; <b>triagieren</b> Sie Anfragen, erstellen "
              "Sie die Entwickler-<b>Voranalyse</b> und <b>fragen</b> Sie den Wissensgraphen direkt.",
    },
    "projects.stat_projects": {"tr": "Proje", "en": "Projects", "de": "Projekte"},
    "projects.stat_modules": {
        "tr": "Kod Modülü", "en": "Code Modules", "de": "Codemodule",
    },
    "projects.stat_clauses": {
        "tr": "Kapsam Maddesi", "en": "Scope Clauses", "de": "Umfangsklauseln",
    },
    "projects.stat_requests": {
        "tr": "Toplam Talep", "en": "Total Requests", "de": "Anfragen gesamt",
    },
    "projects.card_footer": {
        "tr": "{d} doküman · {r} repo · iş-takip: {w}",
        "en": "{d} documents · {r} repos · work items: {w}",
        "de": "{d} Dokumente · {r} Repos · Aufgaben: {w}",
    },
    "projects.empty": {
        "tr": "Henüz proje yok. Sağ üstten <b>+ Yeni Proje</b> ile başlayın.",
        "en": "No projects yet. Start with <b>+ New Project</b> in the top right.",
        "de": "Noch keine Projekte. Beginnen Sie oben rechts mit <b>+ Neues Projekt</b>.",
    },
    # --- Polarity badges ---
    "badge.included": {"tr": "DAHİL", "en": "INCLUDED", "de": "ENTHALTEN"},
    "badge.excluded": {"tr": "HARİÇ", "en": "EXCLUDED", "de": "AUSGESCHLOSSEN"},
    "common.included_word": {"tr": "dahil", "en": "included", "de": "enthalten"},
    "common.excluded_word": {"tr": "hariç", "en": "excluded", "de": "ausgeschlossen"},
    # --- Project summary (detail) ---
    "pd.freshness": {"tr": "Tazelik", "en": "Freshness", "de": "Aktualität"},
    # --- AI-assistant (LLM) status ---
    "llm.on": {
        "tr": "Yapay zekâ asistanı: aktif",
        "en": "AI assistant: on",
        "de": "KI-Assistent: aktiv",
    },
    "llm.off": {
        "tr": "Yapay zekâ asistanı: kapalı — kural tabanlı mod",
        "en": "AI assistant: off — rule-based mode",
        "de": "KI-Assistent: aus — regelbasierter Modus",
    },
    "llm.off_hint": {
        "tr": "Anahtar/uç nokta yapılandırılmadığı için sohbet ve ön analiz kural tabanlı "
              "üretilir; triyaj kararları her durumda deterministiktir. Etkinleştirme: "
              "ETKI_LLM_PROVIDER=anthropic + ANTHROPIC_API_KEY veya ETKI_LLM_BASE_URL.",
        "en": "No key/endpoint is configured, so chat and pre-analysis are rule-based; "
              "triage decisions are deterministic either way. Enable via "
              "ETKI_LLM_PROVIDER=anthropic + ANTHROPIC_API_KEY or ETKI_LLM_BASE_URL.",
        "de": "Kein Schlüssel/Endpunkt konfiguriert — Chat und Voranalyse sind regelbasiert; "
              "Triage-Entscheidungen sind ohnehin deterministisch. Aktivierung über "
              "ETKI_LLM_PROVIDER=anthropic + ANTHROPIC_API_KEY oder ETKI_LLM_BASE_URL.",
    },
    "llm.source_llm": {"tr": "yapay zekâ", "en": "AI", "de": "KI"},
    # --- global settings screen (/ayarlar) ---
    "nav.settings": {"tr": "Ayarlar", "en": "Settings", "de": "Einstellungen"},
    "set.subtitle": {
        "tr": "Kurulum genelinde geçerli ayarlar — tüm projeleri etkiler.",
        "en": "Installation-wide settings — they affect all projects.",
        "de": "Installationsweite Einstellungen — sie betreffen alle Projekte.",
    },
    "set.llm_title": {
        "tr": "Yapay Zekâ Asistanı (LLM)",
        "en": "AI Assistant (LLM)",
        "de": "KI-Assistent (LLM)",
    },
    "plugins.title": {"tr": "Eklentiler", "en": "Plugins", "de": "Plugins"},
    "plugins.desc": {
        "tr": "Kurulu adaptör eklentileri ve doğrulanmış eklenti pazarı. Policy yalnızca "
              "ortam değişkeniyle yönetilir; git/wheel kurulumu operatör CLI'ında kalır.",
        "en": "Installed adapter plugins and the verified marketplace. The policy is "
              "environment-only; git/wheel installs stay in the operator CLI.",
        "de": "Installierte Adapter-Plugins und der verifizierte Marktplatz. Die Policy ist "
              "nur per Umgebungsvariable steuerbar; Git-/Wheel-Installationen bleiben in der Operator-CLI.",
    },
    "plugins.policy_label": {
        "tr": "Kurulum politikası (ETKI_PLUGIN_POLICY — yalnızca ortam değişkeni)",
        "en": "Install policy (ETKI_PLUGIN_POLICY — environment-only)",
        "de": "Installationsrichtlinie (ETKI_PLUGIN_POLICY — nur Umgebungsvariable)",
    },
    "plugins.policy_note": {
        "tr": "Bu bir yönetici kilididir; arayüzden değiştirilemez. Değerler: verified_only (varsayılan) · allow_git · allow_local.",
        "en": "This is an admin lock; it cannot be changed from the UI. Values: verified_only (default) · allow_git · allow_local.",
        "de": "Dies ist eine Admin-Sperre; sie kann nicht über die Oberfläche geändert werden. Werte: verified_only (Standard) · allow_git · allow_local.",
    },
    "plugins.installed": {"tr": "Kurulu eklentiler", "en": "Installed plugins", "de": "Installierte Plugins"},
    "plugins.empty": {
        "tr": "Kurulu eklenti yok (entry-point grubu: etki.adapters).",
        "en": "No plugins installed (entry-point group: etki.adapters).",
        "de": "Keine Plugins installiert (Entry-Point-Gruppe: etki.adapters).",
    },
    "plugins.col_name": {"tr": "Ad", "en": "Name", "de": "Name"},
    "plugins.col_version": {"tr": "Versiyon", "en": "Version", "de": "Version"},
    "plugins.col_source": {"tr": "Kaynak", "en": "Source", "de": "Quelle"},
    "plugins.col_compat": {"tr": "Uyum", "en": "Compat", "de": "Kompat."},
    "plugins.col_ports": {"tr": "Portlar", "en": "Ports", "de": "Ports"},
    "plugins.col_state": {"tr": "Durum", "en": "State", "de": "Status"},
    "plugins.state_active": {"tr": "etkin", "en": "active", "de": "aktiv"},
    "plugins.state_disabled": {"tr": "devre dışı", "en": "disabled", "de": "deaktiviert"},
    "plugins.state_failed": {"tr": "hatalı", "en": "failed", "de": "fehlgeschlagen"},
    "plugins.state_incompatible": {"tr": "uyumsuz", "en": "incompatible", "de": "inkompatibel"},
    "plugins.state_blocked": {"tr": "engelli (policy)", "en": "blocked (policy)", "de": "blockiert (Policy)"},
    "plugins.verified_badge": {"tr": "Doğrulanmış", "en": "Verified", "de": "Verifiziert"},
    "plugins.toggle_disable": {"tr": "Devre dışı bırak", "en": "Disable", "de": "Deaktivieren"},
    "plugins.toggle_enable": {"tr": "Etkinleştir", "en": "Enable", "de": "Aktivieren"},
    "plugins.confirm_disable": {
        "tr": "Eklenti devre dışı kalınca onu kullanan projeler boş (sahte) adaptöre düşer "
              "— efor geçmişi kapanır. Devam edilsin mi?",
        "en": "Disabling drops every project using this plugin to the empty (fake) adapter "
              "— effort history goes dark. Continue?",
        "de": "Beim Deaktivieren fallen alle Projekte, die dieses Plugin nutzen, auf den "
              "leeren (Fake-)Adapter zurück — die Aufwandshistorie entfällt. Fortfahren?",
    },
    "plugins.stamp_label": {"tr": "Audit damgası", "en": "Audit stamp", "de": "Audit-Stempel"},
    "plugins.install_note": {
        "tr": "Kaldırma ve git/wheel kurulumu: python -m etki.plugin install|remove "
              "(operatör CLI). Doğrulanmış kurulum yolu için aşağıdaki pazara bakın.",
        "en": "Removal and git/wheel installs: python -m etki.plugin install|remove "
              "(operator CLI). For the verified install path see the marketplace below.",
        "de": "Entfernen und Git-/Wheel-Installationen: python -m etki.plugin "
              "install|remove (Operator-CLI). Für den verifizierten Installationsweg "
              "siehe den Marktplatz unten.",
    },
    "plugins.market_title": {
        "tr": "Eklenti pazarı", "en": "Plugin marketplace", "de": "Plugin-Marktplatz",
    },
    "plugins.market_desc": {
        "tr": "İmzalı marketplace index'inin projeksiyonu: arama, uyumluluk, yetenek beyanı "
              "ve doğrulanmış kurulum yolu (kopyalanabilir CLI komutu; operatör açtıysa "
              "Kur butonu).",
        "en": "A projection of the signed marketplace index: search, compatibility, "
              "capability declarations and the verified install path (copyable CLI "
              "command; an Install button when the operator enabled it).",
        "de": "Eine Projektion des signierten Marketplace-Index: Suche, Kompatibilität, "
              "Fähigkeitserklärungen und der verifizierte Installationsweg (kopierbarer "
              "CLI-Befehl; Install-Button, wenn vom Operator aktiviert).",
    },
    "plugins.market_loading": {
        "tr": "İndeks yükleniyor…", "en": "Loading index…", "de": "Index wird geladen…",
    },
    "plugins.market_source_label": {
        "tr": "İndeks kaynağı (ETKI_PLUGIN_INDEX_URL — yalnızca ortam değişkeni)",
        "en": "Index source (ETKI_PLUGIN_INDEX_URL — environment-only)",
        "de": "Indexquelle (ETKI_PLUGIN_INDEX_URL — nur Umgebungsvariable)",
    },
    "plugins.market_signed_note": {
        "tr": "uzak indeks: sigstore imza doğrulaması zorunlu",
        "en": "remote index: sigstore signature verification is mandatory",
        "de": "Remote-Index: Sigstore-Signaturprüfung ist verpflichtend",
    },
    "plugins.market_mirror_note": {
        "tr": "yerel mirror: SHA-256 doğrulaması (air-gapped kuralı)",
        "en": "local mirror: SHA-256 verification (air-gapped rule)",
        "de": "lokaler Mirror: SHA-256-Prüfung (Air-Gap-Regel)",
    },
    "plugins.market_generated": {
        "tr": "indeks tarihi", "en": "index date", "de": "Indexdatum",
    },
    "plugins.market_search": {
        "tr": "Ada, özete ya da porta göre ara…",
        "en": "Search by name, summary or port…",
        "de": "Nach Name, Beschreibung oder Port suchen…",
    },
    "plugins.market_search_btn": {"tr": "Ara", "en": "Search", "de": "Suchen"},
    "plugins.market_refresh": {"tr": "Yenile", "en": "Refresh", "de": "Aktualisieren"},
    "plugins.market_error": {
        "tr": "İndeks okunamadı",
        "en": "Could not read the index",
        "de": "Index konnte nicht gelesen werden",
    },
    "plugins.market_empty": {
        "tr": "Eşleşen eklenti yok.",
        "en": "No matching plugins.",
        "de": "Keine passenden Plugins.",
    },
    "plugins.market_installed_badge": {"tr": "kurulu", "en": "installed", "de": "installiert"},
    "plugins.market_update_badge": {
        "tr": "güncelleme: {v}", "en": "update: {v}", "de": "Update: {v}",
    },
    "plugins.market_latest": {
        "tr": "uyumlu son sürüm", "en": "latest compatible version",
        "de": "neueste kompatible Version",
    },
    "plugins.market_released": {"tr": "yayın", "en": "released", "de": "veröffentlicht"},
    "plugins.market_no_compat": {
        "tr": "Kurulu etki-api {api} ile uyumlu sürüm yok (indekstekiler: {ranges}).",
        "en": "No version compatible with the installed etki-api {api} (index has: {ranges}).",
        "de": "Keine Version kompatibel mit dem installierten etki-api {api} (im Index: {ranges}).",
    },
    "plugins.market_caps": {
        "tr": "Yetenek beyanı", "en": "Capability declaration", "de": "Fähigkeitserklärung",
    },
    "plugins.market_caps_network": {
        "tr": "ağ erişimi", "en": "network access", "de": "Netzwerkzugriff",
    },
    "plugins.market_caps_fs": {"tr": "dosya sistemi", "en": "filesystem", "de": "Dateisystem"},
    "plugins.market_caps_endpoints": {
        "tr": "dış uçlar", "en": "external endpoints", "de": "externe Endpunkte",
    },
    "plugins.market_repo": {"tr": "Kaynak repo", "en": "Source repo", "de": "Quell-Repo"},
    "plugins.market_report": {
        "tr": "Uygunluk raporu", "en": "Conformance report", "de": "Konformitätsbericht",
    },
    "plugins.market_copy": {"tr": "Kopyala", "en": "Copy", "de": "Kopieren"},
    "plugins.market_copied": {"tr": "Kopyalandı ✓", "en": "Copied ✓", "de": "Kopiert ✓"},
    "plugins.market_install_btn": {"tr": "Kur", "en": "Install", "de": "Installieren"},
    "plugins.market_update_btn": {"tr": "Güncelle", "en": "Update", "de": "Aktualisieren"},
    "plugins.market_confirm_install": {
        "tr": "{name} {version} DOĞRULANMIŞ marketplace index'inden kurulacak (imza + "
              "SHA-256 zinciri). Bildirdiği yetenekler: {caps}. Eklenti, adaptör olarak "
              "sözleşme/talep verinize erişebilir. Devam edilsin mi?",
        "en": "{name} {version} will be installed from the VERIFIED marketplace index "
              "(signature + SHA-256 chain). Declared capabilities: {caps}. As an adapter "
              "the plugin can access your contract/request data. Continue?",
        "de": "{name} {version} wird aus dem VERIFIZIERTEN Marketplace-Index installiert "
              "(Signatur- + SHA-256-Kette). Erklärte Fähigkeiten: {caps}. Als Adapter kann "
              "das Plugin auf Ihre Vertrags-/Anforderungsdaten zugreifen. Fortfahren?",
    },
    "plugins.market_installed_flash": {
        "tr": "{name} kuruldu (doğrulanmış). Adaptörü proje ayarlarından seçebilir, "
              "varsayılan seçenekleri eklenti sayfasından girebilirsiniz.",
        "en": "{name} installed (verified). Pick the adapter in project settings; enter "
              "default options on the plugin page.",
        "de": "{name} installiert (verifiziert). Wählen Sie den Adapter in den "
              "Projekteinstellungen; Standardoptionen auf der Plugin-Seite.",
    },
    "plugins.market_install_error": {
        "tr": "Kurulum başarısız", "en": "Install failed", "de": "Installation fehlgeschlagen",
    },
    "plugins.detail_desc": {
        "tr": "Eklenti durumu ve adaptör varsayılanları. Buradaki değerler proje "
              "ayarlarının ALTINA varsayılan olarak girer; proje değeri her zaman kazanır.",
        "en": "Plugin status and adapter defaults. Values here merge UNDER project "
              "settings as defaults; the project value always wins.",
        "de": "Plugin-Status und Adapter-Standardwerte. Diese Werte gelten als "
              "Standard UNTER den Projekteinstellungen; der Projektwert gewinnt immer.",
    },
    "plugins.detail_info": {"tr": "Durum", "en": "Status", "de": "Status"},
    "plugins.detail_installed_at": {
        "tr": "Kurulum tarihi", "en": "Installed at", "de": "Installiert am",
    },
    "plugins.detail_defaults_title": {
        "tr": "Varsayılan seçenekler — {adapter}",
        "en": "Default options — {adapter}",
        "de": "Standardoptionen — {adapter}",
    },
    "plugins.detail_defaults_desc": {
        "tr": "API anahtarı gibi tanımlar burada BİR KEZ girilir (.etki/plugin-options.json, "
              "0600). Değer doğrudan yazılabilir ya da env:DEĞİŞKEN referansı verilebilir.",
        "en": "Definitions like an API key are entered ONCE here (.etki/plugin-options.json, "
              "0600). Enter the value directly or as an env:VARIABLE reference.",
        "de": "Definitionen wie ein API-Schlüssel werden hier EINMAL erfasst "
              "(.etki/plugin-options.json, 0600). Wert direkt oder als env:VARIABLE-Referenz.",
    },
    "plugins.detail_secret_note": {
        "tr": "Gizli alanlar (api_key, token…) asla geri gösterilmez; boş bırakılan gizli "
              "alan kayıtlı değeri korur.",
        "en": "Secret fields (api_key, token…) are never echoed back; leaving a secret "
              "field empty keeps the stored value.",
        "de": "Geheime Felder (api_key, token…) werden nie zurückgegeben; ein leeres "
              "geheimes Feld behält den gespeicherten Wert.",
    },
    "plugins.detail_secret_stored": {
        "tr": "•••• (kayıtlı — boş bırakmak korur)",
        "en": "•••• (stored — leave empty to keep)",
        "de": "•••• (gespeichert — leer lassen behält)",
    },
    "plugins.detail_save": {"tr": "Kaydet", "en": "Save", "de": "Speichern"},
    "plugins.detail_saved": {
        "tr": "Varsayılan seçenekler kaydedildi. Projeler bir sonraki kullanımda yeni "
              "değerlerle bağlanır.",
        "en": "Default options saved. Projects pick up the new values on next use.",
        "de": "Standardoptionen gespeichert. Projekte übernehmen die neuen Werte bei "
              "der nächsten Verwendung.",
    },
    "plugins.detail_has_defaults": {
        "tr": "kayıtlı varsayılanlar var", "en": "stored defaults exist",
        "de": "gespeicherte Standardwerte vorhanden",
    },
    "plugins.detail_reset": {
        "tr": "Varsayılanları sıfırla", "en": "Reset defaults",
        "de": "Standardwerte zurücksetzen",
    },
    "plugins.detail_reset_confirm": {
        "tr": "Bu adaptörün kayıtlı TÜM varsayılanları (gizli anahtar dahil) silinecek. "
              "Devam edilsin mi?",
        "en": "ALL stored defaults of this adapter (including the secret) will be "
              "deleted. Continue?",
        "de": "ALLE gespeicherten Standardwerte dieses Adapters (inkl. Geheimnis) "
              "werden gelöscht. Fortfahren?",
    },
    "plugins.detail_no_adapters": {
        "tr": "Bu eklenti adaptör bildirmiyor (spec yüklenemedi ya da boş).",
        "en": "This plugin declares no adapters (spec failed to load or is empty).",
        "de": "Dieses Plugin deklariert keine Adapter (Spec nicht ladbar oder leer).",
    },
    "plugins.market_cli_note": {
        "tr": "Kurulum yalnızca operatör CLI'ındadır; doğrulanmış kurulum verified_only "
              "policy'si altında da çalışır (imza + SHA-256 zinciri). Arayüzden kurulumu "
              "operatör ETKI_PLUGIN_UI_INSTALL=true ile açabilir. Air-gapped ortam için: "
              "python -m etki.plugin mirror <url> <dizin>.",
        "en": "Installation lives in the operator CLI only; verified installs also work under "
              "the verified_only policy (signature + SHA-256 chain). The operator can enable "
              "UI installs with ETKI_PLUGIN_UI_INSTALL=true. For air-gapped environments: "
              "python -m etki.plugin mirror <url> <dir>.",
        "de": "Die Installation erfolgt ausschließlich über die Operator-CLI; verifizierte "
              "Installationen funktionieren auch unter der verified_only-Policy (Signatur- + "
              "SHA-256-Kette). Der Operator kann UI-Installationen mit "
              "ETKI_PLUGIN_UI_INSTALL=true aktivieren. Für Air-Gap-Umgebungen: "
              "python -m etki.plugin mirror <url> <verzeichnis>.",
    },
    "plugins.market_ui_note": {
        "tr": "Kur butonu YALNIZCA doğrulanmış index yolunu kullanır (imza + SHA-256 "
              "zinciri, kaynak ortam değişkeniyle sabit); git/wheel kurulumu operatör "
              "CLI'ında kalır. Air-gapped ortam için: python -m etki.plugin mirror <url> <dizin>.",
        "en": "The install button uses ONLY the verified index path (signature + SHA-256 "
              "chain, source pinned by the environment); git/wheel installs stay in the "
              "operator CLI. For air-gapped environments: python -m etki.plugin mirror <url> <dir>.",
        "de": "Der Installations-Button nutzt NUR den verifizierten Index-Pfad (Signatur- + "
              "SHA-256-Kette, Quelle per Umgebungsvariable fixiert); Git-/Wheel-Installationen "
              "bleiben in der Operator-CLI. Für Air-Gap-Umgebungen: python -m etki.plugin "
              "mirror <url> <verzeichnis>.",
    },
    "set.llm_desc": {
        "tr": "Sohbet, ön analiz zenginleştirme ve zayıf eşleşmelerde anlamsal destek için "
              "kullanılır. Triyaj kararları her durumda deterministik ve denetlenebilir kalır.",
        "en": "Used for chat, pre-analysis enrichment and semantic assist on weak matches. "
              "Triage decisions stay deterministic and auditable either way.",
        "de": "Für Chat, Voranalyse-Anreicherung und semantische Unterstützung bei schwachen "
              "Treffern. Triage-Entscheidungen bleiben deterministisch und auditierbar.",
    },
    "set.mode_off": {
        "tr": "Kapalı — kural tabanlı mod", "en": "Off — rule-based mode",
        "de": "Aus — regelbasierter Modus",
    },
    "set.mode_anthropic": {
        "tr": "Anthropic Claude API", "en": "Anthropic Claude API",
        "de": "Anthropic Claude API",
    },
    "set.mode_openai": {
        "tr": "OpenAI-uyumlu uç nokta (Ollama / vLLM)",
        "en": "OpenAI-compatible endpoint (Ollama / vLLM)",
        "de": "OpenAI-kompatibler Endpunkt (Ollama / vLLM)",
    },
    "set.api_key": {"tr": "API anahtarı", "en": "API key", "de": "API-Schlüssel"},
    "set.api_key_opt": {
        "tr": "API anahtarı (gerekliyse)", "en": "API key (if required)",
        "de": "API-Schlüssel (falls nötig)",
    },
    "set.key_saved_ph": {
        "tr": "kayıtlı ✓ — değiştirmek için yeni değeri yazın",
        "en": "saved ✓ — type a new value to replace it",
        "de": "gespeichert ✓ — zum Ersetzen neuen Wert eingeben",
    },
    "set.key_empty_ph": {
        "tr": "sk-ant-…", "en": "sk-ant-…", "de": "sk-ant-…",
    },
    "set.model": {"tr": "Model", "en": "Model", "de": "Modell"},
    "set.base_url": {
        "tr": "Uç nokta (base URL)", "en": "Endpoint (base URL)",
        "de": "Endpunkt (Base-URL)",
    },
    "set.timeout": {
        "tr": "Zaman aşımı (sn)", "en": "Timeout (s)", "de": "Timeout (s)",
    },
    "set.clear_keys": {
        "tr": "Kayıtlı API anahtarlarını sil",
        "en": "Delete stored API keys",
        "de": "Gespeicherte API-Schlüssel löschen",
    },
    "set.save": {"tr": "Kaydet", "en": "Save", "de": "Speichern"},
    "set.saved": {
        "tr": "Kaydedildi — yeni ayarlar bir sonraki istekten itibaren geçerli.",
        "en": "Saved — the new settings apply from the next request on.",
        "de": "Gespeichert — die neuen Einstellungen gelten ab der nächsten Anfrage.",
    },
    "set.test": {"tr": "Bağlantıyı sına", "en": "Test connection", "de": "Verbindung testen"},
    "set.testing": {"tr": "sınanıyor…", "en": "testing…", "de": "wird getestet…"},
    "set.test_ok": {
        "tr": "Bağlantı başarılı", "en": "Connection OK", "de": "Verbindung OK",
    },
    "set.test_fail": {
        "tr": "Bağlantı başarısız", "en": "Connection failed", "de": "Verbindung fehlgeschlagen",
    },
    "set.test_unconfigured": {
        "tr": "Yapılandırma eksik — önce sağlayıcı ve anahtar/uç nokta kaydedin.",
        "en": "Not configured — save a provider and key/endpoint first.",
        "de": "Nicht konfiguriert — zuerst Anbieter und Schlüssel/Endpunkt speichern.",
    },
    "set.err_base_url_required": {
        "tr": "OpenAI-uyumlu mod için uç nokta (base URL) zorunludur.",
        "en": "The endpoint (base URL) is required for OpenAI-compatible mode.",
        "de": "Für den OpenAI-kompatiblen Modus ist der Endpunkt (Base-URL) erforderlich.",
    },
    "set.err_bad_timeout": {
        "tr": "Zaman aşımı sayı olmalı (örn. 60).",
        "en": "Timeout must be a number (e.g. 60).",
        "de": "Timeout muss eine Zahl sein (z. B. 60).",
    },
    "set.err_metadata_url": {
        "tr": "Bu uç noktaya izin verilmiyor (bulut metadata/link-local adresi engellidir).",
        "en": "This endpoint is not allowed (cloud metadata / link-local addresses are blocked).",
        "de": "Dieser Endpunkt ist nicht erlaubt (Cloud-Metadaten-/Link-local-Adressen sind gesperrt).",
    },
    # --- user management card ---
    "set.users_title": {"tr": "Kullanıcılar", "en": "Users", "de": "Benutzer"},
    "set.users_desc": {
        "tr": "Rol yetkileri: <b>pmo</b> onaylar ve yönetir, <b>engineer</b> triyaj/analiz "
              "çalıştırır, <b>viewer</b> salt-okur. Proje grantı boş bırakılan kullanıcı "
              "hiçbir projeyi göremez (pmo, küresel erişim açıkken hepsini görür).",
        "en": "Role powers: <b>pmo</b> approves and administers, <b>engineer</b> runs "
              "triage/analysis, <b>viewer</b> is read-only. A user with no project grants "
              "sees no projects (pmo sees all while global access is on).",
        "de": "Rollen: <b>pmo</b> genehmigt und verwaltet, <b>engineer</b> führt "
              "Triage/Analysen aus, <b>viewer</b> ist schreibgeschützt. Ohne Projekt-Grants "
              "sieht ein Benutzer keine Projekte (pmo sieht bei globalem Zugriff alle).",
    },
    "set.user_new": {"tr": "Yeni kullanıcı", "en": "New user", "de": "Neuer Benutzer"},
    "set.username": {"tr": "Kullanıcı adı", "en": "Username", "de": "Benutzername"},
    "set.password": {"tr": "Parola", "en": "Password", "de": "Passwort"},
    "set.new_password": {"tr": "Yeni parola", "en": "New password", "de": "Neues Passwort"},
    "set.role": {"tr": "Rol", "en": "Role", "de": "Rolle"},
    "set.projects_grants": {
        "tr": "Proje grantları", "en": "Project grants", "de": "Projekt-Grants",
    },
    "set.projects_ph": {
        "tr": "virgülle: demo, shop (boş = hiçbiri)",
        "en": "comma-separated: demo, shop (empty = none)",
        "de": "kommagetrennt: demo, shop (leer = keine)",
    },
    "set.create": {"tr": "Oluştur", "en": "Create", "de": "Anlegen"},
    "set.update": {"tr": "Güncelle", "en": "Update", "de": "Aktualisieren"},
    "set.reset_pw": {"tr": "Parolayı sıfırla", "en": "Reset password", "de": "Passwort zurücksetzen"},
    "set.reset_pw_note": {
        "tr": "Parola sıfırlanınca kullanıcının açık oturumları düşer.",
        "en": "Resetting the password drops the user's live sessions.",
        "de": "Beim Zurücksetzen werden die aktiven Sitzungen des Benutzers beendet.",
    },
    "set.delete_user": {"tr": "Sil", "en": "Delete", "de": "Löschen"},
    "set.delete_user_confirm": {
        "tr": "{u} kullanıcısı silinsin mi? Vaka geçmişi ve denetim izi korunur.",
        "en": "Delete user {u}? Case history and the audit trail are preserved.",
        "de": "Benutzer {u} löschen? Fallhistorie und Audit-Trail bleiben erhalten.",
    },
    "set.err_self_delete": {
        "tr": "Kendi hesabınızı silemezsiniz.",
        "en": "You cannot delete your own account.",
        "de": "Sie können Ihr eigenes Konto nicht löschen.",
    },
    "set.err_last_pmo": {
        "tr": "Son PMO kullanıcısı silinemez veya rolü düşürülemez — sistemde bir onaylayıcı kalmalı.",
        "en": "The last PMO user cannot be deleted or demoted — the system must keep an approver.",
        "de": "Der letzte PMO-Benutzer kann nicht gelöscht oder herabgestuft werden — ein Genehmiger muss bleiben.",
    },
    "set.err_user_not_found": {
        "tr": "Kullanıcı bulunamadı.", "en": "User not found.", "de": "Benutzer nicht gefunden.",
    },
    "set.storage_note": {
        "tr": "Buradan kaydedilen değerler <code>.etki/llm.json</code> dosyasında tutulur "
              "(yalnız dosya sahibi okuyabilir) ve aynı addaki ortam değişkenlerinden "
              "önceliklidir. Üretimde anahtarları ortam değişkeniyle vermek önerilir; "
              "boş bırakılan alanlar ortam değişkenine / varsayılana düşer.",
        "en": "Values saved here live in <code>.etki/llm.json</code> (owner-readable only) "
              "and take precedence over the same-named environment variables. In production, "
              "prefer env vars for secrets; empty fields fall back to env/defaults.",
        "de": "Hier gespeicherte Werte liegen in <code>.etki/llm.json</code> (nur für den "
              "Besitzer lesbar) und haben Vorrang vor gleichnamigen Umgebungsvariablen. In "
              "Produktion Secrets besser per Env-Variable; leere Felder fallen auf "
              "Env/Standardwerte zurück.",
    },
    "llm.source_det": {
        "tr": "kural tabanlı", "en": "rule-based", "de": "regelbasiert",
    },
    "pd.stale_badge": {
        "tr": "{n} gün eski", "en": "{n} days old", "de": "{n} Tage alt",
    },
    "pd.stale_hint": {
        "tr": "İndeks eski — yayılım analizi güncel kodu yansıtmayabilir. Dosyalar & Ayarlar'da "
              "bir değişiklik yapmak projeyi yeniden indeksler.",
        "en": "The index is stale — impact analysis may not reflect current code. Any change "
              "under Files & Settings re-indexes the project.",
        "de": "Der Index ist veraltet — die Impact-Analyse spiegelt evtl. nicht den aktuellen "
              "Code wider. Jede Änderung unter Dateien & Einstellungen re-indexiert das Projekt.",
    },
    "pd.work_items": {"tr": "İş-takip", "en": "Work items", "de": "Aufgaben"},
    "pd.degraded_work_items": {
        "tr": "efor kaynağına ulaşılamıyor ({name}) — efor geçmişi devre dışı",
        "en": "effort source unreachable ({name}) — effort history disabled",
        "de": "Aufwandsquelle nicht erreichbar ({name}) — Aufwandshistorie deaktiviert",
    },
    "pd.degraded_documents": {
        "tr": "doküman kaynağına ulaşılamıyor ({name}) — boş kaynakla devam ediliyor",
        "en": "document source unreachable ({name}) — continuing with an empty source",
        "de": "Dokumentquelle nicht erreichbar ({name}) — es wird mit leerer Quelle fortgefahren",
    },
    "pd.degraded_request_intake": {
        "tr": "talep kaynağına ulaşılamıyor ({name}) — talep alma duraklatıldı",
        "en": "request source unreachable ({name}) — intake paused",
        "de": "Anfragequelle nicht erreichbar ({name}) — Erfassung pausiert",
    },
    "pd.degraded_response_channel": {
        "tr": "yanıt kanalına ulaşılamıyor ({name}) — geri yazma başarısız",
        "en": "response channel unreachable ({name}) — write-back failed",
        "de": "Antwortkanal nicht erreichbar ({name}) — Rückschreiben fehlgeschlagen",
    },
    # --- Request intake / response ---
    "intake.reply_triage_title": {
        "tr": "Etki — otomatik ön değerlendirme",
        "en": "Etki — automatic pre-assessment",
        "de": "Etki — automatische Vorbewertung",
    },
    "intake.reply_decision_title": {
        "tr": "Etki — PMO kararı",
        "en": "Etki — PMO decision",
        "de": "Etki — PMO-Entscheidung",
    },
    "intake.reply_outcome_APPROVE": {
        "tr": "Sonuç: kapsam içinde onaylandı.",
        "en": "Outcome: approved as in scope.",
        "de": "Ergebnis: als im Umfang genehmigt.",
    },
    "intake.reply_outcome_REJECT": {
        "tr": "Sonuç: kapsam dışı olarak reddedildi.",
        "en": "Outcome: rejected as out of scope.",
        "de": "Ergebnis: als außerhalb des Umfangs abgelehnt.",
    },
    "intake.reply_outcome_CONVERT_TO_CR": {
        "tr": "Sonuç: değişiklik talebine (CR) dönüştürüldü.",
        "en": "Outcome: converted to a change request (CR).",
        "de": "Ergebnis: in einen Änderungsantrag (CR) umgewandelt.",
    },
    "intake.reply_outcome_PENDING": {
        "tr": "Sonuç: PMO incelemesi bekliyor.",
        "en": "Outcome: pending PMO review.",
        "de": "Ergebnis: ausstehende PMO-Prüfung.",
    },
    "intake.reply_effort": {
        "tr": "tahmini efor {low}–{high} {unit}",
        "en": "estimated effort {low}–{high} {unit}",
        "de": "geschätzter Aufwand {low}–{high} {unit}",
    },
    "intake.reply_clauses": {
        "tr": "ilgili maddeler: {clauses}",
        "en": "related clauses: {clauses}",
        "de": "zugehörige Klauseln: {clauses}",
    },
    "intake.reply_disclaimer": {
        "tr": "Bu otomatik bir değerlendirmedir; nihai karar PMO onayındadır.",
        "en": "This is an automated assessment; the final decision rests with PMO approval.",
        "de": "Dies ist eine automatische Bewertung; die endgültige Entscheidung liegt bei der PMO-Freigabe.",
    },
    "intake.reply_case_link": {
        "tr": "Vaka detayı: {url}",
        "en": "Case detail: {url}",
        "de": "Falldetail: {url}",
    },
    "intake.mode_on_decision": {
        "tr": "PMO kararından sonra (varsayılan)",
        "en": "After the PMO decision (default)",
        "de": "Nach der PMO-Entscheidung (Standard)",
    },
    "intake.mode_on_triage": {
        "tr": "Triyaj anında (öneri yorumu)",
        "en": "At triage time (recommendation comment)",
        "de": "Zum Triage-Zeitpunkt (Empfehlungskommentar)",
    },
    "intake.mode_both": {
        "tr": "Her ikisi (öneri + nihai karar)",
        "en": "Both (recommendation + final decision)",
        "de": "Beide (Empfehlung + Endentscheidung)",
    },
    "pf.intake_title": {
        "tr": "Talep Kanalı", "en": "Request Channel", "de": "Anfragekanal",
    },
    "pf.intake_desc": {
        "tr": "Jira gibi bir kaynaktan talepleri otomatik çekip triyajlar; kararı geri yazar. "
        "Kimlik bilgileri <code>env:VAR</code> ile verilmelidir.",
        "en": "Automatically pulls requests from a source like Jira, triages them, and writes the "
        "decision back. Credentials must be given as <code>env:VAR</code> references.",
        "de": "Zieht Anfragen automatisch aus einer Quelle wie Jira, triagiert sie und schreibt die "
        "Entscheidung zurück. Zugangsdaten müssen als <code>env:VAR</code> angegeben werden.",
    },
    "pf.intake_adapter": {
        "tr": "Kaynak adaptörü", "en": "Source adapter", "de": "Quelladapter",
    },
    "pf.intake_mode": {
        "tr": "Geri yazma zamanı", "en": "Write-back timing", "de": "Rückschreib-Zeitpunkt",
    },
    "plugins.market_caps_external_write": {
        "tr": "dış sisteme yazma", "en": "external write", "de": "externes Schreiben",
    },
    "pd.files_settings": {
        "tr": "Dosyalar & Ayarlar", "en": "Files & Settings", "de": "Dateien & Einstellungen",
    },
    "pd.stat_modules_sub": {
        "tr": "yayılım grafiği", "en": "impact analysis graph", "de": "Wirkungsanalyse-Graph",
    },
    "pd.included_excluded": {
        "tr": "{inc} dahil · {exc} hariç", "en": "{inc} included · {exc} excluded",
        "de": "{inc} enthalten · {exc} ausgeschlossen",
    },
    "pd.stat_baseline": {
        "tr": "Baseline Sürümü", "en": "Baseline Version", "de": "Baseline-Version",
    },
    "pd.stat_baseline_sub": {
        "tr": "yaşayan kapsam referansı", "en": "living scope reference",
        "de": "lebende Umfangsreferenz",
    },
    "pd.stat_documents": {"tr": "Doküman", "en": "Documents", "de": "Dokumente"},
    "pd.documents_linked_repos": {
        "tr": "{r} repo bağlı", "en": "{r} repos linked", "de": "{r} Repos verknüpft",
    },
    "pd.scope_items": {
        "tr": "Kapsam Maddeleri", "en": "Scope Clauses", "de": "Umfangsklauseln",
    },
    "pd.scope_empty": {
        "tr": "Bu projede çıkarılmış kapsam maddesi yok (şartname yükleyip indeksleyin).",
        "en": "No scope clauses extracted for this project (upload a spec and index it).",
        "de": "Keine Umfangsklauseln für dieses Projekt (Spezifikation hochladen und indexieren).",
    },
    "pd.recent_requests": {
        "tr": "Son Talepler", "en": "Recent Requests", "de": "Letzte Anfragen",
    },
    "pd.recent_empty": {
        "tr": "Bu proje için henüz triyaj talebi yok.",
        "en": "No triage requests for this project yet.",
        "de": "Noch keine Triage-Anfragen für dieses Projekt.",
    },
    "pd.repos": {"tr": "Repolar", "en": "Repositories", "de": "Repositories"},
    "pd.repos_empty": {
        "tr": "Bağlı repo yok.", "en": "No linked repository.", "de": "Kein verknüpftes Repository.",
    },
    "pd.documents": {"tr": "Dokümanlar", "en": "Documents", "de": "Dokumente"},
    "pd.documents_empty": {
        "tr": "Yüklenmiş şartname dokümanı yok.",
        "en": "No uploaded specification document.",
        "de": "Kein hochgeladenes Spezifikationsdokument.",
    },
    # --- Triage screen ---
    "triage.subtitle": {
        "tr": "Bir talep girin; sistem <b>kapsam içi / dışı / CR</b> kararı, efor aralığı, "
              "risk ve etkilenen modül kartları üretir. Sonuç üzerinden sohbetle <b>ön "
              "analiz</b> hazırlayıp vakaya kaydedebilirsiniz. Nihai karar PMO'dadır.",
        "en": "Enter a request; the system produces an <b>in scope / out of scope / CR</b> "
              "decision, an effort range, risk and impacted-module cards. Prepare a <b>pre-"
              "analysis</b> via chat over the result and save it to the case. The final "
              "decision rests with the PMO.",
        "de": "Geben Sie eine Anfrage ein; das System erstellt eine Entscheidung <b>im "
              "Umfang / außerhalb / CR</b>, eine Aufwandsspanne, Risiko und Karten der "
              "betroffenen Module. Erstellen Sie per Chat eine <b>Voranalyse</b> und "
              "speichern Sie sie im Fall. Die endgültige Entscheidung trifft das PMO.",
    },
    "triage.placeholder": {
        "tr": "Örn: Müşteri rapora yeni filtre eklensin, ayrıca login ekranına SSO eklensin dedi.",
        "en": "e.g. The client wants a new filter on the report, plus SSO on the login screen.",
        "de": "z. B. Der Kunde möchte einen neuen Filter im Bericht und SSO im Login.",
    },
    "triage.submit": {"tr": "Triyaj et", "en": "Run triage", "de": "Triage starten"},
    "triage.analyzing": {"tr": "analiz ediliyor…", "en": "analyzing…", "de": "wird analysiert…"},
    "triage.doc_analysis": {
        "tr": "Doküman ile Analiz", "en": "Analysis from document", "de": "Analyse aus Dokument",
    },
    "triage.doc_desc": {
        "tr": "Word/Excel/PDF/CSV yükleyin → her satırı <b>toplu triyaj</b> et, ya da "
              "<b>kapsam maddelerini</b> çıkar.",
        "en": "Upload Word/Excel/PDF/CSV → <b>batch-triage</b> each line, or <b>extract "
              "scope clauses</b>.",
        "de": "Word/Excel/PDF/CSV hochladen → jede Zeile <b>Stapel-Triage</b>, oder "
              "<b>Umfangsklauseln extrahieren</b>.",
    },
    "triage.mode_batch": {"tr": "Toplu triyaj", "en": "Batch triage", "de": "Stapel-Triage"},
    "triage.mode_scope": {
        "tr": "Kapsam çıkar", "en": "Extract scope", "de": "Umfang extrahieren",
    },
    "triage.upload_process": {
        "tr": "Yükle & İşle", "en": "Upload & process", "de": "Hochladen & verarbeiten",
    },
    "triage.processing": {"tr": "işleniyor…", "en": "processing…", "de": "wird verarbeitet…"},
    # --- List pages (approvals/history/analyses) ---
    "list.col_request": {"tr": "Talep", "en": "Request", "de": "Anfrage"},
    "list.col_decisions": {"tr": "Kararlar", "en": "Decisions", "de": "Entscheidungen"},
    "list.col_status": {"tr": "Durum", "en": "Status", "de": "Status"},
    "list.col_date": {"tr": "Tarih", "en": "Date", "de": "Datum"},
    "list.col_pre_analysis": {"tr": "Ön Analiz", "en": "Pre-analysis", "de": "Voranalyse"},
    "badge.escalation": {"tr": "eskalasyon", "en": "escalation", "de": "Eskalation"},
    "badge.analysis": {"tr": "analiz", "en": "analysis", "de": "Analyse"},
    "badge.ready": {"tr": "hazır", "en": "ready", "de": "bereit"},
    "list.go_triage": {"tr": "Triyaja git →", "en": "Go to triage →", "de": "Zur Triage →"},
    "onaylar.subtitle": {
        "tr": "{n} vaka dosyası · PMO onayı bekleyen talepler",
        "en": "{n} case files · requests awaiting PMO approval",
        "de": "{n} Fallakten · Anfragen, die auf PMO-Freigabe warten",
    },
    "list.empty_approvals": {
        "tr": "PMO kararı bekleyen talep yok.", "en": "No requests awaiting a PMO decision.",
        "de": "Keine Anfragen, die auf eine PMO-Entscheidung warten.",
    },
    "history.tab_all": {"tr": "Tümü ({n})", "en": "All ({n})", "de": "Alle ({n})"},
    "history.tab_pending": {
        "tr": "Bekleyen ({n})", "en": "Pending ({n})", "de": "Ausstehend ({n})",
    },
    "history.tab_analyses": {
        "tr": "Analizler ({n})", "en": "Analyses ({n})", "de": "Analysen ({n})",
    },
    "history.subtitle": {
        "tr": "{n} kayıt · bu projenin analiz ve triyaj geçmişi. ● ön analiz hazırlanmış talepler.",
        "en": "{n} records · analysis and triage history for this project. ● requests with a "
              "pre-analysis.",
        "de": "{n} Einträge · Analyse- und Triage-Verlauf dieses Projekts. ● Anfragen mit "
              "Voranalyse.",
    },
    "list.empty_history": {
        "tr": "Bu projede henüz analiz/triyaj geçmişi yok.",
        "en": "No analysis/triage history for this project yet.",
        "de": "Noch kein Analyse-/Triage-Verlauf für dieses Projekt.",
    },
    "analyses.subtitle": {
        "tr": "{n} analiz · PMO tarafından <b>onaylanan</b> vakalar projeye analiz olarak "
              "gelir. Geç gelen analiz öncekini geçersiz kılmaz; hepsi kayıtlı kalır.",
        "en": "{n} analyses · cases <b>approved</b> by the PMO arrive as project analyses. A "
              "later analysis does not invalidate earlier ones; all are kept.",
        "de": "{n} Analysen · vom PMO <b>genehmigte</b> Fälle erscheinen als Projektanalysen. "
              "Eine spätere Analyse hebt frühere nicht auf; alle bleiben erhalten.",
    },
    "list.empty_analyses": {
        "tr": "Henüz onaylanmış analiz yok.", "en": "No approved analyses yet.",
        "de": "Noch keine genehmigten Analysen.",
    },
    # --- Reports (KPI) ---
    "common.hours_short": {"tr": "sa", "en": "h", "de": "Std."},
    "common.minutes_short": {"tr": "dk", "en": "min", "de": "Min."},
    "rep.subtitle": {
        "tr": "KPI / Scorecard — düzeltme oranı, karara bağlanma, efor havuzu",
        "en": "KPI / Scorecard — correction rate, closure, effort pool",
        "de": "KPI / Scorecard — Korrekturrate, Abschlussquote, Aufwandspool",
    },
    "rep.total_cases": {"tr": "Toplam vaka", "en": "Total cases", "de": "Fälle gesamt"},
    "rep.override_rate": {
        "tr": "PMO düzeltme oranı (override)", "en": "PMO correction rate (override)",
        "de": "PMO-Korrekturrate (Override)",
    },
    "rep.corrections": {
        "tr": "{n} düzeltme", "en": "{n} corrections", "de": "{n} Korrekturen",
    },
    "rep.reconciliation": {
        "tr": "Karara bağlanma oranı", "en": "Decision closure rate",
        "de": "Entscheidungsquote",
    },
    "rep.avg_cr_hours": {
        "tr": "Ort. CR onay süresi", "en": "Avg. CR approval time", "de": "Ø CR-Freigabezeit",
    },
    "rep.baseline_version": {
        "tr": "Baseline sürümü", "en": "Baseline version", "de": "Baseline-Version",
    },
    "rep.decisions_dist": {
        "tr": "Kararlar (tip dağılımı)", "en": "Decisions (by type)",
        "de": "Entscheidungen (nach Typ)",
    },
    "rep.no_decisions": {"tr": "henüz karar yok", "en": "no decisions yet", "de": "noch keine Entscheidungen"},
    "deps.card_title": {"tr": "Bağımlılıklar", "en": "Dependencies", "de": "Abhängigkeiten"},
    "deps.package": {"tr": "Paket", "en": "Package", "de": "Paket"},
    "deps.spec": {"tr": "Sürüm koşulu", "en": "Version spec", "de": "Versionsangabe"},
    "deps.ecosystem": {"tr": "Ekosistem", "en": "Ecosystem", "de": "Ökosystem"},
    "deps.used_by": {"tr": "Kullanan modüller", "en": "Used by", "de": "Verwendet von"},
    "deps.latest": {"tr": "Güncel sürüm", "en": "Latest", "de": "Aktuell"},
    "deps.released": {"tr": "Yayın tarihi", "en": "Released", "de": "Veröffentlicht"},
    "deps.fetch_latest": {
        "tr": "Güncel sürümleri getir", "en": "Fetch latest versions",
        "de": "Aktuelle Versionen abrufen",
    },
    "deps.online_off": {
        "tr": "Çevrimiçi registry sorgusu kapalı (ETKI_DEPS_ONLINE) — manifest bilgileri geçerli.",
        "en": "Online registry lookup is off (ETKI_DEPS_ONLINE) — manifest facts stand alone.",
        "de": "Online-Registry-Abfrage ist aus (ETKI_DEPS_ONLINE) — Manifestdaten gelten.",
    },
    "vd.case_title": {
        "tr": "Paket karşılaştırması — {package}", "en": "Package comparison — {package}",
        "de": "Paketvergleich — {package}",
    },
    "vd.compare": {"tr": "Sürümleri karşılaştır", "en": "Compare versions", "de": "Versionen vergleichen"},
    "vd.old_ph": {"tr": "eski (42.0.0)", "en": "old (42.0.0)", "de": "alt (42.0.0)"},
    "vd.new_ph": {"tr": "yeni (46.0.3)", "en": "new (46.0.3)", "de": "neu (46.0.3)"},
    "vd.loading": {
        "tr": "paketler indiriliyor ve karşılaştırılıyor…",
        "en": "downloading and comparing packages…",
        "de": "Pakete werden geladen und verglichen…",
    },
    "vd.api_summary": {
        "tr": "API özeti: -{removed} / +{added} / ~{changed}",
        "en": "API summary: -{removed} / +{added} / ~{changed}",
        "de": "API-Übersicht: -{removed} / +{added} / ~{changed}",
    },
    "vd.your_code": {
        "tr": "Bu projenin kodu", "en": "This project's code", "de": "Code dieses Projekts",
    },
    "vd.no_usage": {
        "tr": "Bu paketi import eden kod bulunamadı — karşılaştırma yalnız genel API özetidir.",
        "en": "No code imports this package — the comparison is the general API summary only.",
        "de": "Kein Code importiert dieses Paket — nur die allgemeine API-Übersicht.",
    },
    "vd.broken": {
        "tr": "yeni sürümde YOK (kırılma)", "en": "MISSING in the new version (break)",
        "de": "FEHLT in der neuen Version (Bruch)",
    },
    "vd.hint": {"tr": "taşınmış olabilir", "en": "possibly moved", "de": "evtl. verschoben"},
    "vd.unresolved": {
        "tr": "çözümlenemedi — elle denetleyin (dinamik erişim olabilir)",
        "en": "unresolved — audit manually (may be dynamic access)",
        "de": "nicht auflösbar — manuell prüfen (evtl. dynamischer Zugriff)",
    },
    "vd.ok": {"tr": "{n} kullanım değişmemiş", "en": "{n} usage(s) unchanged", "de": "{n} Nutzung(en) unverändert"},
    "pre.dep_research_title": {
        "tr": "Paket araştırması — {package} {old} → {new} (bilgi amaçlı; karar sinyali değil)",
        "en": "Package research — {package} {old} → {new} (informational; never a decision signal)",
        "de": "Paketrecherche — {package} {old} → {new} (informativ; nie ein Entscheidungssignal)",
    },
    "pre.dep_broken": {
        "tr": "Kırılan kullanım", "en": "Broken usage", "de": "Brechende Nutzung",
    },
    "pre.dep_changed": {
        "tr": "İmzası değişen kullanım", "en": "Signature-changed usage",
        "de": "Nutzung mit geänderter Signatur",
    },
    "pre.dep_modules": {"tr": "modüller", "en": "modules", "de": "Module"},
    "vd.api_changes": {
        "tr": "API değişiklikleri ({removed} kaldırıldı · {changed} değişti · {added} eklendi)",
        "en": "API changes ({removed} removed · {changed} changed · {added} added)",
        "de": "API-Änderungen ({removed} entfernt · {changed} geändert · {added} hinzugefügt)",
    },
    "vd.used_hits": {
        "tr": "Bu projenin kullandığı semboller",
        "en": "Symbols this project uses",
        "de": "Von diesem Projekt genutzte Symbole",
    },
    "vd.removed_h": {"tr": "Kaldırılan", "en": "Removed", "de": "Entfernt"},
    "vd.changed_h": {"tr": "İmzası değişen", "en": "Signature changed", "de": "Signatur geändert"},
    "vd.added_h": {"tr": "Eklenen", "en": "Added", "de": "Hinzugefügt"},
    "vd.more": {"tr": "… +{n} daha", "en": "… +{n} more", "de": "… +{n} weitere"},
    "vd.no_api_changes": {
        "tr": "İki sürümün dışa açık API'si aynı.",
        "en": "The exported API is identical across the two versions.",
        "de": "Die exportierte API ist in beiden Versionen identisch.",
    },
    "vd.vulns": {"tr": "Bilinen zafiyetler (OSV)", "en": "Known vulnerabilities (OSV)", "de": "Bekannte Schwachstellen (OSV)"},
    "vd.clean": {"tr": "bilinen zafiyet yok", "en": "no known vulnerabilities", "de": "keine bekannten Schwachstellen"},
    "deps.none": {
        "tr": "Manifest bulunamadı (requirements.txt / package.json / pom.xml…) — yeniden indeksleme sonrası dolar.",
        "en": "No manifest found (requirements.txt / package.json / pom.xml…) — populated after a re-index.",
        "de": "Kein Manifest gefunden (requirements.txt / package.json / pom.xml…) — nach Neuindexierung befüllt.",
    },
    "nav.memory": {"tr": "Hafıza", "en": "Memory", "de": "Gedächtnis"},
    "mem.subtitle": {
        "tr": "Karar wiki'si, emsaller ve ihtilaflı maddeler — geçmiş kararların kurumsal hafızası",
        "en": "Decision wiki, precedents and disputed clauses — the institutional memory of past rulings",
        "de": "Entscheidungs-Wiki, Präzedenzfälle und strittige Klauseln — das institutionelle Gedächtnis",
    },
    "mem.search_placeholder": {
        "tr": "Karar hafızasında ara (ör. SSO, ödeme sağlayıcı)…",
        "en": "Search the decision memory (e.g. SSO, payment provider)…",
        "de": "Im Entscheidungsgedächtnis suchen (z. B. SSO)…",
    },
    "mem.search_btn": {"tr": "Ara", "en": "Search", "de": "Suchen"},
    "mem.results": {"tr": "{n} sonuç", "en": "{n} result(s)", "de": "{n} Treffer"},
    "mem.no_results": {"tr": "Eşleşme yok.", "en": "No matches.", "de": "Keine Treffer."},
    "mem.disputed_title": {
        "tr": "İhtilaflı maddeler ({n})", "en": "Disputed clauses ({n})",
        "de": "Strittige Klauseln ({n})",
    },
    "mem.disputed_desc": {
        "tr": "Aynı maddeye çelişen nihai kararlar — bu maddelere yeniden karar vermeden önce geçmişi okuyun.",
        "en": "Conflicting final rulings on the same clause — read the history before ruling again.",
        "de": "Widersprüchliche finale Entscheidungen zur selben Klausel — vor erneuter Entscheidung lesen.",
    },
    "mem.precedents_title": {
        "tr": "Emsaller — PMO düzeltmeleri ({n})", "en": "Precedents — PMO corrections ({n})",
        "de": "Präzedenzfälle — PMO-Korrekturen ({n})",
    },
    "mem.wiki_off": {
        "tr": "Karar wiki'si kapalı (ETKI_WIKI_DIR boş) — arama devre dışı; emsal ve ihtilaf kartları yine de veritabanından hesaplanır.",
        "en": "The decision wiki is off (ETKI_WIKI_DIR empty) — search is unavailable; precedent and dispute cards are still computed from the database.",
        "de": "Das Entscheidungs-Wiki ist aus (ETKI_WIKI_DIR leer) — Suche nicht verfügbar; Präzedenz- und Streitkarten kommen weiterhin aus der Datenbank.",
    },
    "mem.no_disputes": {
        "tr": "İhtilaf yok — aynı maddeye çelişen nihai karar verilmedi.",
        "en": "No disputes — no conflicting final rulings on the same clause.",
        "de": "Keine Streitfälle — keine widersprüchlichen finalen Entscheidungen zur selben Klausel.",
    },
    "mem.no_precedents": {
        "tr": "Henüz emsal yok — PMO bir sistem önerisini düzelttiğinde burada birikir.",
        "en": "No precedents yet — they accumulate here when the PMO corrects a system recommendation.",
        "de": "Noch keine Präzedenzfälle — sie entstehen, wenn das PMO eine Systemempfehlung korrigiert.",
    },
    "mem.files_title": {
        "tr": "Karar dosyaları ({n})",
        "en": "Decision files ({n})",
        "de": "Entscheidungsdateien ({n})",
    },
    "mem.files_projection": {
        "tr": "Wiki projeksiyonu — tek kaynak veritabanıdır; dosyalar yeniden üretilebilir.",
        "en": "Wiki projection — the database is the single source of truth; files are regenerable.",
        "de": "Wiki-Projektion — die Datenbank ist die einzige Quelle; Dateien sind regenerierbar.",
    },
    "mem.no_files": {
        "tr": "Henüz karar dosyası yok — kararlar sonuçlandıkça wiki projeksiyonu burada listelenir.",
        "en": "No decision files yet — the wiki projection lists them here as decisions resolve.",
        "de": "Noch keine Entscheidungsdateien — die Wiki-Projektion listet sie hier, sobald Entscheidungen fallen.",
    },
    "cf.memory_title": {"tr": "Madde hafızası", "en": "Clause memory", "de": "Klausel-Gedächtnis"},
    "cf.memory_precedents": {
        "tr": "{n} geçmiş PMO düzeltmesi (emsal)", "en": "{n} past PMO correction(s) (precedent)",
        "de": "{n} frühere PMO-Korrektur(en) (Präzedenzfall)",
    },
    "cf.memory_last": {"tr": "son: {v}", "en": "last: {v}", "de": "zuletzt: {v}"},
    "cf.memory_disputed": {
        "tr": "İhtilaflı madde — geçmişte çelişen kararlar var",
        "en": "Disputed clause — conflicting past rulings exist",
        "de": "Strittige Klausel — widersprüchliche frühere Entscheidungen",
    },
    "rep.precedents": {"tr": "Emsal kararlar", "en": "Precedent decisions", "de": "Präzedenzentscheidungen"},
    "rep.disputed": {"tr": "İhtilaflı madde", "en": "Disputed clauses", "de": "Strittige Klauseln"},
    # --- Decision-wiki markdown headings (rendered in the PROJECT's language;
    #     tr values must stay byte-identical to the original literals) ---
    "wiki.autogen_case": {
        "tr": "Bu dosya veritabanındaki vaka kaydının otomatik projeksiyonudur — elle\ndüzenlemeyin (`python -m etki.wiki rebuild` üzerine yazar).",
        "en": "This file is an automatic projection of the case record in the database — do not\nedit by hand (`python -m etki.wiki rebuild` overwrites it).",
        "de": "Diese Datei ist eine automatische Projektion des Falls aus der Datenbank — nicht\nmanuell bearbeiten (`python -m etki.wiki rebuild` überschreibt sie).",
    },
    "wiki.autogen_override": {
        "tr": "Bu dosya veritabanındaki override kaydının otomatik projeksiyonudur — elle\ndüzenlemeyin (`python -m etki.wiki rebuild` üzerine yazar).",
        "en": "This file is an automatic projection of the override record in the database — do not\nedit by hand (`python -m etki.wiki rebuild` overwrites it).",
        "de": "Diese Datei ist eine automatische Projektion des Override-Eintrags aus der Datenbank —\nnicht manuell bearbeiten (`python -m etki.wiki rebuild` überschreibt sie).",
    },
    "wiki.request": {"tr": "Talep", "en": "Request", "de": "Anfrage"},
    "wiki.decision_heading": {
        "tr": "Karar {n} — {decision} (güven: {conf})",
        "en": "Decision {n} — {decision} (confidence: {conf})",
        "de": "Entscheidung {n} — {decision} (Konfidenz: {conf})",
    },
    "wiki.pmo_decision": {"tr": "PMO kararı", "en": "PMO decision", "de": "PMO-Entscheidung"},
    "wiki.reasoning": {"tr": "Gerekçe", "en": "Reasoning", "de": "Begründung"},
    "wiki.cited": {"tr": "Dayanak maddeler", "en": "Cited clauses", "de": "Zitierte Klauseln"},
    "wiki.impacted": {"tr": "Etkilenen modüller", "en": "Impacted modules", "de": "Betroffene Module"},
    "wiki.effort": {"tr": "Efor", "en": "Effort", "de": "Aufwand"},
    "wiki.risk": {"tr": "Risk", "en": "Risk", "de": "Risiko"},
    "wiki.assumptions": {"tr": "Varsayımlar", "en": "Assumptions", "de": "Annahmen"},
    "wiki.cr_draft": {
        "tr": "CR taslağı — yayılım analizi", "en": "CR draft — impact analysis",
        "de": "CR-Entwurf — Auswirkungsanalyse",
    },
    "wiki.pre_analysis": {"tr": "Ön analiz", "en": "Pre-analysis", "de": "Voranalyse"},
    "wiki.precedent_title": {
        "tr": "emsal (PMO düzeltmesi)", "en": "precedent (PMO correction)",
        "de": "Präzedenzfall (PMO-Korrektur)",
    },
    "wiki.why_precedent": {"tr": "Neden emsal?", "en": "Why a precedent?", "de": "Warum Präzedenzfall?"},
    "wiki.override_line": {
        "tr": "Karar {n}: sistem **{sys}** dedi, PMO **{human}** olarak düzeltti ({who}).",
        "en": "Decision {n}: the system said **{sys}**, the PMO corrected it to **{human}** ({who}).",
        "de": "Entscheidung {n}: das System sagte **{sys}**, die PMO korrigierte zu **{human}** ({who}).",
    },
    "wiki.decision_file": {"tr": "Karar dosyası", "en": "Decision file", "de": "Entscheidungsdatei"},
    "wiki.disputed_title": {"tr": "İhtilaflı maddeler", "en": "Disputed clauses", "de": "Strittige Klauseln"},
    "wiki.disputed_note": {
        "tr": "Aynı sözleşme maddesine ÇELİŞEN nihai kararlar. Otomatik üretilir —\nbu maddeye yeniden karar vermeden önce buradaki geçmişi okuyun.",
        "en": "CONFLICTING final rulings on the same contract clause. Auto-generated —\nread this history before ruling on the clause again.",
        "de": "WIDERSPRÜCHLICHE finale Entscheidungen zur selben Vertragsklausel. Automatisch erzeugt —\nvor einer erneuten Entscheidung diese Historie lesen.",
    },
    "wiki.index_title": {"tr": "Karar wiki'si", "en": "Decision wiki", "de": "Entscheidungs-Wiki"},
    "wiki.index_autogen": {
        "tr": "Otomatik üretilir — elle düzenlemeyin.", "en": "Auto-generated — do not edit by hand.",
        "de": "Automatisch erzeugt — nicht manuell bearbeiten.",
    },
    "wiki.total": {"tr": "Toplam karar dosyası", "en": "Total decision files", "de": "Entscheidungsdateien gesamt"},
    "wiki.dist": {"tr": "Karar dağılımı", "en": "Verdict distribution", "de": "Entscheidungsverteilung"},
    "wiki.precedent_files": {
        "tr": "Emsal (override) dosyası", "en": "Precedent (override) files",
        "de": "Präzedenzfall-Dateien (Overrides)",
    },
    "wiki.disputed_link": {
        "tr": "⚠ [İhtilaflı maddeler](disputed.md) mevcut",
        "en": "⚠ [Disputed clauses](disputed.md) exist",
        "de": "⚠ [Strittige Klauseln](disputed.md) vorhanden",
    },
    "wiki.recent": {"tr": "Son kararlar", "en": "Recent decisions", "de": "Letzte Entscheidungen"},
    "wiki.module_backlinks": {
        "tr": "modülünü etkileyen kararlar", "en": "decisions touching this module",
        "de": "Entscheidungen zu diesem Modul",
    },
    "wiki.contract_backlinks": {
        "tr": "sözleşmesine atıf yapan kararlar", "en": "decisions citing this contract",
        "de": "Entscheidungen mit Bezug auf diesen Vertrag",
    },
    "rep.effort_pool": {"tr": "Efor Havuzu", "en": "Effort Pool", "de": "Aufwandspool"},
    "rep.no_effort_pool": {
        "tr": "efor havuzu tanımlı madde yok", "en": "no clause with a defined effort pool",
        "de": "keine Klausel mit definiertem Aufwandspool",
    },
    "rep.pool_degraded_note": {
        "tr": "Efor kaynağına ulaşılamıyor — havuz tüketimi güncel olmayabilir.",
        "en": "Effort source unreachable — pool consumption may be out of date.",
        "de": "Aufwandsquelle nicht erreichbar — Poolverbrauch ist evtl. nicht aktuell.",
    },
    "rep.kpi_defs": {
        "tr": "KPI tanımları (nasıl hesaplanır?)", "en": "KPI definitions (how computed?)",
        "de": "KPI-Definitionen (wie berechnet?)",
    },
    "rep.def_override_t": {
        "tr": "PMO düzeltme oranı (override)", "en": "PMO correction rate (override)",
        "de": "PMO-Korrekturrate (Override)",
    },
    "rep.def_override_d": {
        "tr": "PMO'nun sistem önerisini değiştirdiği karar / toplam karar.",
        "en": "Decisions where the PMO changed the system suggestion / total decisions.",
        "de": "Entscheidungen, bei denen das PMO den Systemvorschlag geändert hat / Gesamt.",
    },
    "rep.def_recon_t": {
        "tr": "Karara bağlanma oranı", "en": "Decision closure rate",
        "de": "Entscheidungsquote",
    },
    "rep.def_recon_d": {
        "tr": "Karara bağlanmış (onay/red/CR) vaka / toplam vaka.",
        "en": "Decided (approve/reject/CR) cases / total cases.",
        "de": "Entschiedene (Freigabe/Ablehnung/CR) Fälle / Gesamtfälle.",
    },
    "rep.def_cr_t": {"tr": "CR onay süresi", "en": "CR approval time", "de": "CR-Freigabezeit"},
    "rep.def_cr_d": {
        "tr": "Triyaj olayı → PMO kararı arası ortalama saat (denetim izinden).",
        "en": "Average hours from triage event to PMO decision (from the audit trail).",
        "de": "Durchschn. Stunden vom Triage-Ereignis bis zur PMO-Entscheidung (Audit-Trail).",
    },
    "rep.def_baseline_t": {
        "tr": "Baseline sürümü", "en": "Baseline version", "de": "Baseline-Version",
    },
    "rep.def_baseline_d": {
        "tr": "Her onaylı CR baseline'a madde ekler → sürüm +1 (yaşayan baseline).",
        "en": "Each approved CR adds a clause to the baseline → version +1 (living baseline).",
        "de": "Jeder genehmigte CR fügt eine Klausel hinzu → Version +1 (lebende Baseline).",
    },
    "rep.def_pool_t": {"tr": "Efor havuzu", "en": "Effort pool", "de": "Aufwandspool"},
    "rep.def_pool_d": {
        "tr": "🟢 &lt;%60 · 🟡 %60–85 · 🔴 %85+ → yeni talepler büyük olasılıkla CR olmalı.",
        "en": "🟢 &lt;60% · 🟡 60–85% · 🔴 85%+ → new requests are likely CRs.",
        "de": "🟢 &lt;60 % · 🟡 60–85 % · 🔴 85 %+ → neue Anfragen sind wahrscheinlich CRs.",
    },
    "rep.calibration_summary": {
        "tr": "Geri besleme (eşik kalibrasyonu) — {n} öneri",
        "en": "Feedback (threshold calibration) — {n} suggestions",
        "de": "Feedback (Schwellenkalibrierung) — {n} Vorschläge",
    },
    "rep.no_override_suggestions": {
        "tr": "henüz override yok — öneri yok", "en": "no overrides yet — no suggestions",
        "de": "noch keine Overrides — keine Vorschläge",
    },
    "rep.calibration_note": {
        "tr": "Öneriler otomatik uygulanmaz; eşikler config-güdümlüdür, PMO onaylar.",
        "en": "Suggestions are not auto-applied; thresholds are config-driven, the PMO approves.",
        "de": "Vorschläge werden nicht automatisch angewendet; Schwellen sind konfigurierbar, "
              "das PMO genehmigt.",
    },
    # --- macros: plain summary + glossary + evidence chain ---
    "ps.IN_SCOPE": {
        "tr": "Kapsam içinde — sözleşme kapsamında, normal akışla yapılır.",
        "en": "In scope — within the contract, handled in the normal flow.",
        "de": "Im Umfang — innerhalb des Vertrags, im normalen Ablauf.",
    },
    "ps.OUT_OF_SCOPE": {
        "tr": "Kapsam dışı — ek ücretli Değişiklik Talebi (CR) gerekir.",
        "en": "Out of scope — a paid Change Request (CR) is required.",
        "de": "Außerhalb des Umfangs — ein kostenpflichtiger Änderungsantrag (CR) ist nötig.",
    },
    "ps.CR_CANDIDATE": {
        "tr": "CR adayı — ayrıca fiyatlandırılmalı (kapsam genişliyor).",
        "en": "CR candidate — should be priced separately (scope expands).",
        "de": "CR-Kandidat — sollte separat bepreist werden (Umfang wächst).",
    },
    "ps.GRAY_AREA": {
        "tr": "Belirsiz (gri alan) — net değil, PMO kararı gerekiyor.",
        "en": "Uncertain (gray area) — unclear, PMO decision needed.",
        "de": "Unklar (Graubereich) — nicht eindeutig, PMO-Entscheidung nötig.",
    },
    "ps.MAINTENANCE": {
        "tr": "Bakım kapsamında — bakım akışıyla ele alınır.",
        "en": "Within maintenance — handled in the maintenance flow.",
        "de": "Innerhalb der Wartung — im Wartungsablauf behandelt.",
    },
    "ps.effort": {"tr": "Efor", "en": "Effort", "de": "Aufwand"},
    "ev.escalation_24": {
        "tr": "24s ESKALASYON", "en": "24h ESCALATION", "de": "24-STD-ESKALATION",
    },
    "gl.title": {"tr": "Sözlük (terimler)", "en": "Glossary (terms)", "de": "Glossar (Begriffe)"},
    "gl.cr_t": {"tr": "CR (Değişiklik Talebi)", "en": "CR (Change Request)", "de": "CR (Änderungsantrag)"},
    "gl.cr_d": {
        "tr": "Sözleşme kapsamı dışında, ayrıca fiyatlanan iş.",
        "en": "Work outside the contract scope, priced separately.",
        "de": "Arbeit außerhalb des Vertragsumfangs, separat bepreist.",
    },
    "gl.baseline_t": {"tr": "Baseline", "en": "Baseline", "de": "Baseline"},
    "gl.baseline_d": {
        "tr": "Onaylı, \"dondurulmuş\" kapsam referansı; her şey buna göre ölçülür.",
        "en": "Approved, \"frozen\" scope reference; everything is measured against it.",
        "de": "Genehmigte, \"eingefrorene\" Umfangsreferenz; alles wird daran gemessen.",
    },
    "gl.scope_item_t": {
        "tr": "Kapsam maddesi (scope item)", "en": "Scope item", "de": "Umfangselement (Scope Item)",
    },
    "gl.scope_item_d": {
        "tr": "Sözleşmedeki tek bir kapsam kaleminin yapılandırılmış hali.",
        "en": "The structured form of a single scope item in the contract.",
        "de": "Die strukturierte Form eines einzelnen Umfangselements im Vertrag.",
    },
    "gl.excluded_t": {
        "tr": "Kapsam dışı (EXCLUDED)", "en": "Out of scope (EXCLUDED)",
        "de": "Außerhalb des Umfangs (EXCLUDED)",
    },
    "gl.excluded_d": {
        "tr": "Sözleşmede açıkça hariç tutulmuş; en güçlü \"yapılmaz\" kanıtı.",
        "en": "Explicitly excluded in the contract; the strongest \"won't do\" evidence.",
        "de": "Im Vertrag ausdrücklich ausgeschlossen; der stärkste \"wird nicht gemacht\"-Beleg.",
    },
    "gl.impact_t": {"tr": "Yayılım analizi", "en": "Impact analysis", "de": "Wirkungsanalyse"},
    "gl.impact_d": {
        "tr": "Bir talebin kodda nereleri etkileyeceği (etkilenen modüller).",
        "en": "Where in the code a request will have an effect (impacted modules).",
        "de": "Wo im Code eine Anfrage wirkt (betroffene Module).",
    },
    "gl.churn_t": {"tr": "Churn", "en": "Churn", "de": "Churn"},
    "gl.churn_d": {
        "tr": "Bir kod parçasının ne sıklıkla değiştiği — belirsizlik göstergesi.",
        "en": "How often a piece of code changes — an uncertainty indicator.",
        "de": "Wie oft sich ein Codeabschnitt ändert — ein Unsicherheitsindikator.",
    },
    "gl.pert_t": {"tr": "Efor aralığı (PERT)", "en": "Effort range (PERT)", "de": "Aufwandsspanne (PERT)"},
    "gl.pert_d": {
        "tr": "Tek sayı yerine iyimser–kötümser aralık; erken tahmin belirsizdir.",
        "en": "An optimistic–pessimistic range instead of a single number; early estimates are uncertain.",
        "de": "Eine optimistisch–pessimistische Spanne statt einer einzelnen Zahl; frühe Schätzungen sind unsicher.",
    },
    "gl.gray_t": {"tr": "Gri alan", "en": "Gray area", "de": "Graubereich"},
    "gl.gray_d": {
        "tr": "Kanıt kesin değil → karar PMO'ya bırakılır.",
        "en": "Evidence is not conclusive → the decision is left to the PMO.",
        "de": "Belege sind nicht eindeutig → die Entscheidung liegt beim PMO.",
    },
    "ev.title": {
        "tr": "Kanıt zinciri & detay", "en": "Evidence chain & detail", "de": "Beweiskette & Detail",
    },
    "ev.decision": {"tr": "Karar", "en": "Decision", "de": "Entscheidung"},
    "ev.confidence": {"tr": "güven", "en": "confidence", "de": "Konfidenz"},
    "ev.reasoning": {"tr": "Gerekçe", "en": "Reasoning", "de": "Begründung"},
    "ev.best_match": {"tr": "En iyi eşleşme", "en": "Best match", "de": "Beste Übereinstimmung"},
    "ev.similarity": {"tr": "benzerlik", "en": "similarity", "de": "Ähnlichkeit"},
    "ev.cited_clause": {"tr": "Atıf yapılan madde", "en": "Cited clause", "de": "Zitierte Klausel"},
    "ev.source_coverage": {"tr": "Kaynak kapsamı", "en": "Source coverage", "de": "Quellenabdeckung"},
    "ev.assumptions": {"tr": "Varsayımlar", "en": "Assumptions", "de": "Annahmen"},
    "ev.checked": {"tr": "Kontrol edilen maddeler", "en": "Clauses checked", "de": "Geprüfte Klauseln"},
    "ev.checked_n": {"tr": "{n} madde —", "en": "{n} clauses —", "de": "{n} Klauseln —"},
    "ev.impacted_modules": {
        "tr": "Etkilenen kod modülleri", "en": "Impacted code modules", "de": "Betroffene Codemodule",
    },
    "ev.col_module": {"tr": "modül", "en": "module", "de": "Modul"},
    "ev.col_complexity": {"tr": "karmaşıklık", "en": "complexity", "de": "Komplexität"},
    "ev.col_churn_sub": {"tr": "(commit/6ay)", "en": "(commits/6mo)", "de": "(Commits/6 Mon.)"},
    "ev.effort_est": {"tr": "Efor tahmini", "en": "Effort estimate", "de": "Aufwandsschätzung"},
    # --- Deterministic pre-analysis (web._deterministic_pre_analysis) ---
    "pre.auto_title": {"tr": "Otomatik ön analiz", "en": "Automatic pre-analysis", "de": "Automatische Voranalyse"},
    "pre.signal": {
        "tr": "{loc} satır, karmaşıklık {cyc}, churn {churn}",
        "en": "{loc} lines, complexity {cyc}, churn {churn}",
        "de": "{loc} Zeilen, Komplexität {cyc}, Churn {churn}",
    },
    "pre.related_clauses": {"tr": "İlgili maddeler", "en": "Related clauses", "de": "Zugehörige Klauseln"},
    "ev.risk": {"tr": "Risk", "en": "Risk", "de": "Risiko"},
    "ev.risk_formula": {
        "tr": "= olasılık <b>{p}</b> × etki <b>{i}</b>",
        "en": "= probability <b>{p}</b> × impact <b>{i}</b>",
        "de": "= Wahrscheinlichkeit <b>{p}</b> × Auswirkung <b>{i}</b>",
    },
    "ev.risk_basis": {"tr": "dayanak", "en": "basis", "de": "Grundlage"},
    "ev.risk_signals": {"tr": "Risk sinyalleri", "en": "Risk signals", "de": "Risikosignale"},
    "ev.cr_draft": {"tr": "CR taslağı", "en": "CR draft", "de": "CR-Entwurf"},
    "ev.cr_effort": {"tr": "Tahmini efor", "en": "Estimated effort", "de": "Geschätzter Aufwand"},
    "ev.auditability": {"tr": "Denetlenebilirlik", "en": "Auditability", "de": "Nachvollziehbarkeit"},
    "ev.audit_line": {
        "tr": "model {m} · indeks tazeliği {f} · PMO kararı: {d}",
        "en": "model {m} · index freshness {f} · PMO decision: {d}",
        "de": "Modell {m} · Index-Aktualität {f} · PMO-Entscheidung: {d}",
    },
    "ev.plugin_set": {"tr": "Eklentiler", "en": "Plugins", "de": "Plugins"},
    "ev.cited_header": {
        "tr": "Atıf yapılan madde(ler) — sözleşme içeriği:",
        "en": "Cited clause(s) — contract content:",
        "de": "Zitierte Klausel(n) — Vertragsinhalt:",
    },
    "ev.limit": {"tr": "Limit: en fazla", "en": "Limit: at most", "de": "Limit: höchstens"},
    "ev.effort_pool": {"tr": "Efor havuzu", "en": "Effort pool", "de": "Aufwandspool"},
    "ev.mapped_modules": {
        "tr": "Eşlenen kod modülleri", "en": "Mapped code modules", "de": "Zugeordnete Codemodule",
    },
    # --- Case file (review) ---
    "cf.case_file": {"tr": "Vaka Dosyası", "en": "Case File", "de": "Fallakte"},
    "cf.project": {"tr": "Proje", "en": "Project", "de": "Projekt"},
    "cf.status": {"tr": "Durum", "en": "Status", "de": "Status"},
    "cf.download_report": {
        "tr": "📄 Rapor indir (.docx)", "en": "📄 Download report (.docx)",
        "de": "📄 Bericht herunterladen (.docx)",
    },
    "cf.pre_analysis": {"tr": "Ön Analiz", "en": "Pre-analysis", "de": "Voranalyse"},
    "cf.pre_analysis_chat": {
        "tr": "Ön Analiz Sohbeti", "en": "Pre-analysis Chat", "de": "Voranalyse-Chat",
    },
    "cf.turns": {"tr": "{n} tur", "en": "{n} turns", "de": "{n} Runden"},
    "cf.impacted": {"tr": "Etkilenen", "en": "Impacted", "de": "Betroffen"},
    "cf.approve": {
        "tr": "'{decision}' kararını onayla", "en": "Approve '{decision}'",
        "de": "'{decision}' genehmigen",
    },
    "cf.to_cr": {"tr": "CR'a çevir", "en": "Convert to CR", "de": "In CR umwandeln"},
    "cf.reject": {"tr": "Reddet", "en": "Reject", "de": "Ablehnen"},
    "cf.approve_confirm": {
        "tr": "Sistemin kararı onaylansın mı? Bu işlem denetim izine yazılır ve geri alınamaz.",
        "en": "Approve the system's decision? This is written to the audit trail and cannot be undone.",
        "de": "Entscheidung des Systems genehmigen? Dies wird im Audit-Trail vermerkt und kann "
              "nicht rückgängig gemacht werden.",
    },
    "cf.to_cr_confirm": {
        "tr": "Karar Değişiklik Talebi'ne (CR) çevrilsin mi? CR onayı yaşayan kapsam baseline'ına "
              "yeni madde ekler (sürüm +1) ve geri alınamaz.",
        "en": "Convert this decision to a Change Request (CR)? CR approval adds a new item to the "
              "living scope baseline (version +1) and cannot be undone.",
        "de": "Entscheidung in einen Änderungsantrag (CR) umwandeln? Die CR-Genehmigung fügt der "
              "lebenden Baseline einen neuen Punkt hinzu (Version +1) und ist unwiderruflich.",
    },
    "cf.reject_confirm": {
        "tr": "Karar reddedilsin mi? Bu işlem denetim izine yazılır ve geri alınamaz.",
        "en": "Reject this decision? This is written to the audit trail and cannot be undone.",
        "de": "Entscheidung ablehnen? Dies wird im Audit-Trail vermerkt und kann nicht rückgängig "
              "gemacht werden.",
    },
    "cf.impacted_if_cr": {
        "tr": "CR kabul edilirse etkilenecek",
        "en": "Impacted if the CR is accepted",
        "de": "Betroffen, falls der CR angenommen wird",
    },
    "ps.effort_if_cr": {
        "tr": "CR kabul edilirse tahmini efor",
        "en": "Estimated effort if the CR is accepted",
        "de": "Geschätzter Aufwand, falls der CR angenommen wird",
    },
    "cf.audit_summary": {
        "tr": "Denetim izi — {n} olay (sözleşmesel ihtilaf için yeniden kurgulanabilir)",
        "en": "Audit trail — {n} events (reconstructable for a contractual dispute)",
        "de": "Audit-Trail — {n} Ereignisse (für Vertragsstreit rekonstruierbar)",
    },
    "cf.how_to_read": {
        "tr": "Bu ekran nasıl okunur?", "en": "How to read this screen?",
        "de": "Wie lese ich diesen Bildschirm?",
    },
    "cf.back_approvals": {
        "tr": "Onay kuyruğuna dön", "en": "Back to the approval queue",
        "de": "Zurück zur Freigabe-Warteschlange",
    },
    # --- Index-run history fragment ---
    "ih.link": {"tr": "geçmiş →", "en": "history →", "de": "Verlauf →"},
    "ih.row": {
        "tr": "{m} modül · {c} madde indekslendi", "en": "{m} modules · {c} clauses indexed",
        "de": "{m} Module · {c} Klauseln indexiert",
    },
    "ih.empty": {
        "tr": "Kayıtlı indeksleme koşusu yok — bir sonraki yeniden indekslemeden itibaren burada listelenir.",
        "en": "No recorded index runs yet — they will be listed here from the next re-index on.",
        "de": "Noch keine aufgezeichneten Indexläufe — ab der nächsten Neuindexierung erscheinen sie hier.",
    },
    # --- Ask screen (instant answers over the knowledge graph) ---
    "nav.ask": {"tr": "Sor", "en": "Ask", "de": "Fragen"},
    "ask.title": {"tr": "Sor", "en": "Ask", "de": "Fragen"},
    "ask.subtitle": {
        "tr": "Tek soru, etiketli yanıtlar: önce <b>bilgi grafiğinden deterministik</b> yanıt (anında, LLM'siz); "
              "yapay zekâ yapılandırılmışsa <b>asistan yanıtı</b> otomatik eklenir. Geliştirici de PMO da kullanabilir.",
        "en": "One question, labeled answers: the <b>deterministic knowledge-graph</b> answer first (instant, no LLM); "
              "when an AI is configured the <b>assistant's answer</b> follows automatically. For developers and PMO alike.",
        "de": "Eine Frage, gekennzeichnete Antworten: zuerst die <b>deterministische Wissensgraph-Antwort</b> (sofort, ohne LLM); "
              "ist eine KI konfiguriert, folgt die <b>Assistenten-Antwort</b> automatisch. Für Entwickler und PMO.",
    },
    "ask.placeholder": {
        "tr": "Örn: raporlama modülüne dokunursam ne etkilenir? / SSO kapsamda mı?",
        "en": "E.g.: what is impacted if I touch the reporting module? / is SSO in scope?",
        "de": "z. B.: Was ist betroffen, wenn ich das Reporting-Modul ändere? / Ist SSO im Umfang?",
    },
    "ask.send": {"tr": "Sor", "en": "Ask", "de": "Fragen"},
    "ask.src_graph": {
        "tr": "BİLGİ GRAFİĞİ · DETERMİNİSTİK", "en": "KNOWLEDGE GRAPH · DETERMINISTIC",
        "de": "WISSENSGRAPH · DETERMINISTISCH",
    },
    "ask.src_llm": {"tr": "YAPAY ZEKÂ", "en": "AI", "de": "KI"},
    "ask.llm_wait": {
        "tr": "yapay zekâ yanıtlıyor…", "en": "the AI is answering…", "de": "die KI antwortet…",
    },
    "ask.grounded": {
        "tr": "deterministik yanıt bağlam olarak verildi",
        "en": "grounded in the deterministic answer",
        "de": "auf der deterministischen Antwort fundiert",
    },
    "ask.searching": {"tr": "aranıyor…", "en": "searching…", "de": "suche…"},
    "ask.examples": {
        "tr": "İpuçları: \"…nin komşuları/etkisi\" genişletme yapar; \"kaç/hangi/listele\" araç sorgusu dener; diğerleri benzerlik araması.",
        "en": "Hints: \"neighbours/impact of …\" expands the graph; \"how many/which/list\" tries a tool query; anything else is a similarity search.",
        "de": "Hinweise: \"Nachbarn/Auswirkung von …\" erweitert den Graphen; \"wie viele/welche/liste\" versucht eine Tool-Abfrage; sonst Ähnlichkeitssuche.",
    },
    "ask.strategy": {"tr": "Strateji", "en": "Strategy", "de": "Strategie"},
    "ask.tool": {"tr": "Araç", "en": "Tool", "de": "Werkzeug"},
    "ask.packing": {"tr": "paketleme", "en": "packing", "de": "Packung"},
    "ask.truncated": {"tr": "bütçe doldu (kırpıldı)", "en": "budget hit (truncated)", "de": "Budget erreicht (gekürzt)"},
    "ask.kind_scope": {"tr": "MADDE", "en": "CLAUSE", "de": "KLAUSEL"},
    "ask.kind_module": {"tr": "MODÜL", "en": "MODULE", "de": "MODUL"},
    "ask.kind_package": {"tr": "PAKET", "en": "PACKAGE", "de": "PAKET"},
    "ask.kind_workitem": {"tr": "İŞ KAYDI", "en": "WORK ITEM", "de": "ARBEITSEINTRAG"},
    "ask.empty": {
        "tr": "Eşleşen düğüm bulunamadı — soruyu farklı sözcüklerle deneyin.",
        "en": "No matching nodes — try rewording the question.",
        "de": "Keine passenden Knoten — formulieren Sie die Frage um.",
    },
    "ask.no_index": {
        "tr": "Proje indeksi yok — önce projeyi indeksleyin.",
        "en": "The project has no index yet — index it first.",
        "de": "Das Projekt hat noch keinen Index — zuerst indexieren.",
    },
    "ask.failed": {
        "tr": "Sorgu çalıştırılamadı.", "en": "The query could not be run.",
        "de": "Die Abfrage konnte nicht ausgeführt werden.",
    },
    # --- Baseline timeline screen ---
    "bl.title": {
        "tr": "Baseline Sürüm Geçmişi", "en": "Baseline Version History",
        "de": "Baseline-Versionsverlauf",
    },
    "bl.subtitle": {
        "tr": "Güncel sürüm v{v} — her onaylı CR kapsamı bir sürüm ilerletir (yaşayan baseline).",
        "en": "Current version v{v} — every approved CR advances the scope by one version (living baseline).",
        "de": "Aktuelle Version v{v} — jeder genehmigte CR erhöht den Umfang um eine Version.",
    },
    "bl.item_count": {"tr": "{n} madde", "en": "{n} clauses", "de": "{n} Klauseln"},
    "bl.source_case": {"tr": "kaynak vaka", "en": "source case", "de": "Quellfall"},
    "bl.no_diff": {
        "tr": "Bu sürümde madde farkı izlenemedi.",
        "en": "No clause diff could be derived for this version.",
        "de": "Für diese Version konnte kein Klausel-Diff abgeleitet werden.",
    },
    "bl.no_history": {
        "tr": "Güncel sürüm v{v}, ancak sürüm geçmişi kaydı yok — bu sürümler geçmiş kaydı tutulmaya başlanmadan önce oluşturulmuş olabilir. Yeni CR onayları buraya işlenecek.",
        "en": "Current version is v{v} but no version history is recorded — these versions may predate history tracking. New CR approvals will appear here.",
        "de": "Aktuelle Version ist v{v}, aber kein Versionsverlauf vorhanden — diese Versionen entstanden evtl. vor der Verlaufserfassung. Neue CR-Genehmigungen erscheinen hier.",
    },
    "bl.initial": {
        "tr": "Sözleşme baseline'ı — {n} madde ile başlangıç.",
        "en": "Contract baseline — started with {n} clauses.",
        "de": "Vertrags-Baseline — Start mit {n} Klauseln.",
    },
    "pool.breakdown": {"tr": "döküm →", "en": "breakdown →", "de": "Aufschlüsselung →"},
    "pool.no_items": {
        "tr": "Bu kategoriye yazılmış iş kaydı bulunamadı (sağlayıcı listeleme desteklemiyor olabilir).",
        "en": "No work items charged to this category (the provider may not support listing).",
        "de": "Keine Arbeitseinträge in dieser Kategorie (Anbieter unterstützt evtl. keine Auflistung).",
    },
    "history.clear_decision_filter": {
        "tr": "Karar filtresini kaldır", "en": "Clear the decision filter",
        "de": "Entscheidungsfilter entfernen",
    },
    # --- Module table screen ---
    "mod.title": {"tr": "Kod Modülleri", "en": "Code Modules", "de": "Codemodule"},
    "mod.subtitle": {
        "tr": "{n} modül — metrikler, eşlenen maddeler ve dokunan kararlar; satıra tıklayın.",
        "en": "{n} modules — metrics, mapped clauses and touching decisions; click a row.",
        "de": "{n} Module — Metriken, zugeordnete Klauseln und Entscheidungen; Zeile anklicken.",
    },
    "mod.col_module": {"tr": "Modül", "en": "Module", "de": "Modul"},
    "mod.col_cyclo": {"tr": "Karmaşıklık", "en": "Complexity", "de": "Komplexität"},
    "mod.col_churn": {"tr": "Churn/6ay", "en": "Churn/6mo", "de": "Churn/6Mon"},
    "mod.col_deps": {"tr": "Bağımlılık", "en": "Deps", "de": "Abhäng."},
    "mod.col_clauses": {"tr": "Eşlenen maddeler", "en": "Mapped clauses", "de": "Klauseln"},
    "mod.col_cases": {"tr": "Karar", "en": "Decisions", "de": "Entsch."},
    "mod.deps_hint": {
        "tr": "bağımlı olduğu / kendisine bağımlı modül sayısı",
        "en": "depends-on / depended-by module counts",
        "de": "abhängig von / abhängige Module",
    },
    "mod.packages": {"tr": "Dış paketler", "en": "External packages", "de": "Externe Pakete"},
    "mod.cases_touching": {
        "tr": "Bu modüle dokunan kararlar ({n})", "en": "Decisions touching this module ({n})",
        "de": "Entscheidungen zu diesem Modul ({n})",
    },
    "mod.no_cases": {
        "tr": "Bu modüle dokunan karar yok.", "en": "No decisions touch this module yet.",
        "de": "Noch keine Entscheidungen zu diesem Modul.",
    },
    "mod.stale": {"tr": "indekste yok", "en": "not in index", "de": "nicht im Index"},
    "mod.empty": {
        "tr": "Modül yok — proje henüz indekslenmemiş olabilir.",
        "en": "No modules — the project may not be indexed yet.",
        "de": "Keine Module — das Projekt ist evtl. noch nicht indexiert.",
    },
    # --- Clause detail screen ---
    "clause.title": {"tr": "Madde Detayı", "en": "Clause Detail", "de": "Klausel-Detail"},
    "clause.back": {"tr": "Özete dön", "en": "Back to summary", "de": "Zurück zur Übersicht"},
    "clause.limit": {"tr": "Limit", "en": "Limit", "de": "Limit"},
    "clause.pool": {"tr": "Efor havuzu", "en": "Effort pool", "de": "Aufwandspool"},
    "clause.mapped": {
        "tr": "Eşlenen kod modülleri", "en": "Mapped code modules", "de": "Zugeordnete Codemodule",
    },
    "clause.added_by_cr": {
        "tr": "Onaylı CR ile eklendi", "en": "Added by an approved CR",
        "de": "Durch genehmigten CR hinzugefügt",
    },
    "clause.cited_cases": {
        "tr": "Bu maddeye atıf yapan kararlar", "en": "Decisions citing this clause",
        "de": "Entscheidungen mit Bezug auf diese Klausel",
    },
    "clause.no_cases": {
        "tr": "Bu maddeye atıf yapan karar yok.", "en": "No decisions cite this clause yet.",
        "de": "Noch keine Entscheidungen zu dieser Klausel.",
    },
    "cards.request_label": {"tr": "Talep", "en": "Request", "de": "Anfrage"},
    "cards.sub_requests": {
        "tr": "{n} alt-ister", "en": "{n} sub-requests", "de": "{n} Teilanforderungen",
    },
    "cards.open_case": {
        "tr": "vaka dosyasını aç & onayla →", "en": "open & approve case file →",
        "de": "Fallakte öffnen & freigeben →",
    },
    "cards.index": {"tr": "indeks", "en": "index", "de": "Index"},
    # --- triage_result ---
    "tr.auto_pre": {
        "tr": "Ön Analiz (otomatik)", "en": "Pre-analysis (automatic)",
        "de": "Voranalyse (automatisch)",
    },
    "tr.auto_pre_sub": {
        "tr": "— geliştirici için, vakaya kaydedildi",
        "en": "— for the developer, saved to the case",
        "de": "— für den Entwickler, im Fall gespeichert",
    },
    "tr.edit_pre": {
        "tr": "Ön Analizi düzenle / zenginleştir", "en": "Edit / enrich the pre-analysis",
        "de": "Voranalyse bearbeiten / anreichern",
    },
    "tr.edit_pre_desc": {
        "tr": "Ön analiz otomatik oluşturuldu ve vakaya kaydedildi. Asistana sorular sorarak "
              "(yapay zekâ asistanı yapılandırılmışsa) zenginleştirebilir, metni düzenleyip "
              "<b>tekrar kaydedebilirsiniz</b>.",
        "en": "The pre-analysis was generated automatically and saved to the case. Ask the "
              "assistant questions (if the AI assistant is configured) to enrich it, edit the "
              "text and <b>save again</b>.",
        "de": "Die Voranalyse wurde automatisch erstellt und im Fall gespeichert. Stellen Sie "
              "dem Assistenten Fragen (falls der KI-Assistent eingerichtet ist), um sie "
              "anzureichern, bearbeiten Sie den Text und <b>speichern Sie erneut</b>.",
    },
    "tr.chat_ph": {
        "tr": "Örn: Neden CR adayı? Eforu en çok ne etkiliyor?",
        "en": "e.g. Why a CR candidate? What drives the effort most?",
        "de": "z. B. Warum CR-Kandidat? Was treibt den Aufwand am meisten?",
    },
    "tr.ask": {"tr": "Sor", "en": "Ask", "de": "Fragen"},
    "tr.answering": {"tr": "yanıtlanıyor…", "en": "answering…", "de": "wird beantwortet…"},
    "tr.draft_label": {
        "tr": "Ön analiz taslağı", "en": "Pre-analysis draft", "de": "Voranalyse-Entwurf",
    },
    "tr.use_last": {
        "tr": "Son yanıtı al", "en": "Use last answer", "de": "Letzte Antwort übernehmen",
    },
    "tr.pre_ph": {
        "tr": "Bu talebe dair ön analiz: kapsam durumu, efor, riskler, öneri…",
        "en": "Pre-analysis for this request: scope, effort, risks, recommendation…",
        "de": "Voranalyse zu dieser Anfrage: Umfang, Aufwand, Risiken, Empfehlung…",
    },
    "tr.save_to_case": {
        "tr": "Vakaya kaydet", "en": "Save to case", "de": "Im Fall speichern",
    },
    # --- case_flow ---
    "cflow.title": {
        "tr": "Bu triyajın akış grafiği", "en": "This triage's flow graph",
        "de": "Flussdiagramm dieser Triage",
    },
    "cflow.desc": {
        "tr": "Bu talebin <b>Talep → İster (kapsam maddesi) → Kod modülü</b> akışı. Düğüme "
              "tıklayın; detayı altta görünür.",
        "en": "This request's <b>Request → Requirement (scope clause) → Code module</b> flow. "
              "Click a node; the detail appears below.",
        "de": "Der Fluss dieser Anfrage <b>Anfrage → Anforderung (Umfangsklausel) → "
              "Codemodul</b>. Klicken Sie auf einen Knoten; das Detail erscheint unten.",
    },
    # --- pre_analysis_saved ---
    "pas.saved": {
        "tr": "✓ Ön analiz vakaya kaydedildi", "en": "✓ Pre-analysis saved to the case",
        "de": "✓ Voranalyse im Fall gespeichert",
    },
    # --- document_preview ---
    "dp.preview_source": {
        "tr": "önizleme · kaynak", "en": "preview · source", "de": "Vorschau · Quelle",
    },
    "dp.first_chars": {
        "tr": "ilk {n} karakter", "en": "first {n} characters", "de": "erste {n} Zeichen",
    },
    "common.close": {"tr": "Kapat", "en": "Close", "de": "Schließen"},
    "dp.truncated": {
        "tr": "… belge kısaltıldı (yalnızca ilk kısım gösteriliyor).",
        "en": "… document truncated (only the first part is shown).",
        "de": "… Dokument gekürzt (nur der erste Teil wird angezeigt).",
    },
    # --- project_sankey (flow page) ---
    "sankey.page_title": {"tr": "Akış Haritası", "en": "Flow Map", "de": "Flusskarte"},
    "sankey.page_subtitle": {
        "tr": "Tüm girdilerin birbirine etkisi: <b>Talep/Analiz → İster (kapsam maddesi) → "
              "Kod modülü</b>. Bir düğümün üzerine gelin veya tıklayın; bağlı akış vurgulanır.",
        "en": "How all inputs affect each other: <b>Request/Analysis → Requirement (scope "
              "clause) → Code module</b>. Hover or click a node; the connected flow is "
              "highlighted.",
        "de": "Wie alle Eingaben sich beeinflussen: <b>Anfrage/Analyse → Anforderung "
              "(Umfangsklausel) → Codemodul</b>. Auf einen Knoten zeigen oder klicken; der "
              "verbundene Fluss wird hervorgehoben.",
    },
    "sankey.showing_last": {
        "tr": "(son {a} / {b} talep gösteriliyor)", "en": "(showing last {a} / {b} requests)",
        "de": "(letzte {a} / {b} Anfragen)",
    },
    "sankey.clause_included": {
        "tr": "İster (dahil)", "en": "Requirement (included)", "de": "Anforderung (enthalten)",
    },
    "sankey.clause_excluded": {
        "tr": "İster (hariç)", "en": "Requirement (excluded)", "de": "Anforderung (ausgeschlossen)",
    },
    "sankey.detail_hint": {
        "tr": "Düğüm detayı — grafikte bir düğüme tıklayın:",
        "en": "Node detail — click a node in the graph:",
        "de": "Knotendetail — klicken Sie auf einen Knoten:",
    },
    "sankey.no_node": {
        "tr": "Henüz düğüm seçilmedi.", "en": "No node selected yet.",
        "de": "Noch kein Knoten ausgewählt.",
    },
    "common.back_to_projects": {
        "tr": "Projelere dön", "en": "Back to projects", "de": "Zurück zu Projekten",
    },
    # --- Search ---
    "ara.title": {"tr": "Arama", "en": "Search", "de": "Suche"},
    "ara.found": {
        "tr": "{p} proje · {c} talep", "en": "{p} projects · {c} requests",
        "de": "{p} Projekte · {c} Anfragen",
    },
    "ara.requests_section": {"tr": "Talepler", "en": "Requests", "de": "Anfragen"},
    "ara.no_project": {"tr": "eşleşen proje yok", "en": "no matching project", "de": "kein passendes Projekt"},
    "ara.no_request": {"tr": "eşleşen talep yok", "en": "no matching request", "de": "keine passende Anfrage"},
    "ara.modules_clauses": {
        "tr": "{m} modül · {c} kapsam", "en": "{m} modules · {c} clauses",
        "de": "{m} Module · {c} Klauseln",
    },
    "ara.hint": {
        "tr": "Üst bardan proje adı, sözleşme no veya talep metni arayın.",
        "en": "Search a project name, contract number or request text from the top bar.",
        "de": "Suchen Sie oben nach Projektname, Vertragsnummer oder Anfragetext.",
    },
    # --- New project ---
    "yp.subtitle": {
        "tr": "Boş bir proje iskeleti oluşturur ve indeksler. Oluşturduktan sonra proje "
              "içindeki <b>Dosyalar &amp; Ayarlar</b> ekranından şartname dokümanı, kod reposu "
              "ve iş-takip bağlantısı eklersiniz.",
        "en": "Creates and indexes an empty project skeleton. After creating it, add the spec "
              "document, code repository and work-item link from the project's <b>Files &amp; "
              "Settings</b> screen.",
        "de": "Erstellt und indexiert ein leeres Projektgerüst. Fügen Sie danach im Bildschirm "
              "<b>Dateien &amp; Einstellungen</b> des Projekts das Spezifikationsdokument, das "
              "Code-Repository und die Aufgabenverknüpfung hinzu.",
    },
    "yp.id_label": {
        "tr": "Proje kimliği (kısa, boşluksuz)", "en": "Project ID (short, no spaces)",
        "de": "Projekt-ID (kurz, ohne Leerzeichen)",
    },
    "yp.id_ph": {"tr": "ör. yeni-musteri", "en": "e.g. new-client", "de": "z. B. neuer-kunde"},
    "yp.name_label": {"tr": "Proje adı", "en": "Project name", "de": "Projektname"},
    "yp.name_ph": {
        "tr": "ör. Yeni Müşteri Portalı", "en": "e.g. New Client Portal", "de": "z. B. Neues Kundenportal",
    },
    "yp.contract_label": {"tr": "Sözleşme no", "en": "Contract no.", "de": "Vertragsnr."},
    "yp.create": {
        "tr": "Oluştur ve indeksle", "en": "Create and index", "de": "Erstellen und indexieren",
    },
    # --- Analysis results (document) ---
    "an.scope_extracted": {
        "tr": "{n} kapsam maddesi çıkarıldı", "en": "{n} scope clauses extracted",
        "de": "{n} Umfangsklauseln extrahiert",
    },
    "an.no_clauses": {
        "tr": "Madde çıkarılamadı — metin \"Madde X — …\" yapısında başlıklar içermiyor olabilir.",
        "en": "No clauses extracted — the text may not contain \"Clause X — …\" style headings.",
        "de": "Keine Klauseln extrahiert — der Text enthält evtl. keine \"Klausel X — …\"-Überschriften.",
    },
    "an.triaged": {
        "tr": "{n} talep triyaj edildi", "en": "{n} requests triaged",
        "de": "{n} Anfragen triagiert",
    },
    "an.showing_first": {
        "tr": "ilk {n} gösteriliyor", "en": "showing first {n}", "de": "erste {n} angezeigt",
    },
    "an.no_lines": {
        "tr": "Dosyada triyaj edilecek anlamlı satır bulunamadı.",
        "en": "No meaningful lines to triage were found in the file.",
        "de": "Keine sinnvollen Zeilen zum Triagieren in der Datei gefunden.",
    },
    # --- Files & Settings screen ---
    "pf.subtitle": {
        "tr": "Şartname/spec dokümanları, kod repoları ve iş-takip bağlantısı. Her "
              "değişiklikten sonra proje yeniden indekslenir.",
        "en": "Specification documents, code repositories and work-item link. The project is "
              "re-indexed after each change.",
        "de": "Spezifikationsdokumente, Code-Repositories und Aufgabenverknüpfung. Das Projekt "
              "wird nach jeder Änderung neu indexiert.",
    },
    "pf.doc_desc": {
        "tr": "Word/Excel/PDF/CSV/TXT yükleyin → metne çevrilip kapsam maddeleri çıkarılır.",
        "en": "Upload Word/Excel/PDF/CSV/TXT → converted to text and scope clauses extracted.",
        "de": "Word/Excel/PDF/CSV/TXT hochladen → in Text umgewandelt und Klauseln extrahiert.",
    },
    "pf.upload_index": {
        "tr": "Yükle & İndeksle", "en": "Upload & index", "de": "Hochladen & indexieren",
    },
    "pf.source_badge": {"tr": "kaynak", "en": "source", "de": "Quelle"},
    "pf.preview": {"tr": "Önizle", "en": "Preview", "de": "Vorschau"},
    "pf.confirm_doc": {"tr": "Doküman silinsin mi?", "en": "Delete document?", "de": "Dokument löschen?"},
    "pf.no_docs": {
        "tr": "Doküman yok. Yukarıdan yükleyin veya kaynak bağlayın.",
        "en": "No document. Upload above or link a source.",
        "de": "Kein Dokument. Oben hochladen oder eine Quelle verknüpfen.",
    },
    "pf.preview_loading": {
        "tr": "önizleme yükleniyor…", "en": "loading preview…", "de": "Vorschau wird geladen…",
    },
    "pf.repos": {"tr": "Kod Repoları", "en": "Code Repositories", "de": "Code-Repositories"},
    "pf.repos_desc": {
        "tr": "Git URL (klonlanır) <b>veya</b> yerel yol. Çoklu repo desteklenir; yayılım "
              "analizi hepsini kapsar.",
        "en": "Git URL (cloned) <b>or</b> a local path. Multiple repos supported; impact "
              "analysis covers all.",
        "de": "Git-URL (wird geklont) <b>oder</b> lokaler Pfad. Mehrere Repos möglich; die "
              "Wirkungsanalyse umfasst alle.",
    },
    "pf.repo_name_ph": {
        "tr": "repo adı (ör. main)", "en": "repo name (e.g. main)", "de": "Repo-Name (z. B. main)",
    },
    "pf.engine_ast": {
        "tr": "Hızlı analiz — yalnız Python, kurulum gerektirmez (ast)",
        "en": "Quick analysis — Python only, no setup (ast)",
        "de": "Schnellanalyse — nur Python, keine Installation (ast)",
    },
    "pf.engine_joern": {
        "tr": "Derin analiz — tam kod grafiği, sunucuda kurulum ister (joern)",
        "en": "Deep analysis — full code graph, needs server setup (joern)",
        "de": "Tiefenanalyse — vollständiger Code-Graph, erfordert Server-Setup (joern)",
    },
    "pf.engine_graphify": {
        "tr": "Çok dilli analiz — kurulum gerektirmez (graphify)",
        "en": "Multi-language analysis — no setup (graphify)",
        "de": "Mehrsprachige Analyse — keine Installation (graphify)",
    },
    "pf.src_root_ph": {
        "tr": "veya yerel yol (ör. samples/…/src)", "en": "or local path (e.g. samples/…/src)",
        "de": "oder lokaler Pfad (z. B. samples/…/src)",
    },
    "pf.add_repo": {
        "tr": "Repo ekle & İndeksle", "en": "Add repo & index", "de": "Repo hinzufügen & indexieren",
    },
    "pf.confirm_repo": {
        "tr": "Repo kaldırılsın mı?", "en": "Remove repository?", "de": "Repository entfernen?",
    },
    "pf.work_items": {"tr": "İş-Takip (work-items)", "en": "Work items", "de": "Aufgaben (Work Items)"},
    "pf.work_items_desc": {
        "tr": "Efor tahmininde kullanılan ticket kaynağı. Seçenekleri <span class=\"mono\">"
              "anahtar: değer</span> satırlarıyla girin (sırlar için <span class=\"mono\">"
              "env:DEGISKEN</span>).",
        "en": "Ticket source used in effort estimation. Enter options as <span class=\"mono\">"
              "key: value</span> lines (for secrets use <span class=\"mono\">env:VARIABLE</span>).",
        "de": "Ticket-Quelle für die Aufwandsschätzung. Optionen als <span class=\"mono\">"
              "Schlüssel: Wert</span>-Zeilen eingeben (für Geheimnisse <span class=\"mono\">"
              "env:VARIABLE</span>).",
    },
    "pf.adapter": {"tr": "Adaptör", "en": "Adapter", "de": "Adapter"},
    "pf.invalid_options": {
        "tr": "Seçenekler doğrulanamadı: {msgs}",
        "en": "Options failed validation: {msgs}",
        "de": "Optionen konnten nicht validiert werden: {msgs}",
    },
    "pf.opts_secret_hint": {
        "tr": "Sır alanlarına env:DEGISKEN referansı yazın — değerler düz metin saklanmaz.",
        "en": "Use env:VARIABLE references for secret fields — values are never stored in plain text.",
        "de": "Für Geheimnisfelder env:VARIABLE-Referenzen verwenden — Werte werden nie im Klartext gespeichert.",
    },
    "pf.opts_raw_link": {
        "tr": "serbest metin modu", "en": "free-text mode", "de": "Freitextmodus",
    },
    "pf.unknown_adapter": {
        "tr": "Bilinmeyen iş-takip adaptörü: {name}. Mevcut: {known}. Henüz kurulmamış bir "
              "eklenti adaptörü yalnızca projects.yaml üzerinden yazılabilir.",
        "en": "Unknown work-item adapter: {name}. Available: {known}. A not-yet-installed "
              "plugin adapter can only be set via projects.yaml.",
        "de": "Unbekannter Work-Item-Adapter: {name}. Verfügbar: {known}. Ein noch nicht "
              "installierter Plugin-Adapter kann nur über projects.yaml gesetzt werden.",
    },
    "pf.options_ph": {
        "tr": "ör. file → path: samples/…/work_items.json&#10;ör. jira → base_url: https://…"
              "&#10;     project_key: ABC&#10;     api_token: env:JIRA_TOKEN",
        "en": "e.g. file → path: samples/…/work_items.json&#10;e.g. jira → base_url: https://…"
              "&#10;     project_key: ABC&#10;     api_token: env:JIRA_TOKEN",
        "de": "z. B. file → path: samples/…/work_items.json&#10;z. B. jira → base_url: https://…"
              "&#10;     project_key: ABC&#10;     api_token: env:JIRA_TOKEN",
    },
    "pf.save_index": {
        "tr": "Kaydet & İndeksle", "en": "Save & index", "de": "Speichern & indexieren",
    },
    # --- LLM / Language & Domain Profile card ---
    "pf.llm_profile": {
        "tr": "LLM / Dil & Alan Profili", "en": "LLM / Language & Domain Profile",
        "de": "LLM / Sprache & Domänenprofil",
    },
    "pf.llm_desc": {
        "tr": "Bu projenin LLM çıktısı (ön analiz, sohbet, eşleştirme gerekçesi) bu dile ve "
              "alan profiline göre üretilir. Yalnız LLM yolunu etkiler; deterministik karar değişmez.",
        "en": "This project's LLM output (pre-analysis, chat, match rationale) is produced in "
              "this language and domain profile. Affects only the LLM path; the deterministic "
              "decision is unchanged.",
        "de": "Die LLM-Ausgabe dieses Projekts (Voranalyse, Chat, Match-Begründung) wird in "
              "dieser Sprache und diesem Domänenprofil erzeugt. Betrifft nur den LLM-Pfad; die "
              "deterministische Entscheidung bleibt unverändert.",
    },
    "pf.lang_label": {"tr": "Çıktı dili", "en": "Output language", "de": "Ausgabesprache"},
    "pf.lang_ph": {
        "tr": "ör. tr, en, de, ar…", "en": "e.g. tr, en, de, ar…", "de": "z. B. tr, en, de, ar…",
    },
    "pf.domain_label": {"tr": "Alan profili", "en": "Domain profile", "de": "Domänenprofil"},
    "pf.domain_none": {"tr": "— (yok)", "en": "— (none)", "de": "— (keines)"},
    "pf.instructions_label": {
        "tr": "Ek talimat (serbest)", "en": "Extra instructions (free text)",
        "de": "Zusätzliche Anweisungen (Freitext)",
    },
    "pf.instructions_ph": {
        "tr": "Bu projeye özel ek bağlam/talimat… (alan profiline eklenir)",
        "en": "Project-specific extra context/instructions… (appended to the domain profile)",
        "de": "Projektspezifischer Zusatzkontext/Anweisungen… (ergänzt das Domänenprofil)",
    },
    "pf.pivot_label": {
        "tr": "Pivot dili (opsiyonel)", "en": "Pivot language (optional)",
        "de": "Pivot-Sprache (optional)",
    },
    "pf.pivot_ph": {"tr": "boş = kapalı; ör. en", "en": "empty = off; e.g. en", "de": "leer = aus; z. B. en"},
    "pf.pivot_hint": {
        "tr": "Doluysa girdiler bu dile çevrilip muhakeme edilir, çıktı proje diline geri "
              "çevrilir (her çağrıda +ekstra çeviri; zayıf/yerel LLM kalitesi için).",
        "en": "If set, inputs are translated to this language for reasoning, then the output is "
              "translated back to the project language (extra calls per request; for weak/local LLMs).",
        "de": "Wenn gesetzt, werden Eingaben zur Verarbeitung in diese Sprache übersetzt und die "
              "Ausgabe in die Projektsprache zurückübersetzt (zusätzliche Aufrufe; für schwache/lokale LLMs).",
    },
    # --- Engine free-text strings (deterministic) — generated in the PROJECT's language at
    # triage time and frozen into the evidence chain (audit: never re-translated afterwards).
    "engine.est.similar": {
        "tr": "{n} benzer iş ({hours})", "en": "{n} similar past work items ({hours})",
        "de": "{n} ähnliche frühere Arbeiten ({hours})",
    },
    "engine.est.hours": {"tr": "{h}sa", "en": "{h}h", "de": "{h} Std."},
    "engine.est.code_metric": {
        "tr": "benzer iş yok; kod karmaşıklığına dayalı",
        "en": "no similar work; based on code complexity",
        "de": "keine ähnliche Arbeit; basiert auf Codekomplexität",
    },
    "engine.est.dep_surface": {
        "tr": "bağımlılık yüzeyinden: paketi {mods} modül kullanıyor, {apis} çağrı noktası "
              "denetlenecek (sürüm geçişi modül LOC'una değil kullanım yüzeyine orantılıdır)",
        "en": "from the dependency surface: {mods} module(s) use the package, {apis} call "
              "site(s) to audit (a version change scales with usage surface, not module LOC)",
        "de": "aus der Abhängigkeitsoberfläche: {mods} Modul(e) nutzen das Paket, {apis} "
              "Aufrufstelle(n) zu prüfen (ein Versionswechsel skaliert mit der "
              "Nutzungsoberfläche, nicht mit Modul-LOC)",
    },
    "engine.est.dep_unknown": {
        "tr": "çağrı noktaları kod grafiğinde görünmüyor → üst sınır genişletildi; "
              "gerçek kullanım taranarak doğrulanmalı",
        "en": "call sites are not visible in the code graph → upper bound widened; "
              "verify by scanning actual usage",
        "de": "Aufrufstellen im Code-Graph nicht sichtbar → Obergrenze erweitert; "
              "tatsächliche Nutzung prüfen",
    },
    "engine.est.floor": {
        "tr": "benzer iş/kod metriği yok → kaba alt-sınır varsayımı",
        "en": "no similar work or code metric → rough lower-bound assumption",
        "de": "keine ähnliche Arbeit/Codemetrik → grobe Untergrenzen-Annahme",
    },
    "engine.est.churn_widen": {
        "tr": "yüksek churn → üst sınır genişletildi",
        "en": "high churn → upper bound widened",
        "de": "hoher Churn → Obergrenze erweitert",
    },
    "engine.est.zero_spread": {
        "tr": "tek/özdeş analog → aralık faktörlerle genişletildi",
        "en": "single/identical analog → range widened with the factors",
        "de": "einzelnes/identisches Analogon → Spanne mit Faktoren erweitert",
    },
    "engine.est.narrow_spread": {
        "tr": "dar analog yayılımı → aralık faktörlerle genişletildi",
        "en": "narrow analog spread → range widened with the factors",
        "de": "geringe Analogon-Streuung → Spanne mit Faktoren erweitert",
    },
    "engine.est.pert": {
        "tr": "PERT~{mean}sa (P10–P80)", "en": "PERT~{mean}h (P10–P80)",
        "de": "PERT~{mean} Std. (P10–P80)",
    },
    "engine.rsn.maintenance": {
        "tr": "Bakım kapsamında hata düzeltme ({ref}).",
        "en": "Bug fix within the maintenance scope ({ref}).",
        "de": "Fehlerbehebung im Wartungsumfang ({ref}).",
    },
    "engine.rsn.excluded": {
        "tr": "Sözleşmede açıkça hariç tutulmuş ({ref}).",
        "en": "Explicitly excluded in the contract ({ref}).",
        "de": "Im Vertrag ausdrücklich ausgeschlossen ({ref}).",
    },
    "engine.rsn.limit": {
        "tr": "Limit aşımı: talep {qty} > sözleşme {limit} ({ref}).",
        "en": "Limit exceeded: requested {qty} > contractual {limit} ({ref}).",
        "de": "Limit überschritten: angefragt {qty} > vertraglich {limit} ({ref}).",
    },
    "engine.rsn.pool": {
        "tr": "Efor havuzu aşımı: {consumed}+{high}sa > {pool}sa ({ref}).",
        "en": "Effort pool exceeded: {consumed}+{high}h > {pool}h ({ref}).",
        "de": "Aufwandspool überschritten: {consumed}+{high} Std. > {pool} Std. ({ref}).",
    },
    "engine.rsn.short_query": {
        "tr": "Talep çok kısa/belirsiz (1-2 anlamlı sözcük) → benzerlik kanıtı "
              "tek başına yeterli değil; PMO netleştirmeli.",
        "en": "Request too short/vague (1-2 meaningful words) → similarity evidence "
              "alone is not enough; the PMO should clarify.",
        "de": "Anfrage zu kurz/vage (1-2 aussagekräftige Wörter) → Ähnlichkeitsbeleg "
              "allein reicht nicht; das PMO sollte klären.",
    },
    "engine.rsn.in_scope": {
        "tr": "'{item}' ile yüksek benzerlik; {note}.",
        "en": "High similarity with '{item}'; {note}.",
        "de": "Hohe Ähnlichkeit mit '{item}'; {note}.",
    },
    "engine.rsn.touches_code": {
        "tr": "kapsamlı koda dokunuyor", "en": "touches already-scoped code",
        "de": "berührt bereits im Umfang befindlichen Code",
    },
    "engine.rsn.weak_code": {
        "tr": "kod eşlemesi zayıf", "en": "code mapping is weak",
        "de": "Code-Zuordnung ist schwach",
    },
    "engine.rsn.gray": {
        "tr": "Metin/kod kanıtı kesin değil → PMO kararı.",
        "en": "Text/code evidence inconclusive → PMO decision.",
        "de": "Text-/Code-Beleg nicht eindeutig → PMO-Entscheidung.",
    },
    "engine.exc_veto_note": {
        "tr": "Sözcüksel dışlama isabeti LLM doğrulamasında reddedildi ({ref} bu talebi yasaklamıyor) — dışlama yok sayıldı",
        "en": "The lexical exclusion hit was refuted on LLM verification ({ref} does not forbid this request) — exclusion ignored",
        "de": "Der lexikalische Ausschlusstreffer wurde bei der LLM-Prüfung widerlegt ({ref} verbietet diese Anfrage nicht) — Ausschluss ignoriert",
    },
    "engine.rsn.cr_sem_no_cover": {
        "tr": "Sözcük benzerliği gri bantta ama cross-encoder hiçbir maddenin talebi kapsamadığını gösteriyor → CR sinyali (sözcük artefaktı).",
        "en": "Lexical similarity sits in the gray band but the cross-encoder shows no clause covers the request → CR signal (tokenizer artifact).",
        "de": "Lexikalische Ähnlichkeit liegt im Graubereich, aber der Cross-Encoder zeigt, dass keine Klausel die Anfrage abdeckt → CR-Signal (Tokenizer-Artefakt).",
    },
    "engine.rsn.no_match": {
        "tr": "Hiçbir kapsam maddesiyle anlamlı eşleşme yok → güçlü CR sinyali.",
        "en": "No meaningful match with any scope clause → strong CR signal.",
        "de": "Keine sinnvolle Übereinstimmung mit einer Umfangsklausel → starkes CR-Signal.",
    },
    "engine.asm.spec_no_code": {
        "tr": "Şartnamede var ama kodda henüz yok → efor yalnızca kaba ALT-SINIR; "
              "gerçek kapsam kod/efor verisiyle netleşince büyüyebilir.",
        "en": "In the specification but not yet in the code → effort is only a rough "
              "LOWER BOUND; it may grow once code/effort data clarifies the real scope.",
        "de": "In der Spezifikation, aber noch nicht im Code → Aufwand ist nur eine grobe "
              "UNTERGRENZE; er kann wachsen, sobald Code-/Aufwandsdaten den realen Umfang klären.",
    },
    "engine.asm.no_history": {
        "tr": "Benzer geçmiş iş yok → efor kod metriği/varsayımdan; gerçek loglarla iyileşir.",
        "en": "No similar past work → effort comes from code metrics/assumption; "
              "improves with real logs.",
        "de": "Keine ähnliche frühere Arbeit → Aufwand aus Codemetrik/Annahme; "
              "verbessert sich mit echten Logs.",
    },
    "engine.asm.history_unreachable": {
        "tr": "Efor kaynağına ulaşılamadı → benzer iş sorgulanamadı; efor kod "
              "metriği/varsayımdan. Karar bundan etkilenmez.",
        "en": "Effort source unreachable → similar work could not be queried; effort "
              "comes from code metrics/assumption. The decision is unaffected.",
        "de": "Aufwandsquelle nicht erreichbar → ähnliche Arbeit konnte nicht abgefragt "
              "werden; Aufwand aus Codemetrik/Annahme. Die Entscheidung bleibt unberührt.",
    },
    "engine.asm.period_normalized": {
        "tr": "Talepteki periyot ({req}) madde limitinin periyodundan ({clause}) farklı — "
              "kota kıyası iki taraf yıllığa çevrilerek yapıldı (aylık ×12; adetin yıla "
              "eşit yayıldığı varsayımı). Tek aya yığılma ihtimalini PMO değerlendirmeli.",
        "en": "The request's period ({req}) differs from the clause limit's period "
              "({clause}) — the quota check annualized both sides (monthly ×12; assumes "
              "the amount spreads evenly over the year). The PMO should weigh possible "
              "bursting into a single month.",
        "de": "Der Zeitraum der Anfrage ({req}) weicht vom Zeitraum des Klausel-Limits "
              "({clause}) ab — der Mengenvergleich wurde annualisiert (monatlich ×12; "
              "Annahme gleichmäßiger Verteilung übers Jahr). Mögliche Ballung in einen "
              "Monat sollte das PMO prüfen.",
    },
    "engine.asm.code_no_spec": {
        "tr": "Şartnamede açık madde yok, kod mevcut → bakım/iyileştirme varsayıldı.",
        "en": "No explicit clause in the specification, code exists → assumed "
              "maintenance/improvement.",
        "de": "Keine explizite Klausel in der Spezifikation, Code vorhanden → "
              "Wartung/Verbesserung angenommen.",
    },
    "engine.asm.no_evidence": {
        "tr": "Hiçbir kaynakta kanıt yok → en düşük güven; PMO netleştirmeli.",
        "en": "No evidence in any source → lowest confidence; the PMO should clarify.",
        "de": "Kein Beleg in irgendeiner Quelle → geringstes Vertrauen; das PMO sollte klären.",
    },
    "engine.cov.spec": {
        "tr": "Şartname / ister", "en": "Specification / requirement",
        "de": "Spezifikation / Anforderung",
    },
    "engine.cov.code": {"tr": "Kod grafiği", "en": "Code graph", "de": "Code-Graph"},
    "engine.cov.history": {"tr": "Geçmiş efor", "en": "Past effort", "de": "Bisheriger Aufwand"},
    "engine.cov.best_clause": {
        "tr": "en yakın madde, benzerlik {score}", "en": "closest clause, similarity {score}",
        "de": "nächste Klausel, Ähnlichkeit {score}",
    },
    "engine.cov.no_clause": {
        "tr": "eşleşen madde yok", "en": "no matching clause", "de": "keine passende Klausel",
    },
    "engine.cov.modules": {"tr": "{n} modül", "en": "{n} modules", "de": "{n} Module"},
    "engine.cov.no_modules": {
        "tr": "modül eşleşmedi", "en": "no module matched", "de": "kein Modul zugeordnet",
    },
    "engine.cov.similar": {
        "tr": "{n} benzer iş", "en": "{n} similar work items", "de": "{n} ähnliche Arbeiten",
    },
    "engine.cov.no_similar": {
        "tr": "benzer iş yok", "en": "no similar work", "de": "keine ähnliche Arbeit",
    },
    "engine.cov.history_unreachable": {
        "tr": "kaynağa ulaşılamadı", "en": "source unreachable",
        "de": "Quelle nicht erreichbar",
    },
    "engine.llm_note": {
        "tr": "LLM destekli eşleştirme", "en": "LLM-assisted matching",
        "de": "LLM-gestützte Zuordnung",
    },
    "engine.sem_note": {
        "tr": "Anlamsal (embedding) eşleştirme — kosinüs {cos}, deterministik",
        "en": "Semantic (embedding) match — cosine {cos}, deterministic",
        "de": "Semantische (Embedding-)Zuordnung — Kosinus {cos}, deterministisch",
    },
    "engine.rerank_note": {
        "tr": "Cross-encoder (reranker) eşleşmesi: {ref} — skor {score}, deterministik",
        "en": "Cross-encoder (reranker) match: {ref} — score {score}, deterministic",
        "de": "Cross-Encoder-(Reranker-)Zuordnung: {ref} — Score {score}, deterministisch",
    },
    "engine.sem_hint": {
        "tr": "Anlamsal en yakın madde (bilgi amaçlı, karara etkisiz): {ref} — kosinüs {cos}",
        "en": "Semantically nearest clause (informational, no decision effect): {ref} — cosine {cos}",
        "de": "Semantisch nächste Klausel (informativ, ohne Entscheidungswirkung): {ref} — Kosinus {cos}",
    },
    "engine.precedent_note": {
        "tr": "Madde hafızası (bilgi amaçlı, karara etkisiz): bu maddede {n} geçmiş PMO düzeltmesi var — son: {last}.",
        "en": "Clause memory (informational, no decision effect): this clause has {n} past PMO correction(s) — last: {last}.",
        "de": "Klausel-Gedächtnis (informativ, ohne Entscheidungswirkung): {n} frühere PMO-Korrektur(en) — zuletzt: {last}.",
    },
    "engine.rsn.dep_maintenance": {
        "tr": "Bağımlılık sürüm güncellemesi: '{package}' manifestte bildirilmiş ve {ref} bakım maddesi kütüphane güncellemelerini kapsıyor.",
        "en": "Dependency version update: '{package}' is declared in the manifest and maintenance clause {ref} covers library updates.",
        "de": "Abhängigkeits-Update: '{package}' ist im Manifest deklariert und Wartungsklausel {ref} deckt Bibliotheksaktualisierungen ab.",
    },
    "engine.rsn.dep_new": {
        "tr": "Yeni bağımlılık talebi: paket hiçbir manifestte bildirilmemiş — yeni yetenek/altyapı, CR olarak değerlendirilmelidir.",
        "en": "New dependency request: the package is not declared in any manifest — new capability/infrastructure, should be treated as a CR.",
        "de": "Neue Abhängigkeit: das Paket ist in keinem Manifest deklariert — neue Fähigkeit/Infrastruktur, als CR zu behandeln.",
    },
    "engine.rsn.dep_gray": {
        "tr": "Çelişen kanıt: talep bir 'yükseltme'den söz ediyor ama paket hiçbir manifestte bildirilmemiş — PMO incelemesi gerekli.",
        "en": "Conflicting evidence: the request speaks of an 'upgrade' but the package is not declared in any manifest — PMO review required.",
        "de": "Widersprüchliche Evidenz: die Anfrage spricht von einem 'Upgrade', aber das Paket ist in keinem Manifest deklariert — PMO-Prüfung nötig.",
    },
    "engine.dependency_note": {
        "tr": "Bağımlılık talebi (bilgi amaçlı, karara etkisiz): paket '{package}' — {status}; hedef sürüm: {version}.",
        "en": "Dependency request (informational, no decision effect): package '{package}' — {status}; target version: {version}.",
        "de": "Abhängigkeitsanfrage (informativ, ohne Entscheidungswirkung): Paket '{package}' — {status}; Zielversion: {version}.",
    },
    "engine.dep_declared": {
        "tr": "{manifest} içinde bildirilmiş ({spec})",
        "en": "declared in {manifest} ({spec})",
        "de": "in {manifest} deklariert ({spec})",
    },
    "engine.dep_security_note": {
        "tr": "GÜVENLİK GEREKÇESİ: kapsam kararı sözleşmeye göredir (kapsam dışıysa CR olarak fiyatlanır) ANCAK güvenlik yamasını ertelemek kapsamdan bağımsız risk doğurur — 24 saat içinde PMO değerlendirmesi önerilir.",
        "en": "SECURITY RATIONALE: the scope decision follows the contract (out-of-scope → priced as a CR) BUT deferring a security fix creates risk regardless of scope — PMO review within 24 hours is recommended.",
        "de": "SICHERHEITSBEGRÜNDUNG: die Scope-Entscheidung folgt dem Vertrag (außerhalb → CR), ABER das Aufschieben eines Sicherheits-Fixes schafft Risiko unabhängig vom Scope — PMO-Prüfung binnen 24 Stunden empfohlen.",
    },
    "engine.risk.sig_security": {
        "tr": "güvenlik gerekçeli bağımlılık talebi (erteleme riski)",
        "en": "security-motivated dependency request (deferral risk)",
        "de": "sicherheitsmotivierte Abhängigkeitsanfrage (Aufschubrisiko)",
    },
    "engine.risk.sig_disputed": {
        "tr": "atıflı maddede çelişen nihai kararlar (ihtilaf) — karar öncesi geçmiş okunmalı",
        "en": "conflicting final rulings on the cited clause (dispute) — read the history before ruling",
        "de": "widersprüchliche finale Entscheidungen zur zitierten Klausel (Streitfall) — vor der Entscheidung Verlauf lesen",
    },
    "engine.dep_api_note": {
        "tr": "Kullanılan API yüzeyi (bilgi amaçlı): kod bu paketin {n} sembolünü çağırıyor — sürüm değişikliğinde denetlenmeli: {apis}.",
        "en": "Used API surface (informational): the code calls {n} symbol(s) of this package — audit on a version change: {apis}.",
        "de": "Genutzte API-Oberfläche (informativ): der Code ruft {n} Symbol(e) dieses Pakets auf — bei Versionswechsel prüfen: {apis}.",
    },
    "engine.dep_undeclared": {
        "tr": "manifestlerde bildirilmemiş (yeni bağımlılık)",
        "en": "not declared in any manifest (new dependency)",
        "de": "in keinem Manifest deklariert (neue Abhängigkeit)",
    },
    "engine.disputed_note": {
        "tr": "Madde hafızası (bilgi amaçlı, karara etkisiz): bu madde geçmişte ÇELİŞEN nihai kararlar aldı — onaydan önce ihtilaf geçmişini inceleyin.",
        "en": "Clause memory (informational, no decision effect): this clause has CONFLICTING past final rulings — review the dispute history before approving.",
        "de": "Klausel-Gedächtnis (informativ, ohne Entscheidungswirkung): WIDERSPRÜCHLICHE frühere finale Entscheidungen — vor der Freigabe die Historie prüfen.",
    },
    "engine.cr.impact": {
        "tr": "Etkilenen modüller: {modules}. Risk: {risk}.",
        "en": "Impacted modules: {modules}. Risk: {risk}.",
        "de": "Betroffene Module: {modules}. Risiko: {risk}.",
    },
    "engine.cr.no_modules": {
        "tr": "tespit edilemedi", "en": "could not be determined", "de": "nicht ermittelbar",
    },
    "engine.cr.effort": {
        "tr": "~{low}-{high} saat efor", "en": "~{low}-{high} hours of effort",
        "de": "~{low}-{high} Stunden Aufwand",
    },
    "engine.risk.sig_churn": {
        "tr": "yüksek churn ({n} commit/6ay)", "en": "high churn ({n} commits/6mo)",
        "de": "hoher Churn ({n} Commits/6 Mon.)",
    },
    "engine.risk.sig_cx": {
        "tr": "yüksek kod karmaşıklığı (cyclomatic {n})",
        "en": "high code complexity (cyclomatic {n})",
        "de": "hohe Codekomplexität (zyklomatisch {n})",
    },
    "engine.risk.sig_spread": {
        "tr": "geniş yayılım (çok modül)", "en": "wide spread (many modules)",
        "de": "breite Streuung (viele Module)",
    },
    "engine.risk.sig_pool": {
        "tr": "efor havuzu %85+ dolu", "en": "effort pool 85%+ consumed",
        "de": "Aufwandspool zu 85%+ verbraucht",
    },
    "engine.risk.basis_churn": {
        "tr": "değişim geçmişi (en yük. {churn} commit/6ay) + karmaşıklık (cx {cx})",
        "en": "change history (max {churn} commits/6mo) + complexity (cx {cx})",
        "de": "Änderungshistorie (max. {churn} Commits/6 Mon.) + Komplexität (cx {cx})",
    },
    "engine.risk.basis_cx": {
        "tr": "commit/ticket geçmişi yok → kod karmaşıklığı (cyclomatic {cx}, {n} modül)",
        "en": "no commit/ticket history → code complexity (cyclomatic {cx}, {n} modules)",
        "de": "keine Commit-/Ticket-Historie → Codekomplexität (zyklomatisch {cx}, {n} Module)",
    },
    # Risk likelihood/impact words are stored in the engine as TR keys (matrix key,
    # frozen data) — translated to the UI language at display time (macros.html).
    "risk.word.düşük": {"tr": "düşük", "en": "low", "de": "niedrig"},
    "risk.word.orta": {"tr": "orta", "en": "medium", "de": "mittel"},
    "risk.word.yüksek": {"tr": "yüksek", "en": "high", "de": "hoch"},
    "cf.how_to_read_desc": {
        "tr": "Sistem <b>öneri</b> verir; nihai karar PMO'dadır (\"copilot, autopilot değil\"). "
              "Her kararın altındaki <b>Kanıt zinciri</b>, hangi sözleşme maddelerine karşı "
              "kontrol edildiğini, en iyi eşleşmeyi, etkilenen kod modüllerini, efor dayanağını "
              "ve riski gösterir — müşteri/ihtilaf pazarlığında dayanak olur. <b>CR'a çevir</b> "
              "onaylanan talebi baseline'a ekler (sürüm +1, \"yaşayan baseline\"). Tüm aksiyonlar "
              "denetim izine yazılır.",
        "en": "The system <b>suggests</b>; the final decision rests with the PMO (\"copilot, "
              "not autopilot\"). Under each decision, the <b>evidence chain</b> shows which "
              "contract clauses were checked, the best match, impacted code modules, the effort "
              "basis and risk — your leverage in client/dispute negotiations. <b>Convert to CR</b> "
              "adds the approved request to the baseline (version +1, \"living baseline\"). All "
              "actions are written to the audit trail.",
        "de": "Das System <b>schlägt vor</b>; die endgültige Entscheidung trifft das PMO "
              "(\"Copilot, kein Autopilot\"). Unter jeder Entscheidung zeigt die <b>Beweiskette</b>, "
              "welche Vertragsklauseln geprüft wurden, die beste Übereinstimmung, betroffene "
              "Codemodule, die Aufwandsgrundlage und das Risiko — Ihr Vorteil in Kunden-/"
              "Streitverhandlungen. <b>In CR umwandeln</b> fügt die genehmigte Anfrage der Baseline "
              "hinzu (Version +1, \"lebende Baseline\"). Alle Aktionen werden im Audit-Trail "
              "protokolliert.",
    },
}
