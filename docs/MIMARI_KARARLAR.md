# MoneyFast — Mimari Durum ve Açık Kararlar (güncel)

Bu doküman, alınan kararların ve hâlâ açık olanların tek kaynağı. Karar kapandıkça
işaretleyip ilgili yere (CLAUDE.md, CONTRACT_WORKFLOW.md) yansıtılmalı.

## Verilen kararlar

| Karar | Sonuç | Not |
|---|---|---|
| Backend dili | Python | .NET denendi, ekip Python'a çok daha aşina olduğu için geri dönüldü |
| Backend framework | FastAPI | Async, otomatik OpenAPI üretimi contract workflow'un temeli |
| Mimari stil | Modüler monolit + ayrı ai-service | Mikroservis (7 servis) koordinasyon yükü 4 hafta için fazla bulundu |
| Veritabanı | PostgreSQL | .NET denemesindeki MySQL kararından değişti |
| Auth | FastAPI + JWT (python-jose/passlib) | ASP.NET Identity önerisi .NET dönemine aitti, Python'a taşındı |
| Frontend | React + Vite + TS + Tailwind | Değişmedi |
| Servisler arası sözleşme | OpenAPI-tabanlı otomatik üretim | Detay: CONTRACT_WORKFLOW.md |

## Açık kararlar

### 1. LLM / AI sağlayıcı
ai-service'in tüm iç mimarisini belirliyor. Kim: Şevval, Burak.
- [ ] Karar verildi: ______________________

### 2. Piyasa/haber veri kaynağı
Scraping mi, ücretsiz bir finans API'si mi. Kim: Şevval, Burak.
- [ ] Karar verildi: ______________________

### 3. Admin paneli
PG-05'te "sistem admini hesapları yönetebilmeli" var, hiçbir modülde karşılığı yok.
auth modülüne rol bazlı mı eklenecek, ayrı bir yüzey mi olacak? Kim: Sen + Arda + Bahar.
- [ ] Karar verildi: ______________________

### 4. Bildirim mekanizması
Ayrı mesaj kuyruğu (RabbitMQ vb.) mu, yoksa zaten kurulu olan Redis'in Pub/Sub'ı mı,
yoksa senkron REST çağrısı mı. Kim: Sen + Arda.
- [ ] Karar verildi: ______________________

### 5. İş kuralları (İK-01 → İK-10) — gerçek mi simüle mi
EFT saat kısıtı, FAST 7/24, BIST/ABD seans saatleri + yaz/kış saati dönüşümü gibi
kurallar gerçek bir zamanlayıcı ile mi uygulanacak, yoksa demo kapsamında validasyon
mesajı gösterip anında mı işlenecek? Kim: Bahar (BA) karar verir, siz uygularsınız.
- [ ] Karar verildi: ______________________

### 6. OTP teslimatı
Kayıt/giriş "tek kullanımlık kod" için gerçek SMS/email mi, demo simülasyonu mu.
Kim: Bahar (BA) + Auth modülünü kuracak kişi.
- [ ] Karar verildi: ______________________

## Kritik ürün notu

Chatbot kullanıcı adına piyasa işlemi (alım/satım) gerçekleştirebilecek (FG-CB-02).
FOG-03 "hassas işlemler için ek kimlik doğrulama" gerektiriyor — ai-service'in bir
işlemi *önermesi* ile backend'in investment modülünün o işlemi *gerçekleştirmesi*
arasında frontend'de açık bir onay adımı olmalı. Bu, ai-service ↔ backend contract'ına
dahil edilmeli.

## Eksik olabilecek altyapı parçaları

- ✅ Paylaşılan sözleşme: OpenAPI-tabanlı otomatik üretimle çözüldü (CONTRACT_WORKFLOW.md)
- ✅ Local orchestration: infra/docker-compose.yml ile çözüldü
- [ ] Router auto-discovery mekanizması backend/app/main.py'de kurulmalı (bkz. CLAUDE.md)
- [ ] Pre-commit hook (ruff/black/eslint/prettier) henüz kurulmadı
