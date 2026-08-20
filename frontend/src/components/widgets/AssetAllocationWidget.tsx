/**
 * AssetAllocationWidget — Varlık Dağılımı Bileşeni
 */

import { useEffect, useState } from 'react'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import { apiClient } from '../../api/client'
import type { AssetAllocationItem } from '../../api/client'
import { toNumber, seriesName } from '../../lib/chartFormat'

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('tr-TR', {
    style: 'currency',
    currency: 'TRY',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount)
}

export default function AssetAllocationWidget() {
  const [items, setItems] = useState<AssetAllocationItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function loadData() {
      try {
        const data = await apiClient.getAssetAllocation()
        setItems(data)
      } catch (error) {
        console.error('Failed to load asset allocation', error)
      } finally {
        setLoading(false)
      }
    }
    loadData()
  }, [])

  if (loading) {
    return (
      <div className="flex flex-col h-full items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500"></div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full flex-col h-full bg-transparent p-1">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-400">Varlık Dağılımı</h3>
      </div>

      <div className="flex-1 flex flex-col sm:flex-row gap-4 items-center">
        {/* Recharts Donut Grafik */}
        <div className="w-full sm:w-1/2 h-[160px] sm:h-full relative flex items-center justify-center">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={items}
                cx="50%"
                cy="50%"
                innerRadius={50}
                outerRadius={70}
                paddingAngle={3}
                dataKey="percentage"
                stroke="none"
              >
                {items.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip 
                formatter={(value, name, item: any) => [`%${toNumber(value) ?? 0} - ${formatCurrency(item?.payload?.amount ?? 0)}`, seriesName(name)]}
                contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 20px -8px rgba(0,0,0,0.1)', backgroundColor: 'rgba(255, 255, 255, 0.9)', backdropFilter: 'blur(8px)' }}
                itemStyle={{ fontSize: '12px', fontWeight: 600, color: '#334155' }}
              />
            </PieChart>
          </ResponsiveContainer>
          {/* Ortadaki Toplam Etiketi */}
          <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
            <span className="text-[10px] uppercase font-semibold tracking-wider text-slate-400">Toplam</span>
            <span className="text-sm font-bold text-white">
              {formatCurrency(items.reduce((acc, curr) => acc + curr.amount, 0))}
            </span>
          </div>
        </div>

        {/* Liste / Tablo */}
        <div className="w-full sm:w-1/2 flex-1 overflow-auto -mx-2 px-2">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-white/10">
              <th className="pb-2 text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Varlık</th>
              <th className="pb-2 text-[10px] font-semibold text-slate-400 uppercase tracking-wider text-right">Tutar</th>
              <th className="pb-2 text-[10px] font-semibold text-slate-400 uppercase tracking-wider text-right">Ağırlık</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.assetClass} className="border-b border-slate-50 hover:bg-white/5 transition-colors">
                <td className="py-2 flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full" style={{ backgroundColor: item.color }} />
                  <span className="text-[12px] font-semibold text-white">{item.assetClass}</span>
                </td>
                <td className="py-2 text-right">
                  <span className="text-[12px] font-semibold tabular-nums text-white">{formatCurrency(item.amount)}</span>
                </td>
                <td className="py-2 text-right">
                  <span className="text-[12px] font-bold tabular-nums text-slate-400">{item.percentage}%</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </div>
    </div>
  )
}
