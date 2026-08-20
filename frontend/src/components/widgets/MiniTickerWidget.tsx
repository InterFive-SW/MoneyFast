import { useQuote } from '../../hooks/useMarketStream'

/**
 * Tek satırlık canlı kur/endeks kutucuğu.
 *
 * Sembolü alır, fiyatı doğrudan canlı akıştan okur. İlk kare gelene kadar
 * fiyat yerine "—" gösterilir; 0,00 yazmak bir fiyat iddiası olurdu ve yanlış
 * olurdu.
 */
export default function MiniTickerWidget({ symbol, label }: { symbol: string; label?: string }) {
  const quote = useQuote(symbol)
  const changePercent = quote?.changePercent ?? null

  return (
    <div className="flex flex-col h-full justify-center">
      <span className="text-[11px] uppercase tracking-wider font-medium text-slate-400 mb-1">{label ?? symbol}</span>
      <div className="flex items-baseline gap-2">
        <span className="text-lg font-bold text-white tabular-nums">
          {quote
            ? quote.price.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
            : '—'}
        </span>
        {changePercent != null && (
          <span className={`text-[11px] font-semibold tabular-nums ${changePercent < 0 ? 'text-rose-500' : 'text-emerald-500'}`}>
            {changePercent > 0 ? '+' : ''}{changePercent.toFixed(2)}%
          </span>
        )}
      </div>
    </div>
  )
}
