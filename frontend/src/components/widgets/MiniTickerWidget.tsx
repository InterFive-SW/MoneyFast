import type { MarketTicker } from '../../data/mockData'

export default function MiniTickerWidget({ ticker }: { ticker: MarketTicker }) {
  return (
    <div className="flex flex-col h-full justify-center">
      <span className="text-[11px] uppercase tracking-wider font-medium text-slate-500 mb-1">{ticker.symbol}</span>
      <div className="flex items-baseline gap-2">
        <span className="text-lg font-bold text-slate-900 tabular-nums">
          {ticker.value.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </span>
        <span className={`text-[11px] font-semibold tabular-nums ${ticker.changePercent < 0 ? 'text-rose-500' : 'text-emerald-500'}`}>
          {ticker.changePercent > 0 ? '+' : ''}{ticker.changePercent}%
        </span>
      </div>
    </div>
  )
}
