# Docker Network — Servisler Nasıl Haberleşiyor

Bu doküman, `infra/docker-compose.yml`'deki 7 servisin (`base-db`, `vector-db`,
`backend`, `rag`, `mcp`, `agents`, `ingestor`) birbirine nasıl bağlandığını, hangi URL/port'u
kullandığını ve **neden** böyle bağlandığını anlatır. Amaç: yeni bir servis eklerken
veya bir servisin diğerine bağlanamadığı bir hatayla karşılaşınca buraya bakıp
kendi kendine çözebilmek.

## 1. Temel kural: servis adı = hostname

`docker compose up` çalıştığında, container'lar birbirine **IP adresiyle değil,
`docker-compose.yml`'deki servis adıyla** ulaşır. `backend` servisinin adı
`backend`'se, başka bir container içinden `http://backend:...` yazınca Docker bunu
otomatik doğru container'a yönlendirir — internal bir DNS gibi düşünülebilir.

**`ports:` satırı sadece host makineden (Enes'in bilgisayarından) erişim içindir.**
Container'lar birbirine ulaşırken bu satırı hiç görmez/kullanmaz. Onun yerine hedef
servisin **container içinde gerçekten dinlediği port'u** kullanır.

Bu ikinci madde en çok karıştırılan yer — somut örnekle:

```yaml
backend:
  ports:
    - "8000:8000"   # ← SADECE Enes'in bilgisayarından (host) localhost:8000 için
```

`backend/Dockerfile`'da `uvicorn app.main:app --host 0.0.0.0 --port 8000` ile
container **içeride** 8000'i dinliyor. Bu örnekte host ve container port'u aynı
(8000) olduğu için kafa karıştırmıyor, ama **her zaman container içindeki port'a
göre** URL kurulmalı — host tarafındaki eşleme (`ports:`) alakasız.

## 2. Ağ üyeliği otomatik DEĞİL

Compose'un "tüm servisleri tek bir default ağa koyma" davranışı bu projede
**geçerli değil**: `docker-compose.yml` dört ağı elle tanımlıyor ve her servis
yalnızca ihtiyacı olanlara katılıyor.

| Ağ | Üyeler | `internal` | Amaç |
|---|---|---|---|
| `web-ingress` | `backend` | **hayır** | Host'tan gelen tek giriş (`ports: 8000:8000`) |
| `base-db-net` | `base-db`, `backend` | evet | Ana uygulama veritabanı trafiği |
| `vector-db-net` | `vector-db`, `rag` | evet | Vektör veritabanı trafiği |
| `moneyfast-net` | `backend`, `rag`, `mcp`, `agents`, `ingestor` | evet | Servisler arası HTTP/MCP |
| `ai-egress` | `agents` | hayır | Groq API'sine dışarı çıkış |
| `data-egress` | `ingestor` | hayır | yfinance ve RSS kaynaklarına çıkış |

### `web-ingress` neden ayrı ve neden `internal` değil

**Docker, yalnızca `internal: true` ağlara bağlı bir container'a host trafiğini
yönlendiremez.** `ports: "8000:8000"` satırı yazılmış olsa bile port sessizce
bind edilmez — `docker compose ps` çıktısında `0.0.0.0:8000->8000/tcp` yerine
sadece `8000/tcp` görünür ve `curl localhost:8000` "connection refused" verir.
Hata mesajı çıkmaz; bu yüzden config'e bakarak fark edilmesi zordur.

Bu yüzden `backend` ek olarak `internal` olmayan `web-ingress` ağına bağlı.
Bedeli şu: bridge ağ aynı zamanda dışarı çıkış da verir, yani `backend`
internete erişebilir. Kabul edilebilir, çünkü `backend` zaten dışarıya açılan
servis. `rag`, `mcp` ve veritabanları bu ağa girmez; onların izolasyonu
korunur.

`internal: true` olan ağlarda dışarı çıkış yoktur. **Yalnızca iki servis
internete çıkabilir ve ikisi de ayrı ağlardan çıkar:** `agents` (LLM
sağlayıcısı Groq dışarıda) ve `ingestor` (fiyat ve haber kaynakları
dışarıda). Ayrı ağlar, çünkü iki farklı gerekçe — birinin gerekçesi
ortadan kalkarsa diğerinin erişimi de kalkmalı.

`rag` internete çıkamaz ve çıkmasına gerek de yok: embedding modeli
image'ın içinde. `ingestor` da hiçbir veritabanı ağına giremez ve hiçbir
DB kredensiyeli taşımaz — internete çıkan tek toplayıcı, uygulama
verisinden bu şekilde uzak tutuluyor. Veritabanı container'ları bu
ağa asla katılmaz ve hiçbir veritabanı host'a port yayınlamaz.

İki servis aynı ağda değilse birbirini **göremez** — bu bir hata değil, kasıtlı
sınır. `mcp` doğrudan `vector-db`'ye ulaşamaz; ulaşması da gerekmez, `rag`
üzerinden gider.

## 3. Şu an kim kime bağlı

Bir sohbet turunun izlediği yol:

```
  host:8000
      │
      ▼
  BACKEND  ──HTTP──►  AGENTS  ──HTTP (SSE)──►  MCP
 (frontend +                                    │
  API, tek                                      ├──HTTP──►  BACKEND   (portföy, işlem,
  giriş noktası)                                │                      risk, uyumluluk)
      │                                         │
      │                                         └──HTTP──►  RAG       (semantik arama)
      │                                                       │
      ▼                                                       ▼
   BASE-DB                                                VECTOR-DB
  (moneyfast)                                            (moneyfast_rag)
  base-db-net                                             vector-db-net

  AGENTS   ──ai-egress────►  Groq API
  INGESTOR ──data-egress──►  yfinance + Türkçe RSS akışları
                             (dışarı çıkan yalnızca bu iki servis)

  INGESTOR ──POST──► BACKEND /api/market/ingest        (fiyat + mum)
           ──POST──► BACKEND /api/market/news/ingest   (haber, panel için)
           ──POST──► RAG     /ingest                   (haber, sohbet için)
```

Haberler iki yere birden yazılıyor: panel "en yeni 20 haber"i indeksli bir
sorguyla istiyor, sohbet ise semantik benzerlik arıyor. İki farklı erişim
deseni, iki farklı depo — tek kopya tutulsaydı biri diğerinin sorgusunu
taklit etmek zorunda kalırdı.

`backend` hem başlangıç noktası hem de bir ara durak: kullanıcı isteğini
`agents`'a iletir, `mcp` de veri için ona geri döner. Döngü değil, iki ayrı
sorumluluk — biri HTTP girişi, diğeri uygulama verisi.

| Bağlantı | URL / env değişkeni | Nerede tanımlı |
|---|---|---|
| backend → base-db | `DATABASE_URL` (`BASE_DATABASE_URL`'den) | `infra/docker-compose.yml` |
| backend → agents | `AI_ORCHESTRATOR_URL=http://agents:8080` | `infra/docker-compose.yml` |
| agents → mcp | `MCP_SERVER_URL=http://mcp:8000/sse` | `infra/docker-compose.yml` |
| mcp → backend | `BACKEND_API_BASE_URL=http://backend:8000/api` | `infra/docker-compose.yml` |
| mcp → rag | `RAG_API_BASE_URL=http://rag:8100` | `infra/docker-compose.yml` |
| rag → vector-db | `RAG_DATABASE_URL` | `infra/.env` |
| ingestor → backend | `BACKEND_API_BASE_URL` + `BACKEND_API_KEY` | `infra/docker-compose.yml` |
| ingestor → rag | `RAG_API_BASE_URL` | `infra/docker-compose.yml` |
| ingestor → yfinance / RSS | `NEWS_FEEDS` | `infra/.env` (boşsa yerleşik varsayılanlar) |
| agents → Groq | `GROQ_API_KEY` | `AI-Services/moneyfast-orchestrator/.env` |

**`base-db` ve `vector-db` birbirine bağlı değil.** İki ayrı, birbirinden habersiz
Postgres instance'ı (farklı image: `postgres:16` vs `pgvector/pgvector:pg16`, farklı
DB adı: `moneyfast` vs `moneyfast_rag`) ve **farklı ağlarda**. Aralarında veri
taşınması gerekiyorsa bu, DB-DB bağlantısıyla değil, HTTP isteğiyle yapılmalı —
servisler arası sınırı DB seviyesinde değil, API seviyesinde koruyoruz (bkz.
CLAUDE.md'deki `shared/` kuralının mantığı).

### `mcp` neden iki farklı base URL kullanıyor?

`mcp` içindeki yedi tool'dan beşi uygulama durumunu okur/yazar ve `backend`'e
gider (`/investment/portfolio/{user_id}/positions`,
`/investment/transactions/stage`, `/risk/calculate`, `/compliance/validate`,
`/market/instruments`). Altıncısı (`rag_semantic_market_search`) semantik arama
yapar ve doğrudan `rag`'e gider (`/search`). Yedincisi
(`classify_and_route_intent`) hiçbir yere gitmez, yerel hesaplanır.

Bunun sebebi kredensiyel sınırı: `rag`, vektör veritabanının bağlantı bilgisini
tutan **tek** servis. Aynı işi `backend` üzerinden proxy'leyerek de yapabilirdik
ama bu, hiçbir şey yapmayan bir uç nokta ve fazladan bir ağ atlaması demekti.

`backend_client.request()` her iki çağrıyı da aynı timeout, retry ve hata eşleme
politikasından geçirir; `base` parametresi yalnızca host'u değiştirir.

## 4. Başlangıç sırası

`depends_on` + `healthcheck` zinciri şunu garanti eder:

```
base-db (healthy) ──► backend ──┐
                                ├──► mcp (healthy) ──► agents
vector-db (healthy) ──► rag ────┘
     (healthy)
```

`rag`'in healthcheck'i `/readyz` uç noktasına bakar ve bu uç nokta iki şeyi birden
kanıtlar: embedding modeli belleğe yüklendi **ve** vector-db yanıt veriyor. Sadece
canlılık (`/healthz`) kontrol edilseydi, `mcp` henüz arama yapamayan bir
retriever'a karşı başlardı.

`vector-db` şema kurulumu ayrı bir container gerektirmez; Postgres'in kendi
`/docker-entrypoint-initdb.d/` mekanizması kullanılır (bkz.
`docs/VECTOR_DB_ARCHITECTURE.md`).

## 5. Yeni bir servis eklerken izlenecek adımlar

1. `docker-compose.yml`'e servisi ekle, bir isim ver (bu isim = hostname).
2. **Hangi ağlara katılacağını açıkça yaz.** Yazılmazsa hiçbir ağa katılmaz ve
   kimse ona ulaşamaz. Dışarı çıkması gerekmiyorsa `ai-egress`'e ekleme.
3. Bu servise bağlanması gereken servislerin ortam değişkenlerine
   `http://<yeni-servis-adı>:<container-içi-port>` formatında bir URL ekle —
   host tarafındaki `ports:` eşlemesini kullanma.
4. Gerekliyse `depends_on` + `healthcheck` ekle.
5. Yeni servisin gerçekten doğru servise bağlandığını doğrulamak için:
   ```bash
   docker compose exec <servis> python -c \
     "import urllib.request;print(urllib.request.urlopen('http://<hedef>:<port>/healthz').read())"
   ```
   Container içinden container içine gerçek bir istek atarak network'ün
   çalıştığını kanıtlamak gerekir; sadece config'e bakıp "olması lazım"
   denilmemelidir.
