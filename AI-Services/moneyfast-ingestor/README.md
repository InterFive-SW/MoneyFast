# MoneyFast ingestor

Collects live market prices, daily price history, and Turkish financial news,
then pushes all of it to the services that own the data.

```
ingestor ──yfinance──► quotes + daily candles ──POST──► backend /api/market/ingest
         ──RSS feeds──► news ─────────────────┬───────► backend /api/market/news/ingest
                                              └───────► rag     /ingest
```

## What it does not do

**No bot-detection evasion.** No CAPTCHA solving, no browser-fingerprint
spoofing, no proxy rotation, no ignoring `robots.txt`. The `User-Agent` names
the project and links to it, so an operator who wants us gone can see who we
are and say so.

This is a deliberate decision, not an oversight, and the reasons are practical
before they are ethical:

* Evasion stacks break without warning. You would be debugging one during a
  demo, not shipping features.
* This is a bank-sponsored internship project. A scraper that defeats access
  controls is a liability nobody wants to explain.
* **It is not necessary.** Everything this project needs is already published
  for machine consumption. RSS exists to be read by programs. yfinance serves
  BIST tickers without a key. The sites that put up bot walls — Investing.com,
  Bigpara — are precisely the ones with legitimate substitutes.

If some datum turns out to be reachable *only* by evasion, the right move is
to say so and pick a different source, not to route around the block.

## Courtesies

Being allowed to fetch something is not the same as being a good citizen of
someone else's server:

* `robots.txt` is fetched once per host, cached, and honoured.
* Requests to one host are spaced by `INGESTOR_HOST_DELAY_SECONDS` (2s).
* `ETag` / `Last-Modified` are echoed, so an unchanged feed costs the
  publisher a 304 instead of a full response body.
* A 429 backs off until the next cycle rather than retrying into the wall.

## Sources

| Source | What | Key needed |
|---|---|---|
| yfinance | Prices, previous close, daily OHLCV | no |
| Turkish financial RSS | Headlines, summaries, publication dates | no |

BIST tickers reach yfinance as `<SYMBOL>.IS`. The mapping from our symbols
(`TEST-THYAO`) to the provider's (`THYAO.IS`) lives in
`investment.investment_products` and is fetched from the backend at run time —
adding an instrument is a database row, not a redeploy of this service.

**Price history is what makes real risk metrics possible.** Volatility,
drawdown, VaR, beta and Sharpe have nothing to compute from without OHLCV
bars; the nightly candle job is what fills that gap.

## Idempotency

Every job can be run twice with no second effect, which is what makes a missed
cycle self-healing instead of something to reconcile by hand:

* **Quotes** append. A price at a point in time is a fact, not a correction.
* **Candles** hit `UNIQUE(product_id, interval, timestamp)` and are discarded
  if already held, so re-requesting a year of history every night is free.
* **News** is deduplicated on a SHA-256 of the article text — not the URL,
  because the same wire story is republished under different links and some
  feeds renumber their URLs on every rebuild.

## Isolation

This service holds **no database credential**. It is the only component that
reaches the internet for data, and it is deliberately kept away from the
application databases: it joins `moneyfast-net` (to reach `backend` and `rag`)
and `data-egress` (to reach the outside), and neither `base-db-net` nor
`vector-db-net`.

Writes are authenticated with `BACKEND_API_KEY`. When that variable is unset
the backend's ingest endpoints **refuse** rather than accepting anonymous
writes — a write endpoint that silently became public because an env var was
missing is exactly the failure nobody notices.

## Running

```bash
# One-shot, against a running stack
docker compose exec ingestor python -m ingestor.run --once

# Just one job
docker compose exec ingestor python -m ingestor.run --once --news
```

Without `--once` it starts the scheduler: quotes every 15 minutes during BIST
hours (10:00–18:00 Europe/Istanbul, weekdays), news every 15 minutes, candles
daily at 19:15. It also runs quotes and news immediately on boot, so a cold
start does not show an empty dashboard for fifteen minutes.

```bash
make install install-test
make test          # 90% coverage gate; no network, no database
```

The suite blocks real sockets. A test that forgets a stub would otherwise hit
a live news site — slow, flaky, and rude.


## Haber kaynakları ve neden bunlar

Beslemeler **finans bölümü** olanlardan seçildi. `dunya.com/rss?dunya` ve
`ekonomim.com/rss` site geneli akışlar: ekonomi haberlerinin yanında futbol
transferi, YÖKDİL sonucu ve deprem bülteni de taşıyorlar. Bu sitelerin
bölüm bazlı görünen adresleri (`?finans`, `?borsa`) sunucu tarafından yok
sayılıyor — üçü de aynı ana sayfa akışını döndürüyor.

Bu yüzden iki katman var:

1. `patronlardunyasi.com/rss/{borsa,finans,sirketler,ekonomi}` ve AA'nın
   `cat=ekonomi` akışı — hepsi finans, ek süzgeç gerekmiyor. `sirketler`
   özellikle önemli: şirket bazlı haber ("Akbank ile ilgili haberler")
   yalnızca oradan geliyor.
2. Karışık akışlar için `rss_source.is_financial`: haberin bölümü **URL
   yolundan** okunuyor (`/ekonomi/`, `/spor/`). Bu, yayıncının kendi
   sınıflandırması — başlığa bakıp tahmin yürütmek değil.

Süzgeç bir **denylist**: bölümü tanınmayan haber TUTULUR. Allowlist olsaydı,
finans haberini beklenmedik bir bölüm adı altında yayınlayan bir kaynağı
sessizce kaybederdik ve eksik bir haber, fazladan bir futbol başlığının aksine
görünmez olurdu.

BloombergHT denendi ve **çıkarıldı**: içeriği finansal ama akışı donmuş
durumda (en yeni haberi iki hafta öncesine aitti). Canlı fiyatların yanında
duran bayat bir kaynak, bir eksik kaynaktan daha kötü.
