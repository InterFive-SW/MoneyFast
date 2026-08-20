# MoneyFast — Proje Context

Bu dosya Claude Code tarafından her session başında otomatik okunur. Antigravity ve
diğer agent araçlarını kullanan ekip arkadaşları bu dosyayı kendi tool'larına manuel
eklemeli — tek doğru kaynak burası, araç fark etmemeli.

## Proje özeti

InternTech 2026 kapsamında InterFive takımı tarafından geliştirilen MoneyFast — çoklu
ajan mimarisiyle çalışan bir kişisel finans danışmanı. Chatbot odakta; bankacılık
işlemleri, yatırım/portföy yönetimi, RAG tabanlı piyasa/haber okuma ve risk
değerlendirmesi sunuyor. Süre: 4 hafta. Gerçek müşteri verisi kullanılmıyor — tüm veri
dummy/sentetik (TC kimlik no dahil, gerçekçi ama açıkça sahte formatta).

## Mimari: 7 container

Başlangıçta 3 ayrı servis (backend, frontend, ai-service) planlanmıştı;
PO ile yapılan değerlendirme sonrası **frontend backend'e birleştirildi** —
aralarında gerçek bir izolasyon ihtiyacı yoktu (frontend statik dosya, CPU/bellek
yükü yaratmıyor), birleştirme CORS'u ve bir deploy adımını ortadan kaldırdı.
AI tarafı ise üç servise ayrıldı; gerekçe hâlâ aynı: RAG/embedding kütüphaneleri
farklı bağımlılık profiline sahip ve performans izolasyonu gerektiriyor
(chatbot yavaşlarsa/çökerse bankacılık işlemleri etkilenmemeli — bkz. gereksinim
FOG-04/FOG-05).

| Servis | Rol |
|---|---|
| `backend` | FastAPI monolit + derlenmiş frontend (tek dış giriş noktası) |
| `base-db` | PostgreSQL 16 — uygulama verisi |
| `vector-db` | pgvector — yalnızca `rag.documents` / `rag.chunks` |
| `rag` | Retrieval servisi. Vektör DB kredensiyelini tutan **tek** bileşen; embedding'i yerel çalıştırır |
| `mcp` | MCP tool sunucusu (SSE). Ajanların çağırdığı yedi tool |
| `agents` | LangGraph orchestrator. Yönlendirme + uzman ajanlar; Groq'a çıkar |
| `ingestor` | Fiyat (yfinance) ve haber (RSS) toplayıcı. DB kredensiyeli **taşımaz**, her şeyi HTTP ile iter |

Ağ topolojisi ve hangi servisin hangi URL'i kullandığı: `docs/DOCKER_NETWORKING.md`.

backend modülleri (auth, banking, investment, notification, analytics, market,
risk, compliance) network sınırı olmadan, aynı process içinde, doğrudan Python
import'uyla birbirini çağırır.

`banking` artık gerçek: `banking.accounts` + `banking.transactions` +
`banking.account_transactions` (migration 0008). Transfer, çift taraflı kayıt
olarak yazılıyor — bir `transactions` satırı ve iki `account_transactions`
bacağı (DEBIT/CREDIT), her biri `balance_before`/`balance_after` ile. Bakiyeleri
saklamak, bir hesabın belirli bir andaki durumunu tüm geçmişi yeniden
oynatmadan söyleyebilmeyi sağlıyor. Üçü **tek** transaction'da commit ediliyor:
borcu yazıp alacağı yazamamak, bir hesaptan çıkıp hiçbir yere varmamış para
demek.

```
moneyfast/
├── backend/            ← ana monolit (FastAPI) + frontend'in derlenmiş statik dosyaları
│   └── app/
│       ├── main.py     ← modül router'larını otomatik keşfedip toplar + StaticFiles serve
│       ├── core/        (config, DB bağlantısı, JWT middleware)
│       ├── modules/      auth/, banking/, investment/, notification/, analytics/,
│       │                 market/, risk/, compliance/, ai_orchestrator/
│       └── shared/      (SADECE domain'siz ortak kod — enum, exception, pagination.
│                         DB modeli KOYMA, bkz. "shared/ kuralı" aşağıda)
├── frontend/            ← React kaynak kodu (build sonrası backend image'ına kopyalanır)
├── AI-Services/
│   ├── moneyfast-orchestrator/          ← `agents` servisi (LangGraph + Groq)
│   │   └── mcp-server/                  ← `mcp` servisi (MCP tool sunucusu)
│   ├── moneyfast-rag/                   ← `rag` servisi (fastembed + vector-db)
│   └── moneyfast-ingestor/              ← `ingestor` servisi (yfinance + RSS)
├── infra/docker-compose.yml   ← 7 servisin tamamı, tek kaynak
└── docs/
```

### AI uç noktaları backend'de nerede

`mcp` içindeki tool'lar backend'e gerçek uç noktalar üzerinden gider. Bunların
gövde/yanıt şemaları **"MCP Tools Interface Definitions v2.2"ye karşı dondurulmuş**
— eksik bir alan default'lanmaz, tool katmanı `ContractViolationError` fırlatır.
Bu uç noktaları değiştirirken `AI-Services/.../mcp-server/*_tools.py` içindeki
`_normalize()` fonksiyonlarına bakılmalı.

| Tool | Uç nokta |
|---|---|
| `get_portfolio_positions` | `GET /api/investment/portfolio/{user_id}/positions` |
| `prepare_transaction_proposal` | `POST /api/investment/transactions/stage` |
| `calculate_portfolio_risk_metrics` | `POST /api/risk/calculate` |
| `validate_compliance_rules` | `POST /api/compliance/validate` |
| `rag_semantic_market_search` | `POST /search` — **backend'de değil, `rag` servisinde** |
| `get_market_data` | `GET /api/market/instruments` — v2.2 ile eklendi |

v2.3 ile `get_portfolio_positions` yanıtına `totals.cash_balance` ve
`totals.total_value` eklendi. Öncesinde sözleşmede nakit yoktu, dolayısıyla
"bakiyem ne kadar" sorusuna ajan ya pozisyonların piyasa değerini bakiye gibi
söylüyor ya da "bu veri sette yok" diyordu. `null` = bilinmiyor; sıfır olarak
raporlanmaz.

`sort_by` yalnızca beş değer alır: `symbol`, `change_percent` (en çok
yükselenler), `change_percent_asc` (en çok düşenler), `market_cap`, `pe_ratio`.
Bu liste hem `prompts.py`'deki uzman ajan sözleşmesinde hem de
`market_data_tools.ALLOWED_SORTS`'ta yazılı; ikisi ayrışırsa ajan geçersiz bir
değer üretir ve kullanıcı "veriye ulaşamadım" cevabı alır. Modelin sık yazdığı
eşanlamlılar (`gainers`, `change_percent_desc`) `_SORT_SYNONYMS` ile kanonik
hâle çevrilir; tanınmayan değer sessizce yok sayılmaz, hata verir.

Sohbet akışının kendisi `POST /api/ai_orchestrator/chat`. `user_id` gövdeden
DEĞİL, bearer token'dan çözülür (`app/core/deps.py`); MCP sözleşmesi bu değerin
yalnızca doğrulanmış oturumdan gelmesini şart koşuyor. İşlem onayı yalnızca
`POST /api/investment/transactions/{proposal_id}/confirm` üzerinden, kullanıcının
kendi eylemiyle verilir — sohbette "evet" demek onay sayılmaz.

Frontend'in kullandığı `/api/investment/positions`, `/api/investment/watchlist`
gibi uç noktalar bunlardan ayrı ve camelCase şemalarını koruyor; ikisi farklı
tüketicilere hizmet ediyor ve farklı sebeplerle değişiyor. Emir verme yolu ise
ortak: panel de sohbet de `transactions/stage` → `transactions/{id}/confirm`
kullanıyor (eski `/orders/propose` ve `/orders/confirm` taslakları kaldırıldı,
bkz. CONTRACT_WORKFLOW.md).

### Canlı fiyat akışı

`ingestor` 10 saniyede bir tek toplu yfinance isteğiyle ~95 enstrümanı çekip
backend'e HTTP ile yazıyor. Frontend `GET /api/market/stream` (SSE) üzerinden
dinliyor; `frontend/src/hooks/useMarketStream.ts` tüm uygulama için **tek**
`EventSource` tutuyor, akış kurulamazsa 10 saniyelik yoklamaya düşüyor.
Fiyata bağlı kolonları (pozisyon değeri, günlük/toplam getiri) yeniden hesaplama
işi `useLiveRows` içinde; yalnızca fiyatı tazeleyip yanındaki değeri dondurmak
satırı kendi içinde tutarsız bırakırdı.

## Teknoloji stack'i

- Backend: Python + FastAPI + PostgreSQL (SQLAlchemy + Alembic)
- AI servisleri: Python. RAG **pgvector** üzerinde (Chroma değil — karar ve
  gerekçe için MIMARI_KARARLAR.md). Embedding yerel çalışıyor (fastembed/ONNX,
  `paraphrase-multilingual-MiniLM-L12-v2`, 384 boyut, API anahtarı yok).
  LLM çıkışı yalnızca `agents` servisinde ve yalnızca Groq'a.
- Auth: ASP.NET Core Identity + JWT önerisi .NET dönemine aitti; Python'a dönüşle
  **FastAPI + python-jose (JWT) + passlib (parola hash)** kullanılıyor — Identity'nin
  Python karşılığı budur.
- Frontend: React + Vite + TypeScript + TailwindCSS
- Servisler arası tek network sınırı: backend ↔ ai-service (HTTP). Sözleşme yönetimi
  için bkz. `CONTRACT_WORKFLOW.md`.

### Nakit, takas ve hesaplar

Her kullanıcının kendi `investment.investment_accounts` satırı var (migration
0007). Onaylanan bir işlem `investment/service.py` içindeki `settle()` ile
uygulanır: nakit `payload["estimate"]["net_amount"]` kadar azalır/artar,
pozisyon **ağırlıklı ortalama maliyetle** güncellenir ve bunların hepsi
önerinin durum değişikliğiyle **aynı transaction** içinde commit edilir. Ayrı
commit'lemek, para hareket edip önerinin "beklemede" kalabildiği bir aralık
bırakırdı.

Alım, hem hazırlama (`ai_service.stage_transaction`) hem de onay anında bakiyeye
karşı kontrol edilir. İki kez, çünkü aynı bakiyeye karşı iki öneri hazırlanıp
sonra ikisi de onaylanabilir.

**Para birimi hiçbir yerde varsayılmaz.** Enstrümanın para birimi ile hesabın
para birimi ayrı şeyler: AAPL USD, hesap TRY. `net_amount` enstrümanın para
biriminde hesaplanır; bakiye kontrolü ve takas, `ai_service._convert` ile
hesabın para birimine çevirdikten sonra yapılır. Kur, önerinin üzerinde
`estimate.fx` olarak saklanır ve takasta yeniden çekilmez — kullanıcı o kurla
hesaplanmış bir maliyeti onayladı. Kur yoksa işlem **reddedilir**; 1.0
varsaymak 15.098 TL'lik bir alımı 315 TL'ye yaptırıyor, 226.468 TL'lik bir
satışı 4.723 TL'ye ödüyordu.

`source_account_id` sorulmaz: kullanıcının kendi hesabı backend'de çözülür.
Sorulduğu dönemde hiç doğrulanmıyordu ve gelen "1" değeri kabul edilip hiçbir
yerde kullanılmıyordu.

## shared/ kuralı — DB modeli asla buraya girmez

`shared/` çöp kutusu değil, sadece **domain'siz** ortak kod içindir: enum'lar
(`RiskLevel`, `TransactionType`), custom exception sınıfları, pagination
yardımcıları, generic tipler.

Bir DB modeli (SQLAlchemy sınıfı) her zaman onu **sahiplenen modülde** yaşar —
örn. `User` modeli sadece `app/modules/auth/models.py`'de. Başka bir modül
(`banking` gibi) o kullanıcıya referans vermek istediğinde, `User` sınıfını
import ETMEZ; sadece bir `user_id: UUID` foreign key kolonu tutar. Aynı Postgres
DB'si olduğu için bu foreign key sorunsuz çalışır, sadece Python seviyesinde
sınıfı import etmiyoruz — böylece modüller arası gizli bağımlılık ağı oluşmaz,
"sadece kendi modülünde çalış" kuralı anlamını korur.

## Modül sınırı kuralları — HERKES İÇİN GEÇERLİ

- **Sadece ilgili modülde çalışılır.** `app/modules/<modül>/` dışına, özellikle
  `core/` ve `shared/`'a dokunmak gerekiyorsa önce ekiple konuşulur, tek başına
  değiştirilmez.
- `main.py`'ye router eklemek için elle satır eklemeye gerek yok — router
  auto-discovery mekanizması modülü otomatik bulur (bkz. backend/app/main.py).
- **Alembic migration eklerken:** önce `main`'den güncel çekilir, migration en son
  adım olarak atılır, aynı gün migration atacak başka biri varsa koordine olunur
  (kısa bir mesajla "5 dk migration atıyorum" yeterli). Bu, tek gerçek çakışma
  noktası.
- Yeni bir endpoint/model eklendiğinde ya da mevcut biri değiştirildiğinde, bu bir
  "breaking change" olabilir — PR açıklamasına not düşülür (bkz. CONTRACT_WORKFLOW.md).

## Kod kuralları

- API key / secret asla kod içine hardcode edilmez. `.env` + `.env.example` + `.gitignore`.
- Format/lint: Python'da `ruff` + `black`, frontend'de `eslint` + `prettier` — pre-commit
  hook olarak bağlı, farklı ajanların farklı stilde kod üretmesini önler.
- **Testler: altı paketin altısı da %100 kapsama zorunlu** (backend, rag,
  orchestrator, mcp, ingestor, frontend). Her paket çalıştığında `junit.xml`
  (test sonuçları) ve `coverage.xml` (kapsama) üretir; frontend'de karşılığı
  `coverage/cobertura-coverage.xml`. Eşikler `pytest.ini`/`vitest.config.ts`
  içinde — Makefile'daki `coverage` hedefi değil, çünkü `make test` ve
  Dockerfile'lar düz `pytest` çalıştırıyor.
- Küçük, tek amaçlı PR'lar. Bir PR bir özellik/endpoint.
- Test verisi üretirken gerçekçi ama açıkça sahte veri kullan (örn. "TEST-" prefix'li
  müşteri ID'leri, gerçek olmayan TC formatları).

## Claude Code / agent kullanım notları

- Geniş kapsamlı görevlerde (yeni modül, mimari değişikliği) önce plan mode ile
  plan çıkar, onaylat, sonra uygula.
- Üretilen kod her zaman commit öncesi gözden geçirilir; otomatik commit'e güvenilmez.
- Antigravity gibi otonom, tarayıcı/terminal erişimli ajanlarla çalışırken: hiçbir
  otomatik işlem (dış siteden veri çekme, terminal komutu) review'suz merge edilmez.

## Analiz ve Tasarım Dokümanları

- docs/analiz/ — iş gereksinimleri, user story'ler, test senaryoları, UAT planı
- docs/tasarim/ — wireframe notları, tasarım referansları (Fintables)

Yeni bir modül/endpoint/ekran geliştirirken ilgili User Story ve İş Kuralı'na
(İK-XX) bakılmalı, kod bunlarla tutarlı olmalı.

## Belirsizlik ve Kapsam Kararları

- Bir User Story'de veya İş Kuralında AÇIKÇA tanımlı bir davranış varsa, ona
  sadık kal, sormaya gerek yok.
- Dokümanlar arasında belirsiz/eksik/çelişkili bir nokta bulursan (örn. iki
  dokümanın çelişmesi, ya da hiç bahsedilmeyen bir durum), varsayımda bulunup
  ilerlemek yerine kullanıcıya SOR.
- Proje mimarisini (modül sınırları, DB şeması, servisler arası iletişim gibi)
  etkileyecek bir karar noktasında da mutlaka sor.