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

## Mimari: backend+frontend birlikte, AI/RAG ayrı servis (2 Dockerfile)

Güncelleme: Başlangıçta 3 ayrı servis (backend, frontend, ai-service) planlanmıştı;
PO ile yapılan değerlendirme sonrası **frontend backend'e birleştirildi** —
aralarında gerçek bir izolasyon ihtiyacı yoktu (frontend statik dosya, CPU/bellek
yükü yaratmıyor), birleştirme CORS'u ve bir deploy adımını ortadan kaldırdı.
**ai-service ayrı kaldı** — bunun gerekçesi hâlâ geçerli: RAG/embedding
kütüphaneleri farklı bağımlılık profiline sahip ve performans izolasyonu
gerektiriyor (chatbot yavaşlarsa/çökerse bankacılık işlemleri etkilenmemeli —
bkz. gereksinim FOG-04/FOG-05). Frontend çökerse zaten kullanıcı hiçbir şeye
erişemez, bu yüzden onu izole etmenin gerçek bir koruma değeri yoktu.

backend modülleri (auth, banking, investment, notification, analytics) network
sınırı olmadan, aynı process içinde, doğrudan Python import'uyla birbirini çağırır.

```
moneyfast/
├── backend/            ← ana monolit (FastAPI) + frontend'in derlenmiş statik dosyaları
│   └── app/
│       ├── main.py     ← modül router'larını otomatik keşfedip toplar + StaticFiles serve
│       ├── core/        (config, DB bağlantısı, JWT middleware)
│       ├── modules/      auth/, banking/, investment/, notification/, analytics/
│       └── shared/      (SADECE domain'siz ortak kod — enum, exception, pagination.
│                         DB modeli KOYMA, bkz. "shared/ kuralı" aşağıda)
├── frontend/            ← React kaynak kodu (geliştirme sırasında ayrı, build sonrası backend'e kopyalanır)
├── ai-service/         ← ayrı servis: chatbot, RAG, MCP, ajanlar
├── infra/docker-compose.yml   ← backend (frontend dahil) + ai-service + postgres + redis
└── docs/
```

## Teknoloji stack'i

- Backend: Python + FastAPI + PostgreSQL (SQLAlchemy + Alembic)
- AI servis: Python, RAG (Chroma), MCP, LLM sağlayıcı — karar için MIMARI_KARARLAR.md'ye bakın
- Auth: ASP.NET Core Identity + JWT önerisi .NET dönemine aitti; Python'a dönüşle
  **FastAPI + python-jose (JWT) + passlib (parola hash)** kullanılıyor — Identity'nin
  Python karşılığı budur.
- Frontend: React + Vite + TypeScript + TailwindCSS
- Servisler arası tek network sınırı: backend ↔ ai-service (HTTP). Sözleşme yönetimi
  için bkz. `CONTRACT_WORKFLOW.md`.

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