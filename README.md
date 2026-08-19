# MoneyFast

InterFive takımı tarafından InternTech 2026 kapsamında geliştirilen, çoklu ajan
mimarisiyle çalışan akıllı kişisel finans danışmanı. Chatbot odakta; bankacılık
işlemleri, yatırım/portföy yönetimi, RAG tabanlı piyasa/haber okuma ve risk
değerlendirmesi sunuyor.

## Mimari

İki servis:

- **backend/** — Python + FastAPI modüler monolit. Bankacılık, yatırım, auth,
  bildirim, analitik modüllerini ve **frontend'i** (statik olarak, aynı origin'den)
  barındırır.
- **ai-service/** — Chatbot, RAG, MCP, ajanlar. Performans/bağımlılık izolasyonu
  için backend'den ayrı tutuluyor (chatbot yavaşlarsa bankacılık işlemleri
  etkilenmemeli).

Neden bu şekilde ve hangi kararların nasıl alındığı için: **[docs/MIMARI_KARARLAR.md](docs/MIMARI_KARARLAR.md)**.

Core işlemler ve RAG retrieval yükü iki bağımsız PostgreSQL instance'ında
çalışır. Vector DB sınırları, migration sahipliği ve kaynak izolasyonu için:
**[docs/VECTOR_DB_ARCHITECTURE.md](docs/VECTOR_DB_ARCHITECTURE.md)**.

```
moneyfast/
├── backend/          FastAPI modüler monolit + frontend'in derlenmiş hali
│   └── app/
│       ├── main.py    router auto-discovery + SPA serving
│       ├── core/       config, DB, JWT
│       └── modules/    auth, banking, investment, notification, analytics
├── frontend/         React + Vite + TS + Tailwind (kaynak kod)
├── ai-service/       Chatbot, RAG, MCP, ajanlar (henüz kurulmadı)
├── infra/            docker-compose.yml
├── docs/             MIMARI_KARARLAR.md ve diğer proje dokümanları
├── CLAUDE.md         Claude Code / AI ajanları için proje context'i
└── CONTRACT_WORKFLOW.md   Servisler arası sözleşme yönetimi
```

## Çalıştırma

Gereksinimler: Docker + Docker Compose.

```bash
cp infra/.env.example infra/.env
# infra/.env içindeki change-me değerlerini değiştir
cd infra
docker compose up --build
```

- `http://localhost:8000` → React uygulaması
- `http://localhost:8000/docs` → Swagger UI (API dokümantasyonu)
- `http://localhost:8000/api/<modül>/...` → API endpoint'leri

İlk çalıştırmada Postgres hazır olduktan sonra backend otomatik olarak Alembic
migration'larını uygular, elle bir şey yapmana gerek yok.
Vector DB migration'ları ayrı `vector-migrations` job'ı tarafından checksum
kontrollü olarak uygulanır; backend vector şemasını migrate etmez.

### Ortam değişkenleri

`backend/.env.example` dosyasını `backend/.env` olarak kopyala, `SECRET_KEY`'i
rastgele bir değerle değiştir:

```bash
cd backend
cp .env.example .env
python3 -c "import secrets; print(secrets.token_hex(32))"   # çıktıyı SECRET_KEY'e yapıştır
```

## Geliştirme kuralları

Detaylar için **[CLAUDE.md](CLAUDE.md)** — özet:

- Her kişi kendi modülünde (`app/modules/<isim>/`) çalışır, `core/` ve `shared/`'a
  dokunmadan önce ekiple konuşulur.
- Yeni bir modül router'ı eklemek `main.py`'ye elle satır eklemeyi gerektirmez
  (auto-discovery).
- DB modelleri `shared/`'a değil, sahiplendiği modüle konur.
- Servisler arası (backend↔ai-service) sözleşme yönetimi için:
  **[CONTRACT_WORKFLOW.md](CONTRACT_WORKFLOW.md)**.

## Durum

- ✅ Sistem mimarisi
- ✅ Backend altyapısı
- ✅ Frontend altyapısı (backend'e entegre)
- ⏳ ai-service iskeleti
- ⏳ Modül implementasyonları (banking, investment, notification, analytics)

Açık kararlar ve eksik altyapı parçaları için: **[docs/MIMARI_KARARLAR.md](docs/MIMARI_KARARLAR.md)**.
