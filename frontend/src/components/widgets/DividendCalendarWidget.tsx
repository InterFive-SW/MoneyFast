import { useEffect, useState } from 'react'
import { apiClient } from '../../api/client'
import type { DividendItem } from '../../api/client'

export default function DividendCalendarWidget() {
  const [data, setData] = useState<DividendItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function loadData() {
      try {
        const response = await apiClient.getDividends()
        setData(response)
      } catch (error) {
        console.error('Failed to load dividends', error)
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

  return (
    <div className="flex flex-col h-full bg-white/70 backdrop-blur-md rounded-2xl p-5 border border-white/50 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-500">Temettü Takvimi</h3>
        <span className="text-xs font-medium text-slate-400">Yaklaşan Ödemeler</span>
      </div>

      <div className="flex-1 overflow-y-auto pr-2 -mr-2">
        <div className="flex flex-col gap-3">
          {data.map((item) => {
            const dateObj = new Date(item.paymentDate)
            const day = dateObj.getDate()
            const month = dateObj.toLocaleString('tr-TR', { month: 'short' })
            
            return (
              <div key={item.symbol} className="flex items-center gap-4 p-3 bg-white/40 hover:bg-white/60 rounded-xl transition-colors border border-white/20">
                <div className="flex flex-col items-center justify-center bg-slate-100 rounded-lg min-w-[50px] py-1">
                  <span className="text-xs font-semibold text-slate-500 uppercase">{month}</span>
                  <span className="text-lg font-bold text-slate-800">{day}</span>
                </div>
                
                <div className="flex-1">
                  <div className="font-semibold text-slate-800 text-sm">{item.symbol}</div>
                  <div className="text-xs text-slate-500">Ex-Date: {item.exDate}</div>
                </div>
                
                <div className="text-right">
                  <div className="tabular-nums text-sm font-medium text-slate-700">
                    {item.amount.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ₺
                  </div>
                  <div className="tabular-nums text-xs font-semibold text-emerald-600">
                    Verim: {item.yieldPercent}%
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
