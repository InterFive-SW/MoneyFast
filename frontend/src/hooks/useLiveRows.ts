/**
 * Overlay live quotes onto a list of rows fetched once from the API.
 *
 * Every price widget has the same shape of problem: it loads a snapshot on
 * mount (which carries the columns the stream does not — quantity, cost basis,
 * company name) and then needs the price columns to keep moving. Merging in
 * one place keeps the three widgets from each inventing their own answer to
 * "what happens to a row the stream has no quote for".
 *
 * That answer is: it is left exactly as fetched. A row is never blanked and
 * never zeroed because a quote is missing — a stale price shown as stale beats
 * a price shown as 0,00 TL.
 */

import { useMarketStream, type QuoteFrame } from './useMarketStream';

export interface PricedRow {
  symbol: string;
  price: number;
  change?: number | null;
  changePercent?: number | null;
}

/**
 * Merge the live snapshot into `rows`, matching on `symbol`.
 *
 * `derive` lets a caller recompute the columns that depend on price — a
 * position's market value and P&L, say. Without it a table would tick its
 * price column while the value beside it stayed frozen, which reads as a
 * rendering bug and is really an inconsistent row.
 */
export function useLiveRows<T extends PricedRow>(
  rows: T[],
  derive?: (row: T, quote: QuoteFrame) => Partial<T>,
): T[] {
  const { quotes } = useMarketStream();

  return rows.map((row) => {
    const quote = quotes[row.symbol];
    if (!quote || typeof quote.price !== 'number') return row;

    const merged = {
      ...row,
      price: quote.price,
      change: quote.change ?? row.change,
      changePercent: quote.changePercent ?? row.changePercent,
    } as T;

    return derive ? { ...merged, ...derive(merged, quote) } : merged;
  });
}
