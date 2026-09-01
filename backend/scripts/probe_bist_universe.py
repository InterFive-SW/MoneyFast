"""Hangi BIST şirketleri evrenimizde eksik, ve hangileri fiyatlanabiliyor.

**Elle çalıştırılır, açılışta DEĞİL.** Çıktısı bir migration'a yapıştırılmak
üzere basılır. 0006, 0010 ve 0023'ün hepsi aynı kuralı izliyor: listeler elle
yazılır ve tarihlenir, çünkü altından sessizce değişen bir tohum, diff'te
okunabilenden kötüdür. Bir migration'ın ağa çıkması, aynı şemanın iki makinede
farklı çıkması demek olurdu.

Dört adım:

1. **Kadro KAP'tan.** Bildirim listelemesi, bir pencerede bildirim vermiş her
   ihraççı kodunu veriyor. Ayrı bir üye listesi ucundan iyi: altı ayda hiçbir
   şey bildirmemiş bir şirketin gösterecek şeyi de yok, ve kadro böylece
   gerçekten bildirim iliştirebileceğimiz kümeyle tutarlı kalıyor.
2. **Elimizdekiyle farkı al.**
3. **Eksik olanları fiyat için yeniden sor.** 0023'ün kuralı birebir:
   sağlayıcının fiyatlayamadığı bir enstrüman TOHUMLANMAZ. Fiyatlanamayan bir
   adı tohumlamak, olmayan bir enstrümanı varmış gibi göstermek olur -- ve o
   ad ısı haritasında, aramada ve ekranlarda boş fiyatla görünür.
4. **Adı da yaz.** 0023 `name = symbol` yazmıştı çünkü sağlayıcı `.IS`
   sembolleri için şirket adı uçlarını 401'liyor. KAP adı bedavaya veriyor.

Kullanım:

    docker compose exec ingestor python3 - < backend/scripts/probe_bist_universe.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import date, timedelta

import httpx

KAP = os.getenv("INGESTOR_KAP_BASE_URL", "https://www.kap.org.tr")
BACKEND = os.getenv("BACKEND_API_BASE_URL", "http://backend:8000/api")
UA = os.getenv(
    "INGESTOR_USER_AGENT",
    "MoneyFastBot/1.0 (+https://github.com/InterFive-SW/moneyfast; internship project)",
)
WINDOW_DAYS = 3
LOOKBACK_DAYS = int(os.getenv("PROBE_LOOKBACK_DAYS", "183"))
CODE = re.compile(r"^[A-Z0-9]{2,6}$")


def roster(client: httpx.Client) -> dict[str, str]:
    """Every issuer code KAP has seen, mapped to its registered title."""
    names: dict[str, str] = {}
    until = date.today()
    floor = until - timedelta(days=LOOKBACK_DAYS)
    while until >= floor:
        since = max(floor, until - timedelta(days=WINDOW_DAYS - 1))
        rows = []
        for attempt in range(3):
            try:
                response = client.post(
                    f"{KAP}/tr/api/disclosure/members/byCriteria",
                    json={
                        "fromDate": since.isoformat(),
                        "toDate": until.isoformat(),
                        "mkkMemberOidList": [],
                        "subjectList": [],
                    },
                    headers={"User-Agent": UA},
                    timeout=30,
                )
                response.raise_for_status()
                rows = response.json()
                break
            except Exception as exc:  # noqa: BLE001
                # Bir pencerenin düşmesi, saatlerce süren bir taramayı
                # kaybetmeye değmez. Kadro zaten yaklaşık bir küme: aynı
                # ihraççı altı ayda birçok kez bildirim veriyor.
                print(f"  {since}..{until} attempt {attempt + 1}: {exc}", file=sys.stderr)
                time.sleep(5 * (attempt + 1))
        for row in rows:
            title = (row.get("kapTitle") or "").strip()
            for field in ("stockCodes", "relatedStocks"):
                for token in (row.get(field) or "").replace(";", ",").split(","):
                    token = token.strip().upper()
                    if CODE.match(token):
                        # Only the filer's own codes get the filer's name.
                        names.setdefault(token, title if field == "stockCodes" else "")
        until = since - timedelta(days=1)
        time.sleep(2)  # the same per-host courtesy the ingestor observes
    return names


def held(client: httpx.Client) -> set[str]:
    response = client.get(f"{BACKEND}/investment/products", timeout=60)
    response.raise_for_status()
    return {p["symbol"] for p in response.json() if p.get("market") == "BIST"}


def priced(symbols: list[str]) -> dict[str, float]:
    """Which of these does the price provider actually quote?"""
    import yfinance as yf

    out: dict[str, float] = {}
    for start in range(0, len(symbols), 40):
        batch = symbols[start:start + 40]
        frame = yf.download(
            [f"{s}.IS" for s in batch],
            period="5d", interval="1d", progress=False,
            group_by="ticker", threads=True, timeout=30,
        )
        for symbol in batch:
            try:
                series = frame[f"{symbol}.IS"]["Close"].dropna()
            except Exception:  # noqa: BLE001
                continue
            if len(series):
                out[symbol] = float(series.iloc[-1])
    return out


def main() -> int:
    with httpx.Client(follow_redirects=True) as client:
        names = roster(client)
        ours = held(client)

    missing = sorted(set(names) - ours)
    print(f"KAP roster: {len(names)} codes over {LOOKBACK_DAYS} days", file=sys.stderr)
    print(f"already held: {len(ours)} | missing: {len(missing)}", file=sys.stderr)

    quotes = priced(missing)
    seedable = sorted(quotes)
    print(
        f"of {len(missing)} missing, {len(seedable)} return a price and "
        f"{len(missing) - len(seedable)} do not",
        file=sys.stderr,
    )

    print(json.dumps(
        {
            "generated": date.today().isoformat(),
            "seedable": [[s, names.get(s) or s] for s in seedable],
            "unpriceable": [s for s in missing if s not in quotes],
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
