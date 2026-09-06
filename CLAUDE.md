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
| `get_open_orders` | `GET /api/investment/agent/{user_id}/orders` — v2.20 |
| `cancel_order` | `POST /api/investment/agent/{user_id}/orders/{id}/cancel` — v2.20 |

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

`POST /api/ai_orchestrator/chat/stream` aynı turu SSE ile yürütür: graf
düğümleri ilerledikçe `stage` olayları, sonunda tek bir `done`. **Model
çıktısı token token akmaz.** Graf fail-closed: uygunluk kapısının engellediği
bir taslak kullanıcıya ulaşmamalı, ekrana yazılmış metin ise geri alınamaz.
Bu yüzden yalnızca ilerleme akar; onaylanmış metin istemcide daktilo
efektiyle gösterilir (`useTypewriter`). Akış kurulamazsa istemci tamponlu
`/chat` uç noktasına düşer.

### Oturum ömrü

Access token 30 dakika yaşar ve `get_optional_user_id` süresi dolmuş bir
token'ı **anonim** sayar — okuma uçları için doğru, para hareketi için değil.
Bu ikisi bir süre karışmıştı: oturum sessizce anonime düşüyor, sohbet
çalışmaya devam ediyor, ama hazırladığı öneriler `user_id="anonymous"` ile
kaydediliyordu. Bu öneriler DEMO hesabına karşı fiyatlanıyor ve onay adımının
sahiplik denetimini hiçbir zaman geçemiyordu: kullanıcı, her basışta 404
dönen bir "Onayla" düğmesi görüyordu.

İki taraflı çözüldü: `POST /api/auth/refresh` (uzun ömürlü yenileme token'ı,
`typ` claim'i ile access token'dan ayrılır; biri diğerinin yerine
kullanılamaz) oturumu sessizce tazeler, ve `transactions/stage` sahibi
belirsiz bir öneriyi **401 ile reddeder**. `market_service.account` artık
`allow_demo_fallback=False` alabiliyor — demo portföyünü okumak zararsız,
ona karşı işlem fiyatlamak değil.

### İki piyasa

Evren 88 BIST + 3 ABD hissesiydi; o üçü yalnızca demo portföyü onları tuttuğu
için vardı. Migration 0010 ile **Nasdaq-100** eklendi (96 sembol; ANSS ve EA
sağlayıcıda fiyat döndürmediği için listeden çıkarıldı — fiyatlanamayan bir
adı tohumlamak, olmayan bir enstrümanı varmış gibi göstermek olurdu). Üyelik
listesi 0006'daki BIST listesi gibi elle yazılı ve tarihli: endeks üyeliği
lisanslı bir üründür ve altından sessizce değişen bir tohum, diff'te
okunabilenden kötüdür.

Ekranlarda BIST / ABD / Tümü süzgeci var; sohbette `get_market_data`'nın
`market` filtresi kullanılıyor (aksi hâlde "en çok yükselen ABD hisseleri"
listesinin başında bir Türk hissesi çıkıyordu). Alım-satım yolu ortak: ABD
emri USD cinsinden fiyatlanır, öneride saklanan kurla TRY'ye çevrilir ve
bakiye kontrolü hesabın para biriminde yapılır.

**Bir pozisyon satırında iki para birimi vardır.** `last_price` ve `avg_cost`
enstrümanın kendi para biriminde; `market_value`, `cost_basis` ve
`unrealized_pnl` ise zaten `base_currency`'ye çevrilmiş. Bunu söyleyen bir
kural yoktu ve 481 dolarlık bir MSFT pozisyonu "23.068,69 USD" olarak
yazıldı — TL değeri, yanlış birimle, yaklaşık kırk kat abartılmış.

### Sütunlar hangi araçtan geldiyse ona uyar

Tek bir varsayılan sütun seti vardı ve bu bir TARAMA setiydi:
`| Hisse | Sektör | Fiyat (TL) | 1.000 TL ile lot | Günlük ciro | F/K |`.
"portföyümü göstersene" sorusuna portföy verisiyle bu sütunlar dolduruldu;
portföy aracı bu alanların hiçbirini döndürmediği için tablonun tamamı
"veri yok" oldu. Veri eksik değildi — sektör 94 enstrümanın 90'ında, F/K
64'ünde vardı.

`Günlük ciro` ise yapısal olarak boştu: hacim her `market_quotes` satırında
DOLU saklanıyor ama hiçbir uç nokta dışarı vermiyordu. Artık veriliyor.

`veri yok`, o satırda eksik olan bir değeri işaretler; aracın hiç döndürmediği
bir alan için kullanılmaz, o sütun hiç yazılmaz.

### İzleme listesi

`GET /api/investment/watchlist` evrenin ilk sekiz hissesini alfabetik
döndürüyordu: herkese aynı liste, kimsenin seçimini yansıtmayan ve arayüzden
değiştirilemeyen bir "izleme listesi". Artık `investment.watchlist_items`
(migration 0011) üzerinden **kullanıcıya ait**; Piyasalar ekranındaki yıldız
onu yazıyor, Gösterge Paneli ve Portföy sayfası aynı `WatchlistWidget`'ı
kullandığı için üç yüzey asla farklı bir liste gösteremez.

Boşsa boş görünür ve Piyasalar'a yönlendirir. Kullanıcının seçmediği hisseleri
onun listesiymiş gibi göstermek, listenin ne olduğunu anlamsızlaştırır.
Sekmeler `bist` / `global` / `all`; eskiden API'de olmayan `us` ve `crypto`
anahtarlarını okuduğu için ABD ve Kripto sekmeleri her zaman boştu ve sistemde
hiç kripto enstrümanı yok.

Kotanın (`WATCHLIST_LIMIT = 8`) yeri yok: elle kurulmuş bir liste kullanıcının
yaptığı kadardır, kırpmak onun bilerek eklediği enstrümanı gizler.

### İç isimler kullanıcıya sızmaz

Ölçüm: 158 asistan yanıtında `source` enum'u 7 kez, ham alan adı 1 kez, iç
anahtarlar 9 kez kullanıcıya ulaşmıştı —
`Veri YFINANCE_DELAYED kaynağından, 17 dk gecikmeli (as_of 2026-08-21 13:32)`
ve `sıralama = günlük yüzde değişim (change_percent)` gibi.

İki katman: `prompts.py`'deki **NAMING** kuralı modele ne yapacağını söyler,
`sanitize.py` ise bunu doğru kılar. Prompt tavsiyedir — kriz kaynaklarında
ölçüldüğünde yaklaşık yarı yarıya uyuluyordu, `_keep_crisis` bu yüzden var.
Temizleyici `api._response_payload` içinde, yani `/chat` ve `/chat/stream`'in
ortak tek çıkış noktasında çalışır ve neyi kaldırdığını **loglar**: boş log,
prompt'un çalıştığı anlamına gelir.

Tazelik tek bir biçimde yazılır:
`Fiyatlar 15 dakika gecikmeli; 21 Ağustos 13:32 itibarıyla.` Sağlayıcı adı
geçmez, köşeli parantez içinde ham zaman damgası olmaz.

### Ajan izleme (trace)

`agent_trace.py` her graf düğümünü ve her MCP tool çağrısını
`traces/agent-trace-YYYY-MM-DD.jsonl` dosyasına satır satır yazar: `trace_id`,
süre (ms), durum, tam girdi ve çıktı. İki bağlama noktası var — `build_graph()`
düğümleri kaydederken sarmalar, `MCPClient.call` ise tek tool yoludur —
dolayısıyla ne düğümlerin ne de tool'ların bundan haberi olur.

`trace_id` tur başına üretilir; tool çağrısı graf durumunu göremediği için id
bir `contextvars.ContextVar` ile taşınır. Kayıt **hiçbir koşulda turu
düşürmez**: serileşmeyen değer `repr`'e düşer, yazılamayan dizin bir uyarıyla
tracing'i kapatır. `AGENT_TRACE=0` ile tamamen kapanır.

Dizin `traces/` gitignore'da: tam gövde kaydedildiği için içinde bakiye,
pozisyon ve kullanıcının kendi mesajları var.

### Kriz ve güvenlik sinyalleri

`detect_safety_flags` üç ayrı kategori üretir: `SELF_HARM_RISK`,
`COERCION_RISK`, `FINANCIAL_DISTRESS` (üçü de `DISTRESS_SIGNAL` ile birlikte,
yönlendirme onu okuyor). Tek bir listeydiler ve besledikleri tek yönerge
finansal sıkıntı için yazılmıştı; sonuç, "ölmek istiyorum" diyen birine
borçla yatırımın riski anlatmaktı.

Kriz kaynakları **modelden istenmez**, `crisis_notices` olarak koda gömülüdür
ve `_keep_crisis` ile uygunluk kapısının HER dalında — BLOCK dahil —
`disclosures`'a eklenir. Modelin unutabildiği bir kaynak bloğu güvenlik
denetimi değildir; ölçüldüğünde yaklaşık yarı yarıya çıkıyordu. Numaralar
sabit: model bir kez "ALO 182" (MHRS randevu hattı) önermişti.

Ürün bir uzmana yönlendirme yapamıyor, bu yüzden **teklif de etmez**. Eskiden
"sizi bir uzmana yönlendirebilirim" deyip, kullanıcı kabul edince
"yönlendirme yapamıyorum" diyordu.

Frontend'in kullandığı `/api/investment/positions`, `/api/investment/watchlist`
gibi uç noktalar bunlardan ayrı ve camelCase şemalarını koruyor; ikisi farklı
tüketicilere hizmet ediyor ve farklı sebeplerle değişiyor. Emir verme yolu ise
ortak: panel de sohbet de `transactions/stage` → `transactions/{id}/confirm`
kullanıyor, ve bekleyen bir emrin geri çekilmesi de öyle
(`transactions/{id}/cancel`; sohbetin yolu `agent/{user_id}/orders/...` ama
ikisi de `_cancel_order` üzerinden geçiyor) (eski `/orders/propose` ve `/orders/confirm` taslakları kaldırıldı,
bkz. CONTRACT_WORKFLOW.md).

### Canlı fiyat akışı

**Tek fiyat kuralı:** her fiyat `investment.market_quotes`'tan gelir ve arayüzde
paylaşılan SSE akışıyla tazelenir. Bir ekranın veriyi bir kez çekip bırakması,
yanındaki şeridin oynadığı bir tabloda donmuş fiyat demekti; hisse detay sayfası
ise `mockData.ts`'ten okuduğu için tıklanan satırla asla aynı fiyatı
göstermiyordu. `market_candles` ayrı bir seri (gecelik iş) — grafikler onu
okur, anlık fiyat asla oradan gelmez.

`ingestor` 30 saniyede bir, ~190 enstrümanı 40'lık parçalara bölerek çekiyor
ve backend'e HTTP ile yazıyor. Tek parça ve 10 saniyeydi; evren iki borsaya
çıkınca yetmedi. `yf.download` sembol başına hatayı YUTUYOR ve yine bir frame
döndürüyor, dolayısıyla zaman aşımları istisna olarak değil yalnızca geçen
süre olarak görünüyordu: ölçülen bir turda 61 saniye, 10 saniyelik bütçeye
karşı, ve arada her koşu "skipped" olarak loglanıyordu. Üç değişiklik:
istek başına gerçek bir timeout, parçalama, ve kısa dönen bir partiyi
(`MISSING_TOLERANCE`) yavaşlama sinyali sayıp mevcut backoff merdivenini
besleme.

Fiyat penceresi **beş gün**, iki değil. `period` takvim aralığıdır ve içine
kaç işlem günü düştüğü borsaya göre değişir: bir cumartesi ölçüldüğünde ABD
sembolleri iki bar, her `.IS` sembolü tek bar döndürdü. Tek barla önceki
kapanış yoktur, `change_percent` null kalır — ve izleme listesi, ısı haritası
ve hareketliler listesi değişimi bilinmeyen satırları düşürür. Gözlenen sonuç,
88 BIST hissesinin 87'sinin her hafta sonu bu ekranlardan sessizce
kaybolmasıydı. Yalnızca son iki bar okunur, geniş pencere bedava.

**Piyasa saatleri artık borsa başına.** `open_markets()` o an işlem gören
piyasalar kümesini döner (BIST 10-18, NASDAQ/NYSE 16-23, FX/COMEX 7/24) ve
yalnızca onların enstrümanları çekilir. Tek bir BIST kapısı vardı; ABD
hisseleri eklenince bu, saat 18:00'den sonra ABD fiyatlarının hiç
tazelenmemesi demekti — yani ABD seansının neredeyse tamamı. Tanımadığı bir
borsadaki enstrüman düşürülmez, çekilir: eksik bir `MARKET_HOURS` girdisi,
hiç fiyatlanmayan bir enstrümandan çok daha kolay fark edilir. Frontend `GET /api/market/stream` (SSE) üzerinden
dinliyor; `frontend/src/hooks/useMarketStream.ts` tüm uygulama için **tek**
`EventSource` tutuyor, akış kurulamazsa 10 saniyelik yoklamaya düşüyor.
Fiyata bağlı kolonları (pozisyon değeri, günlük/toplam getiri) yeniden hesaplama
işi `useLiveRows` içinde; yalnızca fiyatı tazeleyip yanındaki değeri dondurmak
satırı kendi içinde tutarsız bırakırdı.

## Veritabanını paylaşmak

Migration'lar şemayı ve enstrüman evrenini kurar ama **hiçbir migration
kullanıcı oluşturmaz**. Klonlayan bir ekip arkadaşı uygulamayı açar ve giriş
ekranını geçemez. Elle üretilen her şey — hesap, portföy, izleme listesi,
sohbet geçmişi — yalnızca kişinin kendi Docker volume'unda durur.

Bu yüzden `seeds/` commit'leniyor: **kullanıcı başına bir dosya**, adı TC
numarası. İki kişi kendi test kullanıcısını eklediğinde farklı dosyalara
dokunur, git içerikleri hiç karşılaştırmaz. Ekip arkadaşının yapması gereken
tek şey:

```
docker compose up --build
```

**Yükleme her açılışta** olur: `backend/docker-entrypoint.sh`, `alembic
upgrade head`'in hemen ardından `scripts/load_seeds.py`'yi çalıştırır. Sıra
tesadüf değil — seed'ler migration'ların kurduğu enstrümanlara referans verir,
dolayısıyla yükleme onlardan sonra ve onları uygulayan container'ın içinde
olmak zorunda. Ayrı bir compose servisi `base-db` sağlıklı olur olmaz
çalışıyordu, yani şema henüz yokken.

Her ifade `ON CONFLICT DO NOTHING`, ama asıl koruma o değil. Her dosyanın
başında `-- moneyfast:user id=... tc=...` satırı var ve **aynı TC farklı bir
id ile zaten kayıtlıysa dosya baştan sona atlanır**. `public.users`'ta `tc_no`
ve `email` üzerinde unique index var, yani kullanıcı satırı zaten
çoğaltılamaz; tehlike aşağıda: dosyadaki hesap, pozisyon ve mesajlar
*seed'in* user id'sini taşır ve modüller şemalar arası foreign key kurmaz
(bkz. "shared/ kuralı"), dolayısıyla hiçbir şey itiraz etmez. Satırlar
kimsenin olmayan bir id'ye bağlanır. Tehlike **kopya değil, yetim satır**.

Dışa aktarma **her commit'te** olur: `.githooks/pre-commit`. Klon başına bir
kez `cd backend && make hooks`. Git, bir klonun çalıştırılabilir hook
kurmasına bilerek izin vermez, o yüzden bu adım kaçınılmaz — ama export
başına değil, kişi başına bir kez. Backend ayakta değilse hook bir satır
yazıp çıkar: bir commit'in Docker'a bağımlı olması kabul edilemez.

Hook'un sadece **senin** verini taşıması ayrı bir kayıt tutmayı gerektirmiyor:
export deterministik olduğu için, yüklediğin ama dokunmadığın bir kullanıcı
birebir aynı baytlarla yeniden yazılır — diff yok, stage'lenecek şey yok.

**`product_id` asla olduğu gibi yazılmaz.** Enstrüman id'leri migration içinde
`gen_random_uuid()` ile üretiliyor, yani her makinede farklı — sabit bir id
taşıyan seed satırı başkasının veritabanında foreign key hatası verir. Bunun
yerine sembolden aranıyor:
`(SELECT id FROM investment.investment_products WHERE symbol = 'THYAO')`.

Çıktı **deterministik** olmak zorunda: her tablo açık `ORDER BY` ile okunur.
Sıralama sabit olmasaydı aynı veri her seferinde farklı satır sırasıyla
yazılır ve her export tam bir yeniden yazma gibi görünürdü — yani tam olarak
kullanıcı başına ayırmanın önlediği çakışma.

`market_quotes` dışa aktarılmaz: bir kotasyon ŞU ANA dair bir iddiadır ve
eski bir fiyatı güncelmiş gibi sunmak, yanlış bir fiyattan ayırt edilemez.
Mum, temel veri ve KAP bildirimi ise tarihsel kayıt ve eskimiyor —
`seeds/market/` altında commit'leniyorlar. Mumlar bir dönem `seeds/market/candles.sql` olarak commit'leniyordu —
7,5 MB — çünkü günlük barlar yalnızca 19:15 cron'uydu ve sabah açılan bir
klon akşama kadar boş grafik gösteriyordu. Artık ingestor açılışta
`GET /api/market/candles/coverage`'a sorup **yalnızca eksik olanı** çekiyor:
ilk açılışta evrenin tamamı (ölçülen: 187 sembol, 37.199 bar, 36 saniye),
yeniden başlatmada tek bir HTTP çağrısı. Bloklamaz — `fetch_candles` sembol
başına çalıştığı için tek seferlik bir scheduler job'ı olarak kuyruğa girer. `dumps/` ise gitignore'da — `make db-dump` tam bir yedek alır
(riskli bir işlemden önce) ve birine tam durumunu vermek için kullanılır.

### KAP — bildirimler

Haberin bir şirketi olmasını sağlayan kaynak. RSS beslemelerinin güvenilir
bir hisse etiketi yok (`_tickers` yalnızca besleme kategorilerini okuyabiliyor,
pratikte `related_symbols` boş geliyor); KAP bildiriminin ihraççısı makine
okunur bir alanda, kalıcı bağlantısıyla birlikte yazılı.

Kazıma değil: KAP bir JSON API sunuyor ve dürüst bir `User-Agent`'a
`Referer` olmadan, oturum ısıtması olmadan cevap veriyor — varsayılmadı,
ölçüldü (sahte referrer ile ve olmadan yanıtlar bayt bayt aynı).

| Uç | Ne verir |
|---|---|
| `POST /tr/api/disclosure/members/byCriteria` | Tarih aralığındaki bildirimler. **2000'de kesiyor**, sayfalama yok → pencere ikiye bölünüyor |
| `GET /tr/api/notification/attachment-detail/{index}` | Gövde (HTML listesi) + ek listesi |
| `GET /tr/api/file/download/{objId}` | Ek. **PDF değil**: serileştirilmiş Java bayt dizisi |

**Süzgeç izin listesi, `rss_source`'un tersi.** Orada kara liste doğru
(kaçırılan haber görünmez, araya karışan futbol haberi görünür); burada hedef
küme sayılabilir. `stockCodes` VE `relatedStocks` birlikte okunuyor:
ölçüldü, eşleşmelerin %37'si yalnızca ikincisi üzerinden geliyor — aracı
kurum kendi kodu altında başka bir şirket hakkında bildirim veriyor.

**Tekilleştirme anahtarı bildirim numarasından türetiliyor**
(`sha256("kap:{index}")`), metinden değil. Bunun asıl faydası şu: anahtar
LİSTELEME yanıtından hesaplanabiliyor, dolayısıyla `POST
/api/market/news/known-hashes` sayesinde hangi gövdenin çekilmeye değeceği,
tek bir gövde indirilmeden biliniyor. Altı aylık taramayı yeniden
başlatılabilir kılan şey bu.

**Sözleşmeye dokunulmadı.** `document_type = FILING` zaten dondurulmuş
`doc_types` enum'unda; `category = kap-disclosure` ve `source = KAP` iki
süzgeç daha veriyor, ikisi de `ALLOWED_FILTERS`'ta. Yeni MCP tool'u yok,
sürüm artışı yok.

**Ekler kırılgan yer.** Java zarfı çözüldükten sonra `%PDF-` DOĞRULANIYOR
(işaret baytları sınıf adının içinde de geçebiliyor) ve çözülemeyenler
sayılıyor — belgelenmemiş, sürümsüz bir uç. Ayrıca bazı PDF'ler `ToUnicode`
eşlemesi olmayan yazı tipleriyle üretilmiş ve `pypdf` bunlarda hata
VERMİYOR, makul görünen anlamsız metin döndürüyor; sembol karakteri
yoğunluğuyla eleniyor (bozuk 0,0617, okunabilenlerin hepsi ≤0,0001).

**Okunamayan pencere, boş pencereden ayrı.** Gerçek bir taramada ölçüldü:
aynı altı ay bir turda 28.508, kısıtlanmış bir turda 14.589 döndürdü ve
ikisi de aynı satırı logladı. Artık okunamayan pencereler sayılıyor ve
`windows_unread` olarak yüzeye çıkıyor.

`seeds/market/news.csv.gz` altı aylık **başlıkları** taşıyor (27.541 satır,
2,1 MB). Gövdeler ve ekler çalışma anında iniyor: panonun istediği tarihsel
bir kayıt, korpusun istediği okunacak metin, ve ikincisi git'te taşınacak
şey değil — vektörleriyle birlikte ~33 MB olurdu ve gzip blob'u
delta'lanmadığı için bu, her yeniden dışa aktarmada kalıcı geçmiş demek.

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

### Emir: onaylamak almak değil

Bir alım onaylandığı anda gerçekleşiyordu ve limit fiyat yalnızca bir
FİYATLAMA girdisiydi: `ai_service._estimate` limit fiyatı gördüğünde onu
referans fiyatın yerine koyuyordu, yani "290'a düşünce al" diyen bir emir,
piyasa 305'ken bile 290'dan doluyordu.

Artık onay emri **yerleştiriyor**:

```
PENDING_USER_CONFIRMATION --onay--> WAITING_PRICE --eşleşme--> CONFIRMED
                                          |
                                          +--iptal--> CANCELLED (iade)
```

Piyasa emrinin bekleyecek bir şeyi yok; fiyat zaten oluşmuş, blokajın hemen
ardından gerçekleşiyor. Limit emri (`order_type` `LIMIT`/`STOP_LIMIT` ve
migration 0040'ta indekslenmiş bir `limit_price`) `WAITING_PRICE`ta bekliyor
ve `matching.py` her dakika tarıyor: ALIŞ için `piyasa <= limit`, SATIŞ için
`piyasa >= limit`. **Dolum limit fiyattan değil, eşleşmeyi sağlayan piyasa
fiyatından** — öneri limitten maliyetlendirildiği için alışta aradaki fark
iade ediliyor; kur ise öneride DONMUŞ olanla kalıyor.

Hisse `market_quotes`tan fiyatlanıyor ve bayat kotasyon ya da kapalı borsa
eşleşmeyi reddediyor: kapalı bir piyasada "fiyat geldi" demek, olmamış bir
işlemi uydurmak olurdu. Fon `market.funds` NAV'ından ve tabiatı gereği
günde bir ilerliyor.

Durum **veritabanında**, bir arka plan görevinin belleğinde değil. Eskiden
onaydan sonra `asyncio.sleep(15)` bekleyen bir görev vardı (docstring'i "3
dakika" diyordu); süreç o aralıkta ölürse satır `PENDING`, para bloke ve onu
bitirecek ya da geri alacak hiçbir şey kalmıyordu. `sweep_stale_pending` o
yoldan kalmış satırların blokajını çözüyor.

`GET /api/investment/orders` bir dönem **kimlik doğrulaması istemiyordu ve
kullanıcıya göre süzülmüyordu**: token'sız bir istek son yirmi emri —
herkesinkini, sembol, adet ve durumuyla — döndürüyordu. Canlı doğrulandı ve
kapatıldı; `recent_orders`ın `user_id` parametresinin varsayılanı yok.

**Bir uç, adının söylediği şeyi döndürmeyebilir.** `fonProfilDtyGetir`
fonun profilini değil, karşılaştırma grafiğinin gösterge listesini
döndürüyor ve yanıt HER FON İÇİN AYNI. İlk satırın `fonTuru` alanı şemsiye
türü sanıldı: 1.054 aktif fonun 1.021'i "ALTIN" şemsiyesine yazıldı ve
hepsine aynı kategori getirisi kondu. Şemsiye eşlemesi artık `fonTurGetir` +
`sfonTurKod` ile süzülmüş anlık görüntüden geliyor (fon başına değil,
şemsiye başına bir istek) ve `category_return` sütunu düştü — doğru kaynağı
yok (migration 0041, `docs/TEFAS_INTEGRATION.md`).

**Emir yolu baktığın yerde.** Alım-satım tek bir yerde — Portföy
ekranındaki hızlı emir kutusunda — duruyordu; bir hisseyi ya da fonu
inceleyen kullanıcının onu alması için önce başka bir ekrana gitmesi
gerekiyordu. Hisse ve fon detay sayfalarının ikisinde de "Al / Sat" düğmesi
var ve aynı `TradeModal`'ı açıyor: emir yolu tek.

`MarketInstrument` artık ISO para birimini de taşıyor. Yalnızca gösterim
işareti (`unit`: ₺/$/€) taşınıyordu ve `TradeModal` varsayılanına düşüyordu,
yani bir dolar hissesi liraya fiyatlanıyordu — "bir fiyat, para birimi
olmadan taşınmaz" kuralının aynısı.

**Bloke tutar GÖRÜNÜR.** GTC bir emir parayı süresiz tutabiliyor; bakiyede
eksilen ama nedeni hiçbir yerde yazmayan bir tutar kullanıcıya bir hata gibi
görünüyor. `/portfolio/summary` `blockedTRY` döndürüyor ve bakiye
bileşeninde yazıyor. Toplama EKLENMİYOR: o para bakiyeden zaten düşüldü,
eklemek iki kez saymak olurdu.

**Sembol, günlük dildeki kelimeyi yener.** `resolve_candidates` bir dönem
takma ad tablosuna (`altın` → XAUUSD) ÖNCE bakıyordu. Fon evreni
köprülenmeye başlayınca bu ölçülebilir bir hataya dönüştü: `ons` tabloda
XAUUSD'ye bağlıydı ama ONS gerçek bir TEFAS fon kodu, dolayısıyla "ONS al"
diyen biri **altın alıyordu**. Artık tam sembol eşleşmesi önce bakılıyor —
sembol kayıtlı bir gerçek, takma ad ise niyet tahmini — ve yalın `ons`
tablodan çıkarıldı; altını isteyen "altın", "ons altın", "gold" ya da "xau"
yazıyor.

**Fonlar ilk emirde köprüleniyor.** `market.funds` ile
`investment.investment_products` iki ayrı evren ve emir/pozisyon/risk
yollarının hepsi ikincisinden geçiyor. 2.602 fonu toptan yazmak Piyasalar
ekranını doldururdu, bu yüzden `funds.ensure_tradable` yalnızca işlem gören
fonu yazıyor: `product_type='fund'`, `data_symbol=NULL` (yfinance onu
fiyatlamasın), fiyat `sync_quotes` ile `market_quotes`a yansıtılıyor.

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

### Para birimi kuralı

**Bir fiyat, para birimi olmadan taşınmaz.** Enstrümanın para birimi
(`investment_products.currency_code`) `Position`, `WatchlistItem`,
`TopMoverItem`, `DividendItem`, `HeatmapItem`, `Order`, `MarketTicker` ve
`CandleSeriesOut` yanıtlarının hepsinde yer alıyor. Bir dönem düşürülüyordu ve
arayüzün tahmin etmekten başka seçeneği yoktu: AAPL'in 314,88 USD'lik fiyatı
gösterge panelinde "₺314,88" olarak görünüyordu.

**Farklı para birimleri toplanmadan önce çevrilir.** `ai_service.holding_value`
tek uygulama; `/portfolio/summary`, `/asset-allocation`, `/sector-allocation`,
`/heatmap` ve `analytics/service.build` hepsi onu kullanıyor. Çevirmeden
toplamak, Analiz sayfasının portföyü 404.467 TL, özet kartının aynı portföyü
1.087.834 TL göstermesine yol açıyordu. Kuru olmayan pozisyon toplama
katılmaz ve adı uyarıda geçer — 1.0 varsaymaz.

Arayüzde tek biçimlendirici var: `frontend/src/lib/money.ts`. Yedi ayrı
TRY'ye sabitlenmiş `formatCurrency` kopyasının yerini aldı. Yabancı bir fiyat
`314,88 $ · ≈₺15.097,83` biçiminde, kendi para birimi ve yaklaşık TL karşılığı
ile gösteriliyor.

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