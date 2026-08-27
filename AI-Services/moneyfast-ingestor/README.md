# MoneyFast ingestor

Collects live market prices, daily price history, Turkish financial news, and
optionally an explicit allowlist of public X accounts. It pushes normalized
data to the services that own it.

```
ingestor ──yfinance──► quotes + daily candles ──POST──► backend /api/market/ingest
         ──RSS feeds──► news ─────────────────┬───────► backend /api/market/news/ingest
                                              └───────► rag     /ingest
         ──X API v2───► public social posts ──────────► backend /api/market/social/ingest
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
| Official X API v2 | Selected public-account posts and URL entities | bearer token |

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
* **X posts** are upserted by the stable platform post ID. A file-backed
  `since_id` cursor reduces requests. It advances only after pagination reaches
  the end of the account backlog and every backend chunk for that account is
  accepted. A failed later page or backend chunk leaves the previous cursor in
  place, so the next cycle replays an overlap; Core DB uniqueness makes that
  replay idempotent. If `X_MAX_PAGES_PER_ACCOUNT` is reached with more pages,
  the delivered segment's pagination token and high-water mark are checkpointed
  while `since_id` stays unchanged. Later cycles resume that backlog and promote
  the high-water mark only after its final page is delivered.

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

The X bearer token is ingestor-only. `X_BEARER_TOKEN_FILE` takes precedence
and is the production path; `X_BEARER_TOKEN` is a local development fallback.
Neither value is sent to the backend or written to logs.

X collection is disabled by default. A configuration example (the handles are
examples, not a production list) is:

```dotenv
X_INGEST_ENABLED=true
X_MONITORED_ACCOUNTS_JSON=[{"handle":"example_account","source_type":"financial_media","trust_score":0.75},{"handle":"kap_bildirimleri","source_type":"disclosure_aggregator","trust_score":0.85}]
X_INCLUDE_REPLIES=false
X_INCLUDE_REPOSTS=false
X_POLL_INTERVAL_MINUTES=10
X_MAX_PAGES_PER_ACCOUNT=3
X_BACKEND_BATCH_SIZE=500
X_IDENTITY_REFRESH_HOURS=24
```

The configured handle is a bootstrap locator. After first resolution the state
file pins that entry to X's stable numeric user ID. Identity refreshes query by
that ID, not by the old handle, so a renamed account follows its original
identity and a reassigned handle cannot silently switch the monitored account.
Changing the configured handle creates a new explicit bootstrap decision.

Backend delivery is account-isolated and uses at most
`X_BACKEND_BATCH_SIZE` posts per atomic request (default 500, hard maximum
1,000). The account record is included in every request. A failed chunk blocks
only that account's checkpoint; independently completed accounts can advance.

An X 429 writes a UTC `blocked_until` value to the same atomic state file.
Cycles inside that window make no X request and do not sleep in the scheduler
thread. Provider delays are bounded to 60 seconds through 6 hours; malformed
headers fall back to the configured polling interval.

Only API-provided expanded/unwound URLs are examined. A KAP provenance link
must be HTTPS and have the exact host `kap.org.tr` or `www.kap.org.tr`; the
ingestor never follows redirects or fetches the KAP page. A valid link does
not verify the post or turn an aggregator into an official disclosure source.

The backend stores these records in dedicated `market.social_*` tables. The
read-only `GET /api/market/social-signals` route is public for the same reason
as existing price and news reads: the data is non-user-specific market data.
It always returns source type, trust score, and verification status, and never
returns raw metadata. `unverified` remains the default even for an official
account or a post containing a valid KAP link.

Instrument relations are reconciled snapshots of the latest accepted
`instrument_references`. An empty list is authoritative and clears every
existing link for that post. When every supplied reference resolves uniquely,
newly matched products are added and genuinely stale links are removed. If any
supplied reference is unknown or ambiguous, reconciliation is not authoritative:
resolved products are still added, but existing links are preserved because a
temporary resolver miss is not proof that a prior valid relation disappeared.
Ambiguous symbols are never guessed; unresolved evidence is returned in the
ingest response. The current timeline endpoint does not reliably enumerate
deleted posts, so `is_tombstoned` is storage/API support for a future explicit
deletion workflow; Phase 1 does not populate tombstones automatically.

Ingestor cycle status distinguishes delivery outcomes explicitly:
`delivery_attempted`, `delivery_complete`, and `delivery_partial`. Compatibility
field `backend_written` is true only when delivery was attempted and every
account chunk succeeded — never when zero backend requests occurred. Provider
posts rejected during local normalization (malformed id/timestamp, filtered
reply/repost, invalid shape) are counted in `normalization_rejections`; a fully
completed provider page may still advance its cursor so malformed records do not
retry forever, but the rejection remains visible in status aggregates.

The runtime entrypoint repairs ownership only on `/app/state`, then executes the
application as UID 10004. A container smoke check can verify both privilege
drop and atomic replacement without touching an existing volume:

```bash
docker run --rm --mount type=volume,dst=/app/state moneyfast-ingestor:smoke \
  python -c "from ingestor.sources.x_source import save_state,load_state; import os; assert os.getuid()==10004; assert save_state({'smoke':{'user_id':'1'}}); assert load_state()['smoke']['user_id']=='1'"
```

Alembic is the runtime schema source of truth. `infra/intertech.sql` remains a
stale reference snapshot and is intentionally not updated by this phase.

## Running

```bash
# One-shot, against a running stack
docker compose exec ingestor python -m ingestor.run --once

# Just one job
docker compose exec ingestor python -m ingestor.run --once --news
```

Without `--once` it starts the scheduler: quotes every 30 seconds for whichever
configured markets are open, news every 15 minutes, candles daily at 19:15,
and X at its configured interval when enabled. X is independent and does not
run during the warm start; a missing token, rate limit, or outage cannot stop
RSS or market jobs. Quotes and news still run immediately on boot.

```bash
make install install-test
make test          # 100% coverage gate; no network, no database
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
