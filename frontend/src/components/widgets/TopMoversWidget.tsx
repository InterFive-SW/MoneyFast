import { useEffect, useState } from 'react'
import { apiClient } from '../../api/client'
import type { TopMoverItem } from '../../api/client'

type Tab = 'gainers' | 'losers'

export default function TopMoversWidget() {
  const [data, setData] = useState<Record<string, TopMoverItem[]>>({})
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<Tab>('gainers')

  useEffect(() => {
    async function loadData() {
      try {
        const response = await apiClient.getTopMovers()
        setData(response)
      } catch (error) {
        console.error('Failed to load top movers', error)
      } finally {
        setLoading(false)
      }
    }
    loadData()
  }, [])

  if (loading) {
    return (
      <div className="flex flex-col h-full items-center justify-center bg-white/70 backdrop-blur-md rounded-2xl border border-white/50 shadow-sm">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500"></div>
      </div>
    )
  }

  const currentItems = data[activeTab] || []

  return (
    <div className="flex flex-col h-full bg-white/70 backdrop-blur-md rounded-2xl p-5 border border-white/50 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-500">Hareketliler</h3>
        <div className="flex bg-slate-100/80 p-1 rounded-lg backdrop-blur-sm">
          <button
            onClick={() => setActiveTab('gainers')}
            className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${activeTab === 'gainers' ? 'bg-white text-emerald-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
          >
            Yükselenler
          </button>
          <button
            onClick={() => setActiveTab('losers')}
            className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${activeTab === 'losers' ? 'bg-white text-rose-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
          >
            Düşenler
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto pr-2 -mr-2">
        <div className="flex flex-col gap-2">
          {currentItems.map((item) => (
            <div key={item.symbol} className="flex items-center justify-between p-3 bg-white/40 hover:bg-white/60 rounded-xl transition-colors border border-white/20">
              <div className="font-semibold text-slate-800 text-sm">{item.symbol}</div>
              <div className="text-right">
                <div className="tabular-nums text-sm font-medium text-slate-700">
                  {item.price.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
                <div className={`tabular-nums text-xs font-semibold ${item.changePercent < 0 ? 'text-rose-500' : 'text-emerald-500'}`}>
                  {item.changePercent > 0 ? '+' : ''}{item.changePercent}%
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
