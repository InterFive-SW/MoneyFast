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

## Mimari: modüler monolit + ayrı AI/RAG servisi

Neden bu şekilde: RAG/embedding kütüphaneleri farklı bağımlılık profiline sahip ve
performans izolasyonu gerektiriyor (chatbot yavaşlarsa bankacılık işlemleri
etkilenmemeli — bkz. gereksinim FOG-04/FOG-05). Bunun dışındaki tüm modüller
(auth, banking, investment, notification, analytics) network sınırı olmadan, aynı
process içinde, doğrudan Python import'uyla birbirini çağırır.

```
moneyfast/
├── backend/            ← ana monolit (FastAPI)
│   └── app/
│       ├── main.py     ← modül router'larını otomatik keşfedip toplar
│       ├── core/        (config, DB bağlantısı, JWT middleware)
│       ├── modules/      auth/, banking/, investment/, notification/, analytics/
│       └── shared/      (modüller arası ortak tipler)
├── ai-service/         ← ayrı servis: chatbot, RAG, MCP, ajanlar
├── frontend/           ← React
├── infra/docker-compose.yml
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

## Modül sınırı kuralları — HERKES İÇİN GEÇERLİ

- **Sadece kendi modülünde çalış.** `app/modules/<senin-modülün>/` dışına, özellikle
  `core/` ve `shared/`'a dokunman gerekiyorsa önce ekiple konuş, tek başına değiştirme.
- `main.py`'ye router eklemek için elle satır eklemene gerek yok — router
  auto-discovery mekanizması modülünü otomatik bulur (bkz. backend/app/main.py).
- **Alembic migration ekleyeceksen:** önce `main`'den güncel çek, migration'ı en son
  adım olarak at, aynı gün migration atacak biri varsa koordine ol (kısa bir mesajla
  "5 dk migration atıyorum" yeterli). Bu, tek gerçek çakışma noktası.
- Yeni bir endpoint/model eklediğinde ya da mevcut birini değiştirdiğinde, bu bir
  "breaking change" olabilir — PR açıklamasına not düş (bkz. CONTRACT_WORKFLOW.md).

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
