import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiClient } from '../../api/client'
import type { TopMoverItem } from '../../api/client'

type Tab = 'gainers' | 'losers'

export default function TopMoversWidget() {
  const navigate = useNavigate()
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
      <div className="flex flex-col h-full items-center justify-center bg-transparent rounded-2xl border border-transparent shadow-sm">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500"></div>
      </div>
    )
  }

  const currentItems = data[activeTab] || []

  return (
    <div className="flex flex-col h-full flex-col h-full bg-transparent p-1">
      <div className="flex items-center justify-between mb-4">
        <h3 
          className="text-[11px] uppercase tracking-wider font-semibold text-slate-400 cursor-pointer hover:text-brandBlue transition-colors"
          onClick={() => navigate('/investment/hisseler')}
        >
          Hareketliler <span className="text-[9px] opacity-70 ml-1">↗</span>
        </h3>
        <div className="flex bg-white/5/10/80 p-1 rounded-lg backdrop-blur-sm">
          <button
            onClick={() => setActiveTab('gainers')}
            className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${activeTab === 'gainers' ? 'bg-white/5 text-emerald-600 shadow-sm' : 'text-slate-400 hover:text-slate-300'}`}
          >
            Yükselenler
          </button>
          <button
            onClick={() => setActiveTab('losers')}
            className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${activeTab === 'losers' ? 'bg-white/5 text-rose-600 shadow-sm' : 'text-slate-400 hover:text-slate-300'}`}
          >
            Düşenler
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto pr-2 -mr-2">
        <div className="flex flex-col gap-2">
          {currentItems.map((item) => (
            <div key={item.symbol} className="flex items-center justify-between p-3 bg-white/5/40 hover:bg-white/5/60 rounded-xl transition-colors border border-white/20">
              <div className="font-semibold text-white text-sm">{item.symbol}</div>
              <div className="text-right">
                <div className="tabular-nums text-sm font-medium text-slate-300">
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
