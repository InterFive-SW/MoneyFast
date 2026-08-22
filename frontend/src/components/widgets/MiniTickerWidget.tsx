import { useNavigate } from 'react-router-dom'
import type { MarketTicker } from '../../data/mockData'

export default function MiniTickerWidget({ ticker }: { ticker: MarketTicker }) {
  const navigate = useNavigate()
  
  return (
    <div 
      className="flex flex-col h-full justify-center cursor-pointer hover:bg-white/5 p-2 -m-2 rounded-xl transition-colors group"
      onClick={() => navigate('/investment')}
    >
      <span className="text-[11px] uppercase tracking-wider font-medium text-slate-400 mb-1 group-hover:text-brandBlue transition-colors">
        {ticker.symbol} <span className="text-[9px] opacity-70 ml-1">↗</span>
      </span>
import { useQuote } from '../../hooks/useMarketStream'
import { formatMoney } from '../../lib/money'

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
          {quote ? formatMoney(quote.price, quote.currency) : '—'}
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
