"""TEFAS NAV geri doldurma -- tek seferlik, parça parça, kaldığı yerden.

`run_tefas` günlük tur için doğru ama geri doldurma için değil: bütün
fonların serisini bellekte biriktirip EN SONDA tek seferde yazıyor. 2.602
fon x ~252 satır = 656 bin satır demek, ve ölçüldü -- on üç dakika sonra
süreç öldüğünde veritabanına HİÇBİR ŞEY yazılmamıştı. Bir saatlerce süren
işin tamamı, sonundaki tek yazmaya bağlı olamaz.

Buradaki fark üç madde:

* **Parça parça yazıyor.** Her `CHUNK` fondan sonra backend'e gidiyor,
  dolayısıyla süreç ölse bile o ana kadarki iş duruyor.
* **Kaldığı yerden devam ediyor.** Her turda `funds/meta/coverage`
  okunuyor ve yalnızca EKSİK olanlar isteniyor; ikinci kez çalıştırmak
  baştan başlamak değil.
* **İlerlemeyi yazıyor.** Saatlerce süren bir işin sessiz kalması, çalışıp
  çalışmadığını ancak veritabanına bakarak anlamak demek.
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

import httpx

from . import config, sinks
from .sources import tefas_source

log = logging.getLogger("moneyfast.ingestor.backfill")

#: Kaç fonun serisi bir arada yazılır. Küçük tutuluyor: bir parça
#: kaybedildiğinde kaybedilen iş de küçük olsun.
CHUNK = 25


def backfill(client: httpx.Client, limit: Optional[int] = None) -> dict:
    """Serisi olmayan fonların NAV geçmişini indirir.

    `limit` verilirse yalnızca o kadar fon işlenir -- testte ve elle bir
    deneme turunda saatlerce beklememek için.
    """
    coverage = sinks.fetch_fund_coverage(client)
    # Serisi olmayanlar ÖNCE; ardından serisi olup kategori sırası boş
    # kalanlar. İkincisi ölçüler eklenmeden önce çekilmiş fonlar -- aynı
    # çağrı ikisini birden veriyor, dolayısıyla ayrı bir yol gerekmiyor.
    missing = list(coverage.get("missing_prices") or [])
    seen = set(missing)
    missing += [
        code for code in (coverage.get("missing_category") or []) if code not in seen
    ]
    if limit is not None:
        missing = missing[:limit]
    if not missing:
        log.info("backfill: nothing missing")
        return {"funds": 0, "rows": 0}

    total_rows = 0
    done = 0
    with httpx.Client(
        follow_redirects=True, headers={"User-Agent": config.user_agent()}
    ) as tefas:
        for start in range(0, len(missing), CHUNK):
            batch = missing[start:start + CHUNK]
            rows: list[dict] = []
            metrics: list[dict] = []
            for code in batch:
                series, category = tefas_source.fetch_prices(code, tefas)
                rows.extend(series)
                # Kategori sırası AYNI yanıtta geliyor; ayrıca istemek 2.602
                # isteği ikinci kez yapmak olurdu.
                if category is not None:
                    metrics.append(category)
            done += len(batch)
            if rows or metrics:
                written = sinks.push_funds_to_backend(client, metrics, rows)
                total_rows += written["prices_written"]
            # Her parçadan sonra: saatlerce süren bir iş sessiz kalmamalı.
            log.info(
                "backfill: %d/%d fon, %d satır yazıldı",
                done, len(missing), total_rows,
            )
    return {"funds": done, "rows": total_rows}


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
    )
    args = list(sys.argv[1:] if argv is None else argv)
    limit = int(args[0]) if args else None
    with httpx.Client() as client:
        result = backfill(client, limit=limit)
    log.info("backfill bitti: %s", result)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
