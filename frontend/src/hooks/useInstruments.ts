/**
 * The live instrument universe, shaped for the markets screens.
 *
 * The markets pages were written against `data/mockData.ts`, whose
 * `MarketInstrument` differs from the API's row in naming (`changePercent` vs
 * `change_percent`), in nullability (every fundamental is optional upstream,
 * because provider coverage is partial) and in vocabulary (`market` is
 * "NASDAQ"/"NYSE" upstream, but the table's tabs say "ABD").
 *
 * Adapting here rather than rewriting seven screens keeps one translation
 * point. What it will NOT do is invent values: a fundamental the provider does
 * not publish stays undefined, so the table renders "—" instead of a zero that
 * would make a company look like the cheapest name on the list.
 */

import { useEffect, useMemo, useState } from 'react';
import { apiClient, type MarketInstrument as ApiInstrument } from '../api/client';
import type { MarketInstrument } from '../data/mockData';
import { useLiveRows } from './useLiveRows';

/** Upstream exchange codes to the market labels the screens filter on. */
const MARKET_LABELS: Record<string, MarketInstrument['market']> = {
  BIST: 'BIST',
  NASDAQ: 'ABD',
  NYSE: 'ABD',
};

const CURRENCY_UNITS: Record<string, string> = { TRY: '₺', USD: '$', EUR: '€' };

function adapt(row: ApiInstrument): MarketInstrument {
  return {
    symbol: row.symbol,
    name: row.name,
    market: MARKET_LABELS[row.market ?? ''] ?? 'BIST',
    price: row.price,
    unit: CURRENCY_UNITS[row.currency] ?? row.currency,
    changePercent: row.change_percent ?? 0,
    // Volume is per-bar, not per-quote; the table reads it from the daily
    // candle instead. Zero here would read as "nobody traded today".
    volume: 0,
    marketCap: row.market_cap ?? 0,
    sector: row.sector ?? 'Bilinmiyor',
    week52Low: row.week52_low ?? 0,
    week52High: row.week52_high ?? 0,
    // Left undefined when the provider publishes nothing, which the column
    // renderer already shows as "—".
    pe: row.pe_ratio ?? undefined,
    pb: row.pb_ratio ?? undefined,
  } as MarketInstrument;
}

export interface InstrumentsState {
  instruments: MarketInstrument[];
  loading: boolean;
  /** Distinct sectors present in the live universe, for the filter panel. */
  sectors: string[];
}

/**
 * Fetch the universe once, then keep prices moving over the shared SSE stream.
 *
 * `changePercent` is refreshed alongside `price` by `useLiveRows`, so a row
 * cannot show a new price beside yesterday's change.
 */
export function useInstruments(limit = 200): InstrumentsState {
  const [fetched, setFetched] = useState<MarketInstrument[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiClient
      .getInstruments({ limit })
      .then((response) => setFetched((response.instruments ?? []).map(adapt)))
      .catch((error) => console.error('Failed to load instruments', error))
      .finally(() => setLoading(false));
  }, [limit]);

  const instruments = useLiveRows(fetched);
  const sectors = useMemo(
    () => Array.from(new Set(instruments.map((row) => row.sector))).sort(),
    [instruments],
  );

  return { instruments, loading, sectors };
}
