import { useEffect, useState } from 'react'
import { apiClient } from '../../api/client'
import type { Position } from '../../api/client'

/**
 * Pozisyonlar Tablosu Bileşeni (Fintables tarzı)
 * Mevcut hisse/varlık portföyünü tabular-nums fontları ile veri-yoğun bir yapıda listeler.
 */
export default function PositionsWidget() {
  const [positions, setPositions] = useState<Position[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function loadData() {
      try {
        const data = await apiClient.getPositions()
        setPositions(data)
      } catch (error) {
        console.error('Failed to load positions', error)
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
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-500">Pozisyonlar</h3>
      </div>

      <div className="flex-1 overflow-x-auto">
        <table className="w-full text-left border-collapse min-w-[500px]">
          <thead>
            <tr className="border-b border-slate-200/50">
              <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400">Varlık</th>
              <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Fiyat</th>
              <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Adet</th>
              <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Ort. Maliyet</th>
              <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Pozisyon (₺)</th>
              <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Günlük Getiri</th>
              <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Toplam Getiri</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100/50">
            {positions.map((pos) => (
              <tr key={pos.symbol} className="hover:bg-slate-50/50 transition-colors group">
                <td className="py-3 font-semibold text-slate-800 text-sm">{pos.symbol}</td>
                <td className="py-3 text-right tabular-nums text-sm font-medium text-slate-700">
                  {pos.price.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </td>
                <td className="py-3 text-right tabular-nums text-sm text-slate-600">{pos.quantity}</td>
                <td className="py-3 text-right tabular-nums text-sm text-slate-600">
                  {pos.avgCost.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </td>
                <td className="py-3 text-right tabular-nums text-sm font-semibold text-slate-800">
                  {pos.totalValue.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </td>
                <td className={`py-3 text-right tabular-nums text-sm font-semibold ${pos.dailyReturn < 0 ? 'text-rose-500' : 'text-emerald-500'}`}>
                  {pos.dailyReturn > 0 ? '+' : ''}{pos.dailyReturn.toLocaleString('tr-TR', { minimumFractionDigits: 2 })} (
                  {pos.dailyReturnPercent > 0 ? '+' : ''}{pos.dailyReturnPercent}%)
                </td>
                <td className={`py-3 text-right tabular-nums text-sm font-semibold ${pos.totalReturn < 0 ? 'text-rose-500' : 'text-emerald-500'}`}>
                  {pos.totalReturn > 0 ? '+' : ''}{pos.totalReturn.toLocaleString('tr-TR', { minimumFractionDigits: 2 })} (
                  {pos.totalReturnPercent > 0 ? '+' : ''}{pos.totalReturnPercent}%)
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
