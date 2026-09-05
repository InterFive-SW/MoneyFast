import { useEffect, useState } from 'react'
import { apiClient } from '../../api/client'
import type { Order } from '../../api/client'
import { formatMoney } from '../../lib/money'
import { formatShortDateTime } from '../../lib/datetime'

/**
 * Emir Geçmişi Bileşeni
 * Gerçekleşen, bekleyen ve iptal olan emirleri listeler.
 */
export default function OrderHistoryWidget() {
  const [orders, setOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function loadData() {
      try {
        const data = await apiClient.getOrders()
        setOrders(data)
      } catch (error) {
        console.error('Failed to load orders', error)
      } finally {
        setLoading(false)
      }
    }
    loadData()
  }, [])

  /**
   * Durum rengi.
   *
   * Etiketler backend'de `market_service.ORDER_STATUS_TR` içinde ve
   * genişlediler: eskiden yalnızca üç değer vardı ve `PENDING` ile `FAILED`
   * haritada hiç YOKTU -- başarısız bir işlem kullanıcıya "Bekliyor" diye
   * gösteriliyordu. Başarısız olan bir şeyi sırada gibi göstermek, yanlış
   * bir renkten daha kötü.
   */
  const getStatusColor = (status: Order['status']) => {
    switch (status) {
      case 'Gerçekleşti': return 'text-emerald-500 bg-emerald-500/10'
      case 'Onay bekliyor':
      case 'Fiyat bekliyor':
      case 'İşleniyor':   return 'text-amber-500 bg-amber-500/10'
      case 'Başarısız':   return 'text-rose-500 bg-rose-500/10'
      case 'İptal edildi':
      case 'İptal':       return 'text-slate-400 bg-white/5'
      default:            return 'text-slate-400 bg-white/5'
    }
  }

  const getTypeColor = (type: Order['type']) => {
    return type === 'Alış' ? 'text-emerald-600' : 'text-rose-600'
  }

  if (loading) {
    // Boş tablo "emir yok" demektir; yüklenirken bunu göstermek yanlış olurdu.
    return (
      <div className="flex flex-col h-full items-center justify-center bg-transparent rounded-2xl border border-transparent shadow-sm">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500"></div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full flex-col h-full bg-transparent p-1">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-400">Emir Geçmişi</h3>
      </div>

      <div className="flex-1 overflow-x-auto">
        <table className="w-full text-left border-collapse min-w-[500px]">
          <thead>
            <tr className="border-b border-white/10">
              <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400">Varlık</th>
              <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400">Durum</th>
              <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400">Yön</th>
              <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Adet</th>
              <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Fiyat</th>
              <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Toplam</th>
              <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Tarih</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/10/50">
            {orders.map((order) => (
              <tr key={order.id} className="hover:bg-white/5 transition-colors group">
                <td className="py-3 font-semibold text-white text-sm">{order.symbol}</td>
                <td className="py-3">
                  <span className={`px-2 py-0.5 rounded text-[11px] font-semibold ${getStatusColor(order.status)}`}>
                    {order.status}
                  </span>
                </td>
                <td className={`py-3 font-semibold text-[13px] ${getTypeColor(order.type)}`}>{order.type}</td>
                <td className="py-3 text-right tabular-nums text-sm text-slate-400">{order.quantity}</td>
                <td className="py-3 text-right tabular-nums text-sm font-medium text-slate-300">
                  {formatMoney(order.price, order.currency)}
                </td>
                <td className="py-3 text-right tabular-nums text-sm font-semibold text-white">
                  {formatMoney(order.total, order.currency)}
                </td>
                <td className="py-3 text-right tabular-nums text-[12px] text-slate-400">
                  {formatShortDateTime(order.date)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
