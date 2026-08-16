import { useEffect, useState } from 'react'
import { apiClient } from '../../api/client'
import type { HeatmapItem } from '../../api/client'

export default function ProfitLossHeatmapWidget() {
  const [data, setData] = useState<HeatmapItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function loadData() {
      try {
        const response = await apiClient.getHeatmap()
        setData(response)
      } catch (error) {
        console.error('Failed to load heatmap data', error)
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

  // Helper to determine color intensity based on performance
  const getBackgroundColor = (changePercent: number) => {
    if (changePercent >= 2) return 'bg-emerald-600'
    if (changePercent > 0) return 'bg-emerald-400'
    if (changePercent <= -2) return 'bg-rose-600'
    if (changePercent < 0) return 'bg-rose-400'
    return 'bg-slate-400'
  }

  return (
    <div className="flex flex-col h-full bg-white/70 backdrop-blur-md rounded-2xl p-5 border border-white/50 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-500">Isı Haritası</h3>
        <span className="text-xs font-medium text-slate-400">BIST 30</span>
      </div>

      <div className="flex-1 w-full overflow-hidden flex flex-wrap gap-1 content-start">
        {data.map((item) => (
          <div
            key={item.symbol}
            style={{ 
              flexGrow: item.weight, 
              width: `${Math.max(item.weight * 2, 12)}%`,
              minHeight: '60px' 
            }}
            className={`flex flex-col items-center justify-center rounded-lg text-white transition-opacity hover:opacity-90 cursor-pointer ${getBackgroundColor(item.changePercent)}`}
            title={`${item.symbol} | Sektör: ${item.sector} | Değişim: ${item.changePercent}%`}
          >
            <span className="text-xs md:text-sm font-bold tracking-tight">{item.symbol}</span>
            <span className="text-[10px] md:text-xs font-medium opacity-90 tabular-nums">
              {item.changePercent > 0 ? '+' : ''}{item.changePercent}%
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
