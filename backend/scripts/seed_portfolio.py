"""Backfill the demo portfolio's cost basis from real historical closes.

Migration 0006 seeds the holdings with `average_buy_price = 0`, because the
candles it needs are ingested rather than shipped. This script fills them in
once the ingestor has run.

Why a real historical close rather than an invented number: the old fixtures
carried hand-written cost bases that predated a stock split, so the dashboard
showed FROTO at −92% and THYAO at +8% side by side. Deriving the cost from the
actual close six months ago makes the P&L arithmetic real — the gains and
losses are whatever the market actually did over that window.

Idempotent: a holding whose cost basis is already set is left alone, so
re-running after a new ingest does not silently re-price someone's book.

    python -m scripts.seed_portfolio              # fill missing cost bases
    python -m scripts.seed_portfolio --months 12  # use a different entry point
    python -m scripts.seed_portfolio --force      # re-price everything
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("moneyfast.seed_portfolio")

DEFAULT_MONTHS = 6

#: A position priced from a bar this far from the target date is reported
#: rather than silently accepted; it usually means the instrument only listed
#: recently and the "six months ago" entry point is fiction.
MAX_DRIFT_DAYS = 21


def _close_near(bars: list[tuple[datetime, float]], target: datetime):
    """The bar closest to `target`, with how far off it is."""
    if not bars:
        return None, None
    best = min(bars, key=lambda row: abs((row[0] - target).total_seconds()))
    drift = abs((best[0] - target).days)
    return best[1], drift


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed portfolio cost bases")
    parser.add_argument("--months", type=int, default=DEFAULT_MONTHS,
                        help="how far back the notional entry point is")
    parser.add_argument("--force", action="store_true",
                        help="re-price holdings that already have a cost basis")
    parser.add_argument("--account", default="TR-DEMO-0001")
    args = parser.parse_args(argv)

    from app.core.database import SessionLocal
    from app.modules.investment import market_service
    from app.modules.investment.models import InvestmentProduct, PortfolioPosition

    target = datetime.now(timezone.utc) - timedelta(days=args.months * 30)
    db = SessionLocal()
    try:
        account = market_service.account(db, args.account)
        if account is None:
            log.error("no account %s; has migration 0006 run?", args.account)
            return 2

        positions = (
            db.query(PortfolioPosition, InvestmentProduct)
            .join(InvestmentProduct, InvestmentProduct.id == PortfolioPosition.product_id)
            .filter(PortfolioPosition.investment_account_id == account.id)
            .all()
        )
        if not positions:
            log.error("account %s holds nothing", args.account)
            return 2

        priced = skipped = missing = 0
        for position, product in positions:
            if float(position.average_buy_price) > 0 and not args.force:
                skipped += 1
                continue

            bars = market_service.candle_closes(db, product.symbol, limit=500)
            close, drift = _close_near(bars, target)
            if close is None:
                # Left at zero rather than guessed. A fabricated cost basis
                # produces a fabricated P&L, which is worse than an obviously
                # unset one.
                log.warning("%s: no price history yet, cost basis left unset", product.symbol)
                missing += 1
                continue

            if drift and drift > MAX_DRIFT_DAYS:
                log.warning(
                    "%s: nearest bar is %d days from the target date; the instrument "
                    "probably listed recently", product.symbol, drift,
                )

            position.average_buy_price = round(close, 4)
            position.opened_at = target
            priced += 1
            log.info("%-8s %8.2f  (%d months ago)", product.symbol, close, args.months)

        db.commit()
        log.info("priced %d, skipped %d already set, %d without history",
                 priced, skipped, missing)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
