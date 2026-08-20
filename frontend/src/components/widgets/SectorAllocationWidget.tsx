import { useEffect, useState } from 'react'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import { apiClient } from '../../api/client'
import type { SectorAllocationItem } from '../../api/client'

export function formatSectorTooltip(value: number): [string, string] {
  return [`${value}%`, 'Oran']
}

export default function SectorAllocationWidget() {
  const [data, setData] = useState<SectorAllocationItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function loadData() {
      try {
        const response = await apiClient.getSectorAllocation()
        setData(response)
      } catch (error) {
        console.error('Failed to load sector allocation', error)
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

  return (
    <div className="flex flex-col h-full flex-col h-full bg-transparent p-1">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-400">Sektörel Dağılım</h3>
      </div>

      <div className="flex-1 flex flex-col md:flex-row items-center gap-4">
        {/* Chart Area */}
        <div className="w-full md:w-1/2 h-[150px] md:h-full relative">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                dataKey="percentage"
                nameKey="sector"
                cx="50%"
                cy="50%"
                innerRadius={40}
                outerRadius={65}
                stroke="none"
              >
                {data.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip
                formatter={formatSectorTooltip}
                contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Legend Area */}
        <div className="w-full md:w-1/2 flex flex-col justify-center gap-3">
          {data.map((item) => (
            <div key={item.sector} className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div 
                  className="w-2.5 h-2.5 rounded-full" 
                  style={{ backgroundColor: item.color }} 
                />
                <span className="text-sm font-medium text-slate-300">{item.sector}</span>
              </div>
              <span className="text-sm font-semibold text-white tabular-nums">{item.percentage}%</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
