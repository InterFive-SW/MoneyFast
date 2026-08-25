# MoneyFast — Mimari Durum ve Açık Kararlar (güncel)

Bu doküman, alınan kararların ve hâlâ açık olanların tek kaynağı. Karar kapandıkça
işaretleyip ilgili yere (CLAUDE.md, CONTRACT_WORKFLOW.md) yansıtılmalı.

## Verilen kararlar

| Karar | Sonuç | Not |
|---|---|---|
| Backend dili | Python | .NET denendi, ekip Python'a çok daha aşina olduğu için geri dönüldü |
| Backend framework | FastAPI | Async, otomatik OpenAPI üretimi contract workflow'un temeli |
| Mimari stil | Modüler monolit (backend+frontend birlikte) + ayrı ai-service | Mikroservis (7 servis) koordinasyon yükü fazla bulundu; PO değerlendirmesi sonrası frontend de backend'e birleşti (2 Dockerfile) — gerekçe aşağıda |
| Veritabanı | PostgreSQL | .NET denemesindeki MySQL kararından değişti |
| Auth | FastAPI + JWT (python-jose/passlib) | ASP.NET Identity önerisi .NET dönemine aitti, Python'a taşındı |
| Frontend | React + Vite + TS + Tailwind — backend'e entegre (StaticFiles + SPA fallback) | Ayrı servis değil; multi-stage Dockerfile ile aynı image'da build edilip serve ediliyor |
| Servisler arası sözleşme | OpenAPI-tabanlı otomatik üretim | Detay: CONTRACT_WORKFLOW.md — artık sadece backend↔ai-service sınırı için geçerli |
| Veritabanı izolasyonu | Ayrı `base-db` ve `vector-db` PostgreSQL 16 instance'ları | Vector sorguları ana işlem yükünden, volume'den ve resource limitlerinden izole; detay: VECTOR_DB_ARCHITECTURE.md |
| LLM sağlayıcı | **Groq** (`llama-3.3-70b-versatile` + `llama-3.1-8b-instant`) | Ücretsiz katman, düşük gecikme. `agents` sistemdeki tek dış çıkışı olan servis |
| Embedding | **`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, 384 boyut**, `rag` içinde fastembed/ONNX ile yerel | Groq embedding modeli sunmuyor; barındırılan her alternatif ya ücretli ya da kotalı. Yerel çalıştırmak API anahtarını ve retrieval yolundaki ağ bağımlılığını tamamen kaldırdı. Model/boyut değişikliği şema değişikliği, re-embedding ve retrieval evaluation gerektirir |
| Niyet yönlendirme | LLM `agents` içinde (Groq), güvenlik ön-filtresi `mcp` içinde deterministik | Bir güvenlik kapısı, koruduğu modele bağımlı olursa sağlayıcı bozulduğunda sessizce açılır. Regex denetlenebilir ve bedava |
| Canlı veri toplama | Ayrı `ingestor` container'ı; yfinance + Türkçe RSS | İnternete çıkan tek toplayıcı hiçbir DB kredensiyeli taşımıyor, her şeyi HTTP ile itiyor. Bot korumasını aşan scraping YAPILMIYOR — bkz. moneyfast-ingestor/README |
| Vector şema kurulumu | Postgres'in kendi `/docker-entrypoint-initdb.d/` mekanizması | Ayrı migration container'ı ve checksum defteri kaldırıldı; korpus dummy ve yeniden üretilebilir olduğu için defter bir şey korumuyordu. Bedeli: initdb yalnızca boş volume'de çalışır (VECTOR_DB_ARCHITECTURE.md'de açıkça yazılı) |
| Container sayısı | 7: `base-db`, `vector-db`, `backend`, `rag`, `mcp`, `agents`, `ingestor` | `rag` ayrı servis: vektör DB kredensiyelini tutan tek bileşen ve ONNX bağımlılıkları bankacılık API'sinin image'ına girmemeli |

### Neden frontend backend'e birleşti, ai-service neden ayrı kaldı

PO'nun "3 Dockerfile yerine neden tek değil" sorusu üzerine değerlendirildi. Sonuç:
frontend ile backend arasında gerçek bir izolasyon ihtiyacı yoktu (frontend statik
dosya, CPU/bellek yükü yaratmıyor; frontend çökerse zaten kullanıcı hiçbir şeye
erişemez, "arkadaki servisler ayakta kalsın" argümanı bu durumda değersiz).
Birleştirme CORS'u ve bir deploy adımını ortadan kaldırdı — gerçek bir kazanç.
ai-service'i ayrı tutmanın gerekçesi farklı ve hâlâ geçerli: RAG/embedding
kütüphaneleri farklı bağımlılık profiline sahip, performans izolasyonu gerekiyor
(chatbot yavaşlarsa/çökerse bankacılık işlemleri etkilenmemeli — FOG-04/FOG-05).
Sonuç: 3 servisten 2'ye inildi (backend+frontend birlikte, ai-service ayrı),
tam tek container'a gidilmedi çünkü bu, ai-service izolasyonunun gerçek gerekçesini
geri alırdı.

## Açık kararlar

### 1. LLM / AI sağlayıcı — KAPANDI
Groq seçildi (`langchain-groq`, `orchestrator.py:get_llm`). Embedding tarafı
Groq'ta bulunmadığı için yerel `fastembed` ile çözüldü; ikisi birbirinden
bağımsız kararlar. Detay: VECTOR_DB_ARCHITECTURE.md → Embedding contract.
- [x] Karar verildi: **Groq (LLM) + yerel paraphrase-multilingual-MiniLM-L12-v2 (embedding)**

Not: ilk tercih `intfloat/multilingual-e5-small` idi; fastembed bu modeli
desteklemiyor (build sırasında tespit edildi). fastembed'in tek 384 boyutlu
çok dilli modeli MiniLM; boyut ve çalışma zamanı aynı kaldığı için şema
değişmedi.

### 2. Piyasa/haber veri kaynağı
Scraping mi, ücretsiz bir finans API'si mi. Kim: Şevval, Burak.
- [ ] Karar verildi: ______________________

### 3. Admin paneli
PG-05'te "sistem admini hesapları yönetebilmeli" var, hiçbir modülde karşılığı yok.
auth modülüne rol bazlı mı eklenecek, ayrı bir yüzey mi olacak? Kim: Mustafa, Arda, Bahar.
- [ ] Karar verildi: ______________________

### 4. Bildirim mekanizması
Ayrı mesaj kuyruğu (RabbitMQ vb.) mu, yoksa zaten kurulu olan Redis'in Pub/Sub'ı mı,
yoksa senkron REST çağrısı mı. Kim: Mustafa, Arda.
- [ ] Karar verildi: ______________________

### 5. İş kuralları (İK-01 → İK-10) — gerçek mi simüle mi
EFT saat kısıtı, FAST 7/24, BIST/ABD seans saatleri + yaz/kış saati dönüşümü gibi
kurallar gerçek bir zamanlayıcı ile mi uygulanacak, yoksa demo kapsamında validasyon
mesajı gösterip anında mı işlenecek? Kim: Bahar (BA) karar verir, backend ekibi uygular.
- [ ] Karar verildi: ______________________

### 6. OTP teslimatı
Kayıt/giriş "tek kullanımlık kod" için gerçek SMS/email mi, demo simülasyonu mu.
Kim: Bahar (BA) + Auth modülünü kuracak kişi.
- [ ] Karar verildi: ______________________

## shared/ kuralı — DB modeli asla buraya girmez

`shared/` sadece domain'siz ortak kod içindir (enum, exception, pagination
yardımcıları). DB modelleri (SQLAlchemy sınıfları) sahiplendikleri modülde yaşar —
örn. `User` sadece `app/modules/auth/models.py`'de. Başka bir modülün kullanıcıya
ihtiyacı varsa `User` sınıfını import etmez, sadece `user_id: UUID` foreign key
kolonu tutar. Detay ve gerekçe: CLAUDE.md.

## Kritik ürün notu

Chatbot kullanıcı adına piyasa işlemi (alım/satım) gerçekleştirebilecek (FG-CB-02).
FOG-03 "hassas işlemler için ek kimlik doğrulama" gerektiriyor — ai-service'in bir
işlemi *önermesi* ile backend'in investment modülünün o işlemi *gerçekleştirmesi*
arasında frontend'de açık bir onay adımı olmalı. Bu, ai-service ↔ backend contract'ına
dahil edilmeli.

## Eksik olabilecek altyapı parçaları

- ✅ Paylaşılan sözleşme: OpenAPI-tabanlı otomatik üretimle çözüldü (CONTRACT_WORKFLOW.md)
- ✅ Local orchestration: infra/docker-compose.yml ile çözüldü (postgres + backend, healthcheck'li)
- ✅ Core/vector PostgreSQL performans izolasyonu ve ayrı migration sahipliği tanımlandı
- ✅ Router auto-discovery: backend/app/main.py'de kuruldu, doğrulandı
- ✅ Backend altyapısı: auth modülü uçtan uca test edildi (register → Postgres kaydı)
- ✅ Frontend altyapısı: backend'e entegre, SPA routing doğrulandı
- [ ] ai-service iskeleti henüz kurulmadı (Şevval, Burak)
- [ ] Pre-commit hook (ruff/black/eslint/prettier) henüz kurulmadı
- [ ] Test suite (pytest) henüz kurulmadı
