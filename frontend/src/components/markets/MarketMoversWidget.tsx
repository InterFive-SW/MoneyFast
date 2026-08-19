import { useMemo, useState } from 'react'
import type { MarketInstrument } from '../../data/mockData'

type Tab = 'gainers' | 'losers'

interface Props {
  instruments: MarketInstrument[]
}

/**
 * Piyasa geneli Yükselenler/Düşenler paneli — TopMoversWidget ile aynı görsel dil,
 * ama apiClient yerine mock enstrüman listesinden client-side hesaplar.
 */
export default function MarketMoversWidget({ instruments }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>('gainers')

  const currentItems = useMemo(() => {
    const sorted = [...instruments].sort((a, b) =>
      activeTab === 'gainers' ? b.changePercent - a.changePercent : a.changePercent - b.changePercent
    )
    return sorted.slice(0, 5)
  }, [instruments, activeTab])

  return (
    <div className="flex flex-col h-full bg-slate-900/50 backdrop-blur-xl rounded-[2rem] border border-white/10 shadow-2xl p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-400">Hareketliler</h3>
        <div className="flex bg-slate-800/5 p-1 rounded-lg backdrop-blur-sm">
          <button
            onClick={() => setActiveTab('gainers')}
            className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${activeTab === 'gainers' ? 'bg-slate-800 text-emerald-500 shadow-sm' : 'text-slate-400 hover:text-slate-200'}`}
          >
            Yükselenler
          </button>
          <button
            onClick={() => setActiveTab('losers')}
            className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${activeTab === 'losers' ? 'bg-slate-800 text-rose-500 shadow-sm' : 'text-slate-400 hover:text-slate-200'}`}
          >
            Düşenler
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto pr-2 -mr-2">
        <div className="flex flex-col gap-2">
          {currentItems.map((item) => (
            <div key={item.symbol} className="flex items-center justify-between p-3 bg-slate-800/40 hover:bg-slate-800/60 rounded-xl transition-colors border border-white/20">
              <div>
                <div className="font-semibold text-white text-sm">{item.symbol}</div>
                <div className="text-xs text-slate-400">{item.name}</div>
              </div>
              <div className="text-right">
                <div className="tabular-nums text-sm font-medium text-slate-200">
                  {item.price.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} {item.unit}
                </div>
                <div className={`tabular-nums text-xs font-semibold ${item.changePercent < 0 ? 'text-rose-500' : 'text-emerald-500'}`}>
                  {item.changePercent > 0 ? '+' : ''}{item.changePercent.toFixed(2)}%
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
