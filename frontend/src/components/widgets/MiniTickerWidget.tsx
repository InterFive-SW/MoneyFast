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
      <div className="flex items-baseline gap-2">
        <span className="text-lg font-bold text-white tabular-nums">
          {ticker.value.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </span>
        <span className={`text-[11px] font-semibold tabular-nums ${ticker.changePercent < 0 ? 'text-rose-500' : 'text-emerald-500'}`}>
          {ticker.changePercent > 0 ? '+' : ''}{ticker.changePercent}%
        </span>
      </div>
    </div>
  )
}
