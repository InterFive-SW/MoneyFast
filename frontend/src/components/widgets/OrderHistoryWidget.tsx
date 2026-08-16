import { useEffect, useState } from 'react'
import { apiClient } from '../../api/client'
import type { Order } from '../../api/client'

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

  const getStatusColor = (status: Order['status']) => {
    switch (status) {
      case 'Gerçekleşti': return 'text-emerald-500 bg-emerald-500/10'
      case 'Bekliyor':    return 'text-amber-500 bg-amber-500/10'
      case 'İptal':       return 'text-rose-500 bg-rose-500/10'
      default:            return 'text-slate-500 bg-slate-500/10'
    }
  }

  const getTypeColor = (type: Order['type']) => {
    return type === 'Alış' ? 'text-emerald-600' : 'text-rose-600'
  }

  return (
    <div className="flex flex-col h-full bg-white/70 backdrop-blur-md rounded-2xl p-5 border border-white/50 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-500">Emir Geçmişi</h3>
      </div>

      <div className="flex-1 overflow-x-auto">
        <table className="w-full text-left border-collapse min-w-[500px]">
          <thead>
            <tr className="border-b border-slate-200/50">
              <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400">Varlık</th>
              <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400">Durum</th>
              <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400">Yön</th>
              <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Adet</th>
              <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Fiyat</th>
              <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Toplam</th>
              <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Tarih</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100/50">
            {orders.map((order) => (
              <tr key={order.id} className="hover:bg-slate-50/50 transition-colors group">
                <td className="py-3 font-semibold text-slate-800 text-sm">{order.symbol}</td>
                <td className="py-3">
                  <span className={`px-2 py-0.5 rounded text-[11px] font-semibold ${getStatusColor(order.status)}`}>
                    {order.status}
                  </span>
                </td>
                <td className={`py-3 font-semibold text-[13px] ${getTypeColor(order.type)}`}>{order.type}</td>
                <td className="py-3 text-right tabular-nums text-sm text-slate-600">{order.quantity}</td>
                <td className="py-3 text-right tabular-nums text-sm font-medium text-slate-700">
                  {order.price.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </td>
                <td className="py-3 text-right tabular-nums text-sm font-semibold text-slate-800">
                  {order.total.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </td>
                <td className="py-3 text-right tabular-nums text-[12px] text-slate-500">
                  {new Date(order.date).toLocaleString('tr-TR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
