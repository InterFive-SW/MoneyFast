# MoneyFast

InterFive takımı tarafından InternTech 2026 kapsamında geliştirilen, çoklu ajan
mimarisiyle çalışan akıllı kişisel finans danışmanı. Chatbot odakta; bankacılık
işlemleri, yatırım/portföy yönetimi, RAG tabanlı piyasa/haber okuma ve risk
değerlendirmesi sunuyor.

## Mimari

Yedi container:

| Servis | Rol |
|---|---|
| **backend** | Python + FastAPI modüler monolit. Bankacılık, yatırım, auth, bildirim, analitik, risk, uyumluluk modülleri + **frontend** (statik, aynı origin). Tek dış giriş noktası |
| **base-db** | PostgreSQL 16 — uygulama verisi |
| **vector-db** | pgvector — yalnızca RAG korpusu |
| **rag** | Retrieval servisi. Embedding'i yerel çalıştırır; vektör DB kredensiyelini tutan tek bileşen |
| **mcp** | MCP tool sunucusu. Ajanların çağırdığı yedi tool |
| **agents** | LangGraph orchestrator (Groq). Yönlendirme + uzman ajanlar |
| **ingestor** | Fiyat (yfinance) ve haber (RSS) toplayıcı. Veritabanı kredensiyeli taşımaz |

AI tarafının backend'den ayrı tutulmasının sebebi performans/bağımlılık
izolasyonu: chatbot yavaşlarsa veya çökerse bankacılık işlemleri etkilenmemeli.

Neden bu şekilde ve hangi kararların nasıl alındığı için: **[docs/MIMARI_KARARLAR.md](docs/MIMARI_KARARLAR.md)**.
Hangi servisin hangi ağda ve hangi URL'i kullandığı için:
**[docs/DOCKER_NETWORKING.md](docs/DOCKER_NETWORKING.md)**.

Ana işlemler ve RAG retrieval yükü iki bağımsız PostgreSQL instance'ında
çalışır. Vector DB sınırları, şema sahipliği ve kaynak izolasyonu için:
**[docs/VECTOR_DB_ARCHITECTURE.md](docs/VECTOR_DB_ARCHITECTURE.md)**.

```
moneyfast/
├── backend/          FastAPI modüler monolit + frontend'in derlenmiş hali
│   └── app/
│       ├── main.py    router auto-discovery + SPA serving
│       ├── core/       config, DB, JWT
│       └── modules/    auth, banking, investment, notification, analytics,
│                       market, risk, compliance, ai_orchestrator
├── frontend/         React + Vite + TS + Tailwind (kaynak kod)
├── AI-Services/
│   ├── moneyfast-orchestrator/       `agents` servisi (LangGraph + Groq)
│   │   └── mcp-server/               `mcp` servisi (MCP tool sunucusu)
│   ├── moneyfast-rag/                `rag` servisi (fastembed + vector-db)
│   └── moneyfast-ingestor/           `ingestor` servisi (yfinance + RSS)
├── infra/            docker-compose.yml (7 servisin tamamı)
├── docs/             MIMARI_KARARLAR.md ve diğer proje dokümanları
├── CLAUDE.md         Claude Code / AI ajanları için proje context'i
└── CONTRACT_WORKFLOW.md   Servisler arası sözleşme yönetimi
```

## Çalıştırma

Gereksinimler: Docker + Docker Compose.

```bash
cp infra/.env.example infra/.env
# infra/.env içindeki change-me değerlerini değiştir
# BACKEND_API_KEY için: python3 -c "import secrets; print(secrets.token_hex(24))"
cp backend/.env.example backend/.env
cp AI-Services/moneyfast-orchestrator/.env.example AI-Services/moneyfast-orchestrator/.env
# .env içine GROQ_API_KEY ekle (https://console.groq.com — ücretsiz)
cd infra
docker compose --env-file .env up -d --build
```

İlk build'de `rag` image'ı embedding modelini (~220MB ONNX) indirip image'a
gömer; bu adım bir kereliktir. Çalışma anında hiçbir model indirmesi yapılmaz
ve **hiçbir embedding API anahtarı gerekmez**.

- `http://localhost:8000` → React uygulaması
- `http://localhost:8000/docs` → Swagger UI (API dokümantasyonu)
- `http://localhost:8000/api/<modül>/...` → API endpoint'leri

İlk çalıştırmada `base-db` hazır olduktan sonra backend otomatik olarak Alembic
migration'larını uygular, elle bir şey yapmana gerek yok.

`vector-db` şeması, Postgres'in kendi `/docker-entrypoint-initdb.d/`
mekanizmasıyla ilk açılışta kurulur — ayrı bir migration container'ı yok.
Bunun bedeli şu: **initdb yalnızca boş bir volume'de çalışır.** Şema
dosyalarını değiştirdikten sonra değişikliğin geçerli olması için volume'ün
bir kez silinmesi gerekir (yalnızca vektör tarafı; `postgres_data` etkilenmez):

```bash
cd infra && docker compose down && docker volume rm infra_vector_db_data
docker compose --env-file .env up -d --build
```

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
- Servisler arası sözleşme yönetimi için: **[CONTRACT_WORKFLOW.md](CONTRACT_WORKFLOW.md)**.
- `mcp`'nin çağırdığı backend uç noktalarının şemaları MCP v2.2'ye karşı
  dondurulmuş; değiştirmeden önce CLAUDE.md'deki "AI uç noktaları backend'de
  nerede" tablosuna bak.
- Frontend'de tip kontrolü `npm run typecheck` (ya da `npm run build`) ile
  çalışır. Kök `tsconfig.json` bir solution dosyası olduğu için düz `tsc`
  hiçbir şeye bakmıyordu; script `tsc -b`'ye çevrildi.
- **Testler: altı paket, altısı da %100.** Beş Python paketi `pytest`, frontend
  `npm test` (Vitest). Her çalıştırma `junit.xml` + kapsama XML'i yazar:

```bash
cd backend && pytest          # junit.xml + coverage.xml
cd frontend && npm run coverage   # junit.xml + coverage/cobertura-coverage.xml
```

## Durum

- ✅ Sistem mimarisi (7 container)
- ✅ Backend altyapısı
- ✅ Frontend altyapısı (backend'e entegre)
- ✅ AI servisleri: `agents` (Groq), `mcp`, `rag` (yerel embedding)
- ✅ AI ↔ backend uç noktaları (portföy, işlem, risk, uyumluluk, semantik arama)
- ✅ Canlı veri: `ingestor` fiyat, mum ve haberleri periyodik topluyor
- ✅ Sohbet uçtan uca: yönlendirme, geçmiş, kalıcılık, widget'lar, işlem onayı
- ✅ Canlı fiyatlar arayüzde: SSE akışı; şerit, izleme listesi, pozisyonlar ve
  mini kutucuklar aynı tek bağlantıdan besleniyor
- ✅ Piyasalar > Hisseler / Sektörler canlı veriden; kaynağı olmayan ekranlar
  (Fonlar, Endeksler, bazı Analizler) "Örnek veri" rozetiyle işaretli
- ⏳ Gerçek risk metrikleri — mum verisi artık var, `risk/service.py`'deki
  `None` dönen dallar açılabilir
- ✅ Analytics: Portföy Analizi (dağılım, trend, performans, işlem geçmişi)
- ✅ Nakit takası: onaylanan işlem bakiyeyi ve pozisyonu gerçekten değiştirir
- ✅ Banking: mevduat hesapları ve çift taraflı kayıtla para transferi
  (kendi hesapların arasında ve başka kullanıcıya)
- ⏳ Modül implementasyonları (notification)
- ⏳ Kalan panel mock uç noktaları (heatmap, temettü, sektör dağılımı)

Açık kararlar ve eksik altyapı parçaları için: **[docs/MIMARI_KARARLAR.md](docs/MIMARI_KARARLAR.md)**.
