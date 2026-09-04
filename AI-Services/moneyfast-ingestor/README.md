# MoneyFast ingestor

Collects live market prices, daily price history, and Turkish financial news,
then pushes all of it to the services that own the data.

```
ingestor ──yfinance──► quotes + daily candles ──POST──► backend /api/market/ingest
         ──RSS feeds──► news ─────────────────┬───────► backend /api/market/news/ingest
         ──KAP────────► disclosures ──────────┘   └───► rag     /ingest
```

(Disclosure bodies reach the corpus too; the listing pass shown here writes
only the headline, issuer and permalink.)

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
| KAP | BIST company disclosures, with issuer, timestamp and permalink | no |

**KAP fits the stance above rather than stretching it.** It is Turkey's
*mandatory* public disclosure platform — the content exists specifically so it
can be read — and it fronts a JSON API that answers our honest `User-Agent`
with no `Referer`, no session warm-up and no challenge. That last part was
measured on 2026-09-01 rather than assumed: responses are byte-identical with
and without a spoofed referrer, so we send none. Third-party notes on this API
recommend both; we do not need either, and would have picked a different
source if we had.

KAP serves no `robots.txt` (the apex 404s, `www` answers with a non-200
oddity), which the courtesy layer reads as permission — the same convention
it applies to any host without one, and the same one RFC 9309 states.

**Only disclosures naming an instrument we carry are kept.** That is an
allowlist, deliberately the opposite of the RSS section filter, because here
the target set is enumerable: a disclosure that names no symbol in
`investment_products` has nowhere in this product to appear. Measured over one
week, 592 of 1.101 disclosures matched — and 218 of those matched *only*
through `relatedStocks`, where a broker files a notice about a company other
than itself. Reading the filer's own code alone would silently lose a third of
the coverage.

BIST tickers reach yfinance as `<SYMBOL>.IS`. The mapping from our symbols
(`TEST-THYAO`) to the provider's (`THYAO.IS`) lives in
`investment.investment_products` and is fetched from the backend at run time —
adding an instrument is a database row, not a redeploy of this service.

**Price history is what makes real risk metrics possible.** Volatility,
drawdown, VaR, beta and Sharpe have nothing to compute from without OHLCV
bars; the nightly candle job is what fills that gap.

## KAP attachments, and why they are the fragile part

A financial report's substance is in its attached PDF, not its disclosure
body, so attachments are downloaded and read. Two things about that endpoint
are worth knowing before touching it.

**The response is not a PDF, whatever the header says.** `Content-Type` is
`application/pdf` and the body is a serialized Java byte array:
`ac ed 00 05 ... 78 70 <4-byte big-endian length> %PDF-1.4`. The unwrap
looks for the marker, reads the length, slices — and then **checks for
`%PDF-`**, because `78 70` can also occur inside a class descriptor, so the
first match is not guaranteed to be the right one. A wrong offset becomes
`None` rather than garbage in the corpus, and unwrap failures are counted:
this is an undocumented, unversioned interface, and the counter is the only
way its breaking becomes visible.

**Some PDFs cannot be read at all, and `pypdf` will not say so.** They embed
subset fonts with no `ToUnicode` map, and extraction returns plausible-looking
nonsense — `§işlıııııi*ı, §ıın,'I'iı:.,,l.Ş.` — rather than raising. Text like
that in a shared corpus is worse than no text: it is searchable garbage, and
it competes for the retrieval slots of the company it is filed under.

The discriminator is the density of symbol characters that ordinary Turkish
prose never contains. Measured across six attachments: a mangled one scored
**0.0617**, and every readable one scored **0.0000–0.0001** — including
numeric price bulletins, which a word-frequency test would have thrown away
(they scored as low as 0.0056 on that measure, against 0.0025 for the mangled
text — far too close to separate on). The threshold sits at 0.01, two orders
of magnitude clear of both ends.

Attachments are read only for disclosures inside `INGESTOR_KAP_PDF_WINDOW_DAYS`
(30). Each one is a second request on top of the body; opening the window
across a six-month backfill would spend a third of its wall clock on old
filings nobody will ask about.

## Idempotency

Every job can be run twice with no second effect, which is what makes a missed
cycle self-healing instead of something to reconcile by hand:

* **Quotes** append. A price at a point in time is a fact, not a correction.
* **Candles** hit `UNIQUE(product_id, interval, timestamp)` and are discarded
  if already held, so re-requesting a year of history every night is free.
* **News** is deduplicated on a SHA-256 of the article text — not the URL,
  because the same wire story is republished under different links and some
  feeds renumber their URLs on every rebuild.
* **Disclosures** are deduplicated on a SHA-256 of KAP's own `disclosureIndex`,
  because unlike a wire story a filing *has* a stable identifier. Two
  consequences: re-offering a stored disclosure writes nothing, and the key is
  computable from a listing alone — so a backfill can ask what is already held
  before spending a request on each body. An amendment is filed under its own
  index and therefore stored as its own row; collapsing it into the original
  would be rewriting a filings archive.

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
