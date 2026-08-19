# Docker Network — Servisler Nasıl Haberleşiyor

Bu doküman, `infra/docker-compose.yml`'deki 5 servisin (postgres, backend, vector-db,
mcp-market-data, orchestrator_agent) birbirine nasıl bağlandığını, hangi URL/port'u
kullandığını ve **neden** böyle bağlandığını anlatır. Amaç: yeni bir servis eklerken
veya bir servisin diğerine bağlanamadığı bir hatayla karşılaşınca buraya bakıp
kendi kendine çözebilmek.

## 1. Temel kural: servis adı = hostname

`docker compose up` çalıştığında, `docker-compose.yml` içindeki **tüm servisler
otomatik olarak aynı sanal ağa (network) katılır** — bunun için hiçbir şey
yazmıyoruz, Compose kendisi yapıyor. Bu ağın içinde iki şey doğru:

1. **Bir container'dan diğerine, IP adresiyle değil, `docker-compose.yml`'deki
   servis adıyla ulaşılır.** `backend` servisinin adı `backend`'se, başka bir
   container içinden `http://backend:...` yazınca Docker bunu otomatik doğru
   container'a yönlendirir — internal bir DNS gibi düşünebilirsin.
2. **`ports:` satırı sadece SENİN bilgisayarından (host) erişim içindir.**
   Container'lar birbirine ulaşırken bu satırı hiç görmez/kullanmaz. Onun yerine
   hedef servisin **container içinde gerçekten dinlediği port'u** kullanır.

Bu ikinci madde en çok karıştırılan yer — somut örnekle:

```yaml
backend:
  ports:
    - "8000:8000"   # ← SADECE senin tarayıcından localhost:8000 için
```

`backend/Dockerfile`'da `uvicorn app.main:app --host 0.0.0.0 --port 8000` ile
container **içeride** 8000'i dinliyor. Bu örnekte host ve container port'u aynı
(8000) olduğu için kafa karıştırmıyor, ama **her zaman container içindeki port'a
göre** URL kurulmalı — host tarafındaki eşleme (`ports:`) alakasız.

## 2. Şu an kim kime bağlı (gerçek `docker-compose.yml`'den)

```
FRONTEND+BACKEND (tek container, backend statik frontend'i serve eder)
        │  DATABASE_URL=postgresql://...@postgres:5432/moneyfast
        ▼
   POSTGRES (ana veritabanı)

   BACKEND ──HTTP──► ORCHESTRATOR_AGENT
        (backend/app/modules/ai_orchestrator/router.py, settings.AI_ORCHESTRATOR_URL)

   ORCHESTRATOR_AGENT ──HTTP (SSE)──► MCP-MARKET-DATA
        MCP_SERVER_URL=http://mcp-market-data:8000/sse

   MCP-MARKET-DATA ──postgres protokolü──► VECTOR-DB
        VECTOR_DB_URL=postgresql://...@vector-db:5432/moneyfast_rag
```

| Bağlantı | Env değişkeni | Nerede tanımlı |
|---|---|---|
| backend → postgres | `DATABASE_URL` | `infra/docker-compose.yml`, `backend` servisi |
| backend → orchestrator_agent | `AI_ORCHESTRATOR_URL` | `backend/.env` (gitignore'da, repoya girmez) |
| orchestrator_agent → mcp-market-data | `MCP_SERVER_URL` | `infra/docker-compose.yml`, `orchestrator_agent` servisi |
| mcp-market-data → vector-db | `VECTOR_DB_URL` | `infra/docker-compose.yml`, `mcp-market-data` servisi |

**`postgres` ve `vector-db` birbirine bağlı değil.** İki ayrı, birbirinden
habersiz Postgres instance'ı (farklı image: `postgres:16` vs
`pgvector/pgvector:pg16`, farklı DB adı: `moneyfast` vs `moneyfast_rag`).
Aralarında veri taşınması gerekiyorsa (örn. kullanıcı hesabı silinince RAG
verisinin de silinmesi) bu, DB-DB bağlantısıyla değil, **backend'in
orchestrator'a/mcp-market-data'ya bir HTTP isteği atmasıyla** yapılmalı —
servisler arası sınırı DB seviyesinde değil, API seviyesinde koruyoruz (bkz.
CLAUDE.md'deki `shared/` kuralının mantığı — aynı prensip burada da geçerli).

## 3. Bilinen eksik: `BACKEND_API_BASE_URL`

`AI-Services/moneyfast-orchestrator/mcp-server/backend_client.py`, MCP
tool'larının backend'e (ör. portföy verisi çekmek için) HTTP isteği atmasını
sağlıyor. Kodun varsayılanı:

```python
DEFAULT_BASE_URL = "http://backend:3000/api/v1"
```

Bu **yanlış** — backend gerçekte `8000` portunu dinliyor (`/v1` de yok, router'lar
`/api/{modül}` şeklinde bağlanıyor, bkz. `backend/app/main.py`). Doğrusu:

```
http://backend:8000/api
```

Bu env değişkeni şu an `infra/docker-compose.yml`'deki `mcp-market-data`
servisinde **hiç tanımlı değil** — eklenmesi gerekiyor:

```yaml
mcp-market-data:
  environment:
    BACKEND_API_BASE_URL: http://backend:8000/api
```

## 4. Yeni bir servis eklerken izlenecek adımlar

1. `docker-compose.yml`'e servisi ekle, bir isim ver (bu isim = hostname).
2. Bu servise bağlanması gereken servislerin ortam değişkenlerine
   `http://<yeni-servis-adı>:<container-içi-port>` formatında bir URL ekle —
   host tarafındaki `ports:` eşlemesini kullanma, container'ın kendi
   `EXPOSE`/dinlediği port neyse onu yaz.
3. Gerekliyse `depends_on` + `healthcheck` ekle, böylece bağımlı servis, hedef
   servis hazır olana kadar beklemeden başlamaz (bkz. `mcp-market-data`'nın
   `vector-db`'yi `condition: service_healthy` ile beklemesi).
4. Yeni servisin gerçekten doğru servise bağlandığını doğrulamak için:
   ```bash
   docker exec <container-adı> curl -s http://<hedef-servis>:<port>/health
   ```
   (veya hedefin sağlık endpoint'i neyse) — container içinden container içine
   gerçek bir istek atarak network'ün çalıştığını kanıtla, sadece config'e
   bakıp "olması lazım" deme.
