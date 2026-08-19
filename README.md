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
cd infra
docker compose up --build
```

- `http://localhost:8000` → React uygulaması
- `http://localhost:8000/docs` → Swagger UI (API dokümantasyonu)
- `http://localhost:8000/api/<modül>/...` → API endpoint'leri

İlk çalıştırmada Postgres hazır olduktan sonra backend otomatik olarak Alembic
migration'larını uygular, elle bir şey yapmana gerek yok.

### Ortam değişkenleri

`backend/.env.example` dosyasını `backend/.env` olarak kopyala, `SECRET_KEY`'i
rastgele bir değerle değiştir:

```bash
cd backend
cp .env.example .env
python3 -c "import secrets; print(secrets.token_hex(32))"   # çıktıyı SECRET_KEY'e yapıştır
```

### Dummy Data Generator

Geliştirme aşamasında test verilerine ihtiyaç duyarsanız, veritabanına sentetik kullanıcılar ekleyebilirsiniz. Bu script **yalnızca** lokal veya test veritabanlarında çalışır (güvenlik kontrolü mevcuttur).

Çalıştırmak için `backend` dizininde:

```bash
# 50 adet sahte kullanıcı üretir
python -m scripts.generate_dummy_data --users 50

# Test verilerini üretirken her zaman aynı verileri elde etmek için seed kullanabilirsiniz
python -m scripts.generate_dummy_data --users 10 --seed 42

# Sadece üretilmiş olan eski sahte kullanıcıları ("999" prefix'li T.C. numaraları vs.) temizler
python -m scripts.generate_dummy_data --reset
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
