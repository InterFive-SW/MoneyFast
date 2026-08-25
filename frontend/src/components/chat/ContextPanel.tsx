import { useEffect, useState } from 'react';
import { apiClient, type NewsItem } from '../../api/client';
import { useQuote } from '../../hooks/useMarketStream';

/**
 * Bağlam paneli — sohbette konuşulan enstrümanın canlı görünümü.
 *
 * Bu panel eskiden sabit bir ₺304,50 ve uydurma iki haber başlığı gösteriyordu;
 * üstünde de yeşil bir "Canlı" rozeti vardı. Haber uç noktasının kendi
 * dokümantasyonu bunu zaten reddediyor: "uydurma haber başlığı göstermek, boş
 * bir akış göstermekten çok daha kötü". Artık fiyat canlı akıştan, haberler
 * `/api/market/news`'ten geliyor; gösterilecek bir şey yoksa panel kendini
 * kapatıyor.
 */

interface ContextPanelProps {
  /** Konuşulan enstrümanın sembolü. */
  symbol: string;
  onClose: () => void;
}

function formatPrice(value: number, currency: string): string {
  const symbol = currency === 'USD' ? '$' : currency === 'EUR' ? '€' : '₺';
  return `${symbol} ${value.toLocaleString('tr-TR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export default function ContextPanel({ symbol, onClose }: ContextPanelProps) {
  const quote = useQuote(symbol);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [currency, setCurrency] = useState('TRY');
  const [name, setName] = useState(symbol);

  useEffect(() => {
    let cancelled = false;

    apiClient
      .getInstruments({ symbols: [symbol], limit: 1 })
      .then((response) => {
        const row = response.instruments?.[0];
        if (cancelled || !row) return;
        setCurrency(row.currency);
        setName(row.name || symbol);
      })
      .catch(() => {
        // Leave the symbol as its own label. A failed lookup is not a reason
        // to show the wrong name.
      });

    apiClient
      .getMarketNews()
      .then((items) => {
        if (cancelled) return;
        // Only headlines the ingestor actually linked to this instrument.
        // Showing unrelated economy news under a ticker is the same lie the
        // hardcoded bullets told, just sourced differently.
        setNews(items.filter((item) => item.relatedSymbols.includes(symbol)).slice(0, 4));
      })
      .catch(() => setNews([]));

    return () => {
      cancelled = true;
    };
  }, [symbol]);

  const changePercent = quote?.changePercent ?? null;
  const isDown = changePercent != null && changePercent < 0;

  return (
    <div className="flex h-full flex-col p-5">
      <div className="mb-5 flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brandBlue/20 text-xs font-bold text-brandBlue">
            {symbol.substring(0, 2).toUpperCase()}
          </div>
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold text-white">{symbol}</h2>
            <p className="truncate text-[11px] text-slate-400">{name}</p>
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Bağlam panelini kapat"
          className="shrink-0 rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-white/10 hover:text-white"
        >
          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      <div className="rounded-2xl border border-white/10 bg-slate-800/60 p-4">
        <div className="flex items-center justify-between">
          <span className="text-[10px] uppercase tracking-wider text-slate-400">Anlık Fiyat</span>
          {/* The badge only claims "live" when a frame has actually arrived. */}
          {quote && (
            <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-400">
              Canlı
            </span>
          )}
        </div>
        {quote ? (
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-2xl font-bold tracking-tight text-white tabular-nums">
              {formatPrice(quote.price, currency)}
            </span>
            {changePercent != null && (
              <span
                className={`flex items-center gap-0.5 text-xs font-semibold tabular-nums ${
                  isDown ? 'text-rose-500' : 'text-emerald-500'
                }`}
              >
                {/* The arrow follows the sign. It used to be hardcoded up. */}
                <svg viewBox="0 0 24 24" className={`h-3 w-3 ${isDown ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M5 10l7-7m0 0l7 7m-7-7v18" />
                </svg>
                %{Math.abs(changePercent).toFixed(2)}
              </span>
            )}
          </div>
        ) : (
          // No frame yet. A placeholder number here would be a price claim.
          <p className="mt-2 text-sm text-slate-400">Fiyat bekleniyor…</p>
        )}
      </div>

      <div className="mt-4 flex min-h-0 flex-1 flex-col rounded-2xl border border-white/10 bg-slate-800/60 p-4">
        <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold text-white">
          <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 text-slate-400" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
          </svg>
          Son Gelişmeler
        </h3>
        <div className="-mr-2 flex-1 space-y-3 overflow-y-auto pr-2">
          {news.map((item) => (
            <a
              key={item.id}
              href={item.url}
              target="_blank"
              rel="noopener noreferrer"
              className="block text-[11px] leading-relaxed text-slate-300 transition-colors hover:text-white"
            >
              {item.title}
              <span className="mt-0.5 block text-[10px] text-slate-500">
                {item.source} · {item.time}
              </span>
            </a>
          ))}
          {news.length === 0 && (
            <p className="text-[11px] text-slate-500">
              {symbol} ile ilgili haber bulunmuyor.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
