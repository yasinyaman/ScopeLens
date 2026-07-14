# Entegrasyon Projeleri

Bu proje bir **sistem entegrasyonu** işidir. Talepleri değerlendirirken şunlara dikkat et:
- Entegrasyon noktaları: API'ler, mesaj kuyrukları, dosya transferleri, webhook'lar, kimlik
  sağlayıcılar (SSO/SAML/OAuth).
- Veri eşleme/dönüşüm (mapping/transform), idempotency, yeniden deneme ve hata kuyruğu.
- Üçüncü taraf bağımlılıkları ve sözleşme dışı entegrasyon talepleri çoğunlukla **CR**'dır.
- Efor sürücüleri: dış sistem sayısı, protokol çeşitliliği, kimlik/güvenlik gereksinimleri.
Önerilerinde bağlantı noktalarını, veri akışını ve dış bağımlılık risklerini vurgula.
