/**
 * Live market prices over Server-Sent Events.
 *
 * ONE EventSource for the whole app, shared through a module-level singleton.
 * A hook that opened its own connection would mean the ticker strip, the
 * watchlist, the positions table and the heatmap each holding a socket and
 * each costing the backend a subscriber — four times the fan-out for
 * identical data.
 *
 * Falls back to interval polling when the stream cannot be established or
 * keeps dropping. A dashboard that silently stops updating is worse than one
 * that polls: the prices look current and are not.
 */

import { useEffect, useState } from 'react';

export interface QuoteFrame {
  price: number;
  change: number | null;
  changePercent: number | null;
  /** The instrument's own currency, so an overlay cannot strip the unit. */
  currency?: string;
}

/** Which instrument quotes the rate for which currency. */
const FX_SYMBOLS: Record<string, string> = { USD: 'USDTRY', EUR: 'EURTRY' };

/**
 * Conversion rates into lira, read out of the frame itself.
 *
 * Derived rather than sent separately: USDTRY and EURTRY are instruments like
 * any other and are already in every frame, so a separate `fx` field could
 * drift from the quotes beside it.
 */
function ratesFrom(quotes: Record<string, QuoteFrame>): Record<string, number> {
  const rates: Record<string, number> = {};
  for (const [currency, symbol] of Object.entries(FX_SYMBOLS)) {
    const quote = quotes[symbol];
    if (quote && typeof quote.price === 'number') rates[currency] = quote.price;
  }
  return rates;
}

export interface MarketSnapshot {
  asOf: string | null;
  isDelayed: boolean;
  delayMinutes: number;
  quotes: Record<string, QuoteFrame>;
  /** Lira conversion rates, derived from the FX quotes in the same frame. */
  rates: Record<string, number>;
  /** 'live' while the stream is connected, 'polling' after it gave up. */
  transport: 'connecting' | 'live' | 'polling';
}

const EMPTY: MarketSnapshot = {
  asOf: null,
  isDelayed: true,
  delayMinutes: 0,
  quotes: {},
  rates: {},
  transport: 'connecting',
};

/** Attempts before giving up on SSE and falling back to polling. */
const MAX_STREAM_RETRIES = 3;

/** Poll cadence for the fallback, matching the ingest cycle. */
const POLL_INTERVAL_MS = 10_000;

type Listener = (snapshot: MarketSnapshot) => void;

let snapshot: MarketSnapshot = EMPTY;
let listeners: Listener[] = [];
let source: EventSource | null = null;
let pollTimer: ReturnType<typeof setInterval> | null = null;
let retries = 0;

function publish(next: MarketSnapshot) {
  snapshot = next;
  listeners.forEach((listener) => listener(next));
}

function applyFrame(raw: any, transport: MarketSnapshot['transport']) {
  const quotes = raw?.quotes ?? {};
  publish({
    asOf: raw?.as_of ?? null,
    isDelayed: Boolean(raw?.is_delayed),
    delayMinutes: Number(raw?.delay_minutes ?? 0),
    quotes,
    rates: ratesFrom(quotes),
    transport,
  });
}

async function pollOnce() {
  try {
    // The whole universe, not the four-symbol ticker strip. Polling /tickers
    // silently narrowed the snapshot from ~95 instruments to 4, so after
    // three SSE failures every live table froze while the strip kept moving.
    const response = await fetch('/api/market/instruments?limit=200');
    if (!response.ok) return;
    const body = await response.json();
    const quotes: Record<string, QuoteFrame> = {};
    for (const row of body?.instruments ?? []) {
      quotes[row.symbol] = {
        price: row.price,
        change: row.change ?? null,
        changePercent: row.change_percent ?? null,
        currency: row.currency,
      };
    }
    publish({ ...snapshot, quotes, rates: ratesFrom(quotes), transport: 'polling' });
  } catch {
    // Leave the last known snapshot in place. Blanking the dashboard on one
    // failed poll would be a worse lie than showing a slightly stale price.
  }
}

function startPolling() {
  if (pollTimer) return;
  pollOnce();
  pollTimer = setInterval(pollOnce, POLL_INTERVAL_MS);
}

function connect() {
  if (source || pollTimer) return;

  source = new EventSource('/api/market/stream');

  source.addEventListener('quotes', (event) => {
    retries = 0;
    try {
      applyFrame(JSON.parse((event as MessageEvent).data), 'live');
    } catch {
      // A malformed frame is skipped rather than clearing the snapshot.
    }
  });

  source.onerror = () => {
    source?.close();
    source = null;
    retries += 1;
    if (retries >= MAX_STREAM_RETRIES) {
      // The browser retries SSE on its own, but if the endpoint is genuinely
      // unavailable that loop never terminates and the UI freezes silently.
      startPolling();
      return;
    }
    // Backs off before reconnecting so a restarting backend is not hammered.
    setTimeout(connect, 1000 * retries);
  };
}

function teardown() {
  source?.close();
  source = null;
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  retries = 0;
}

/**
 * Subscribe to live prices.
 *
 * The connection opens on the first subscriber and closes when the last one
 * unmounts, so a user sitting on a page with no price widgets is not holding
 * a stream open.
 */
export function useMarketStream(): MarketSnapshot {
  const [current, setCurrent] = useState<MarketSnapshot>(snapshot);

  useEffect(() => {
    listeners.push(setCurrent);
    connect();
    return () => {
      listeners = listeners.filter((listener) => listener !== setCurrent);
      if (listeners.length === 0) teardown();
    };
  }, []);

  return current;
}

/**
 * One instrument's live quote, or undefined until a frame arrives.
 *
 * Undefined rather than a zeroed placeholder: a component showing 0,00 TL
 * while it waits is asserting a price, and it would be wrong.
 */
export function useQuote(symbol: string): QuoteFrame | undefined {
  return useMarketStream().quotes[symbol];
}
