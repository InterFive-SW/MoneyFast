/**
 * Percent-change series for comparing instruments, from real candles.
 *
 * The chart this replaces drew a seeded PRNG with a built-in positive bias, so
 * every line trended up regardless of what the instrument had actually done.
 *
 * Rebasing to percent is what makes instruments at different price levels
 * comparable on one axis: a 300 TL stock and a 4.500 USD ounce of gold cannot
 * share a value axis, but their moves since day one can.
 */

import { useEffect, useState } from 'react';
import { apiClient } from '../api/client';

export type ComparisonRow = Record<string, number | string>;

export interface ComparisonState {
  data: ComparisonRow[];
  loading: boolean;
}

export function useComparisonSeries(symbols: string[], days: number): ComparisonState {
  const [data, setData] = useState<ComparisonRow[]>([]);
  const [loading, setLoading] = useState(true);
  const key = symbols.join(',');

  useEffect(() => {
    if (!symbols.length) {
      setData([]);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);

    Promise.all(symbols.map((symbol) => apiClient.getCandles(symbol, days)))
      .then((responses) => {
        if (cancelled) return;

        // Index each series by date so the rows line up even when one
        // instrument was not traded on a given day.
        const byDate = new Map<string, ComparisonRow>();
        responses.forEach((response, index) => {
          const symbol = symbols[index];
          const candles = response.candles ?? [];
          const base = candles[0]?.close;
          if (!base) return;
          for (const candle of candles) {
            const date = String(candle.timestamp).slice(0, 10);
            const row = byDate.get(date) ?? { date };
            row[symbol] = Number((((candle.close - base) / base) * 100).toFixed(2));
            byDate.set(date, row);
          }
        });

        setData([...byDate.values()].sort((a, b) => String(a.date).localeCompare(String(b.date))));
      })
      .catch((error) => {
        console.error('Failed to load comparison series', error);
        if (!cancelled) setData([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // `key` stands in for the array so a new array of the same symbols does
    // not refetch on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, days]);

  return { data, loading };
}
