/**
 * One instrument, live.
 *
 * Detail pages used to resolve their subject against `MOCK_MARKET_INSTRUMENTS`,
 * so clicking THYAO in a table showing 301,25 opened a page showing 295,50 —
 * forever. This fetches the real row and keeps its price on the shared stream,
 * so the row you clicked and the page you land on cannot disagree.
 */

import { useEffect, useState } from 'react';
import { apiClient } from '../api/client';
import type { MarketInstrument } from '../data/mockData';
import { adaptInstrument } from './useInstruments';
import { useLiveRows } from './useLiveRows';

export interface InstrumentState {
  instrument: MarketInstrument | null;
  loading: boolean;
}

export function useInstrument(symbol: string): InstrumentState {
  const [fetched, setFetched] = useState<MarketInstrument | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!symbol) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    apiClient
      .getInstruments({ symbols: [symbol], limit: 1 })
      .then((response) => {
        if (cancelled) return;
        const row = response.instruments?.[0];
        setFetched(row ? adaptInstrument(row) : null);
      })
      .catch((error) => {
        console.error('Failed to load instrument', error);
        if (!cancelled) setFetched(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  // useLiveRows works on a list; a single instrument is a list of one.
  const [live] = useLiveRows(fetched ? [fetched] : []);
  return { instrument: live ?? null, loading };
}
