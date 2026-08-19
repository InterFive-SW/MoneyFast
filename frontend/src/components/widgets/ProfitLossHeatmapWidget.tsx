import { useEffect, useState } from 'react'
import { apiClient } from '../../api/client'
import type { HeatmapItem } from '../../api/client'

interface Props {
  w?: number
  h?: number
}

export default function ProfitLossHeatmapWidget({ w = 4, h = 4 }: Props) {
  const [data, setData] = useState<HeatmapItem[]>([])
  const [loading, setLoading] = useState(true)
  const [hoveredItem, setHoveredItem] = useState<HeatmapItem | null>(null)
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 })

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
      <div className="flex flex-col h-full items-center justify-center bg-transparent rounded-2xl border border-transparent shadow-sm">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500"></div>
      </div>
    )
  }

  // Summary View
  if (w <= 2 || h <= 2) {
    const avgChange = data.reduce((acc, curr) => acc + curr.changePercent, 0) / (data.length || 1)
    const isPositive = avgChange >= 0
    return (
      <div className="flex flex-col h-full flex-col h-full bg-transparent p-1 items-center justify-center text-center">
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-400 mb-2">Piyasa Isısı (Özet)</h3>
        <div className={`text-2xl font-bold ${isPositive ? 'text-accent-600' : 'text-rose-500'}`}>
          {isPositive ? '+' : ''}{avgChange.toFixed(2)}%
        </div>
        <p className="text-xs text-slate-400 mt-1">BIST 30 Ortalama</p>
      </div>
    )
  }

  const getBackgroundGradient = (changePercent: number) => {
    if (changePercent >= 2) return 'bg-gradient-to-br from-accent-400 to-accent-600'
    if (changePercent > 0) return 'bg-gradient-to-br from-accent-300 to-accent-500'
    if (changePercent <= -2) return 'bg-gradient-to-br from-rose-500 to-rose-700'
    if (changePercent < 0) return 'bg-gradient-to-br from-rose-400 to-rose-600'
    return 'bg-gradient-to-br from-slate-400 to-slate-500'
  }

  return (
    <div className="relative flex flex-col h-full flex-col h-full bg-transparent p-1">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-400">Isı Haritası</h3>
        <span className="text-xs font-medium text-slate-400">BIST 30</span>
      </div>

      <div className="flex-1 w-full overflow-hidden flex flex-wrap gap-2 content-start">
        {data.map((item) => (
          <div
            key={item.symbol}
            style={{ 
              flexGrow: item.weight, 
              width: `${Math.max(item.weight * 2, 12)}%`,
              minHeight: '60px' 
            }}
            onMouseEnter={(e) => {
              setHoveredItem(item)
              const rect = e.currentTarget.getBoundingClientRect()
              const parentRect = e.currentTarget.parentElement!.getBoundingClientRect()
              setTooltipPos({ x: rect.left - parentRect.left + rect.width / 2, y: rect.top - parentRect.top })
            }}
            onMouseLeave={() => setHoveredItem(null)}
            className={`flex flex-col items-center justify-center rounded-xl text-white transition-all duration-300 hover:scale-[1.02] hover:shadow-lg hover:z-10 cursor-pointer ${getBackgroundGradient(item.changePercent)} border border-white/20`}
          >
            <span className="text-xs md:text-sm font-bold tracking-tight drop-shadow-sm">{item.symbol}</span>
            <span className="text-[10px] md:text-xs font-medium opacity-90 tabular-nums drop-shadow-sm">
              {item.changePercent > 0 ? '+' : ''}{item.changePercent}%
            </span>
          </div>
        ))}
      </div>

      {hoveredItem && (
        <div 
          className="absolute z-20 pointer-events-none bg-slate-800 text-white p-3 rounded-xl shadow-2xl backdrop-blur-xl border border-slate-700/50 flex flex-col gap-1 min-w-[140px] transform -translate-x-1/2 -translate-y-[110%] transition-opacity duration-200"
          style={{ left: tooltipPos.x, top: tooltipPos.y }}
        >
          <div className="flex justify-between items-center border-b border-slate-600/50 pb-1 mb-1">
            <span className="font-bold">{hoveredItem.symbol}</span>
            <span className={`font-medium ${hoveredItem.changePercent >= 0 ? 'text-accent-400' : 'text-rose-400'}`}>
              {hoveredItem.changePercent > 0 ? '+' : ''}{hoveredItem.changePercent}%
            </span>
          </div>
          <div className="flex justify-between text-xs text-slate-300">
            <span>Sektör:</span>
            <span>{hoveredItem.sector}</span>
          </div>
          <div className="flex justify-between text-xs text-slate-300">
            <span>Ağırlık:</span>
            <span>{hoveredItem.weight}%</span>
          </div>
        </div>
      )}
    </div>
  )
}
