import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiClient } from '../../api/client'
import type { Position } from '../../api/client'
import { useLiveRows } from '../../hooks/useLiveRows'
import { baseEquivalent, formatMoney } from '../../lib/money'
import { useMarketStream } from '../../hooks/useMarketStream'

/**
 * Pozisyonlar Tablosu Bileşeni (Fintables tarzı)
 * Mevcut hisse/varlık portföyünü tabular-nums fontları ile veri-yoğun bir yapıda listeler.
 *
 * Adet ve maliyet açılışta bir kez çekilir; fiyat ve fiyata bağlı kolonlar
 * (pozisyon değeri, günlük ve toplam getiri) canlı akıştan gelen her fiyatla
 * yeniden hesaplanır. Yalnızca fiyat kolonunu güncelleyip yanındaki değeri
 * dondurmak satırı kendi içinde tutarsız bırakırdı.
 */
export default function PositionsWidget() {
  const navigate = useNavigate()
  const [positions, setPositions] = useState<Position[]>([])
  const { rates } = useMarketStream()
  const [fetched, setFetched] = useState<Position[]>([])
  const [loading, setLoading] = useState(true)

  const positions = useLiveRows(fetched, (row, quote) => {
    const totalValue = row.price * row.quantity
    const cost = row.avgCost * row.quantity
    const totalReturn = totalValue - cost
    const previousClose = quote.change != null ? row.price - quote.change : null
    return {
      totalValue,
      totalReturn,
      // Sıfır maliyetli bir satırda yüzde tanımsızdır; 0 yazmak "başabaş"
      // demek olurdu ki bu bir ölçüm değil, uydurma olurdu.
      totalReturnPercent: cost ? round2((totalReturn / cost) * 100) : row.totalReturnPercent,
      dailyReturn: previousClose != null ? round2((row.price - previousClose) * row.quantity) : row.dailyReturn,
      dailyReturnPercent: quote.changePercent ?? row.dailyReturnPercent,
    }
  })

  useEffect(() => {
    async function loadData() {
      try {
        const data = await apiClient.getPositions()
        setFetched(data)
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
      <div className="flex flex-col h-full items-center justify-center bg-transparent rounded-2xl border border-transparent shadow-sm">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500"></div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full flex-col h-full bg-transparent p-1">
      <div className="flex items-center justify-between mb-4">
        <h3 
          className="text-[11px] uppercase tracking-wider font-semibold text-slate-400 cursor-pointer hover:text-brandBlue transition-colors"
          onClick={() => navigate('/portfolio')}
        >
          Pozisyonlar <span className="text-[9px] opacity-70 ml-1">↗</span>
        </h3>
      </div>

      <div className="flex-1 overflow-x-auto">
        <table className="w-full text-left border-collapse min-w-[500px]">
          <thead>
            <tr className="border-b border-white/10">
              <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400">Varlık</th>
              <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Fiyat</th>
              <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Adet</th>
              <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Ort. Maliyet</th>
              <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Pozisyon</th>
              <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Günlük Getiri</th>
              <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Toplam Getiri</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/10/50">
            {positions.map((pos) => (
              <tr key={pos.symbol} className="hover:bg-white/5 transition-colors group">
                <td className="py-3 font-semibold text-white text-sm">{pos.symbol}</td>
                <td className="py-3 text-right tabular-nums text-sm font-medium text-slate-300">
                  {formatMoney(pos.price, pos.currency)}
                </td>
                <td className="py-3 text-right tabular-nums text-sm text-slate-400">{pos.quantity}</td>
                <td className="py-3 text-right tabular-nums text-sm text-slate-400">
                  {formatMoney(pos.avgCost, pos.currency)}
                </td>
                <td className="py-3 text-right tabular-nums text-sm font-semibold text-white">
                  {formatMoney(pos.totalValue, pos.currency)}
                  {baseEquivalent(pos.totalValue, pos.currency, rates) && (
                    <span className="block text-[10px] font-normal text-slate-500">
                      {baseEquivalent(pos.totalValue, pos.currency, rates)}
                    </span>
                  )}
                </td>
                <td className={`py-3 text-right tabular-nums text-sm font-semibold ${pos.dailyReturn < 0 ? 'text-rose-500' : 'text-emerald-500'}`}>
                  {pos.dailyReturn > 0 ? '+' : ''}{formatMoney(pos.dailyReturn, pos.currency)} (
                  {pos.dailyReturnPercent > 0 ? '+' : ''}{pos.dailyReturnPercent}%)
                </td>
                <td className={`py-3 text-right tabular-nums text-sm font-semibold ${pos.totalReturn < 0 ? 'text-rose-500' : 'text-emerald-500'}`}>
                  {pos.totalReturn > 0 ? '+' : ''}{formatMoney(pos.totalReturn, pos.currency)} (
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

/** Kuruş hassasiyeti; kayan nokta artıklarının tabloya sızmasını önler. */
function round2(value: number): number {
  return Math.round(value * 100) / 100
}
