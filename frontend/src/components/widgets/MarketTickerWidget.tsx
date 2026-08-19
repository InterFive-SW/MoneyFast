import type { MarketTicker } from '../../data/mockData'

export default function MarketTickerWidget({ tickers }: { tickers: MarketTicker[] }) {
  return (
    <div className="flex flex-col h-full">
      <h3 className="text-sm font-semibold text-slate-400 mb-4">Piyasa Özeti</h3>
      <div className="grid grid-cols-2 gap-4">
        {tickers.map(t => (
          <div key={t.symbol} className="flex flex-col p-3 bg-white/5 rounded-xl border border-white/10">
            <span className="text-xs text-slate-400 font-medium">{t.symbol}</span>
            <span className="text-sm font-bold text-white mt-1">
              {t.value.toLocaleString('tr-TR')} {t.unit}
            </span>
            <span className={`text-xs font-semibold mt-1 ${t.changePercent < 0 ? 'text-rose-500' : 'text-emerald-500'}`}>
              {t.changePercent > 0 ? '+' : ''}{t.changePercent}%
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
