/**
 * SpendingOverviewWidget — Harcama Özeti
 *
 * Kategorilere göre gerçek harcama; `/api/banking/spending` üzerinden
 * bankacılık defterinden okunuyor. Bir süre Dashboard.tsx içinden gömülü bir
 * nesneyle besleniyordu: 12.500 ₺ ve tek bir uydurma kategori.
 *
 * Kendi hesapları arasındaki transferler ve maaş girişleri toplama dahil
 * değil — para taşımak ya da para almak harcama değildir.
 */

import { useEffect, useState } from 'react'
import { apiClient, type SpendingSummary } from '../../api/client'
import { formatMoney } from '../../lib/money'

/** Kategori simgeleri — sunum tercihi, veri değil. */
const ICONS: Record<string, string> = {
  Market: '🛒',
  Kira: '🏠',
  Faturalar: '🧾',
  Ulaşım: '🚌',
  'Yeme İçme': '🍽️',
  Sağlık: '💊',
  Eğlence: '🎬',
}

export default function SpendingOverviewWidget() {
  const [data, setData] = useState<SpendingSummary | null>(null)

  useEffect(() => {
    apiClient
      .getSpending()
      .then(setData)
      .catch((error) => console.error('Failed to load spending summary', error))
  }, [])

  if (!data) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500"></div>
      </div>
    )
  }

  const categories = data.categories ?? []

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[11px] uppercase tracking-wider font-medium text-slate-400">
          Harcama ({data.period})
        </h3>
      </div>

      <div className="flex items-baseline gap-2 mb-4">
        <span className="text-2xl font-bold text-white tabular-nums">
          {formatMoney(data.total_expense, data.currency_code)}
        </span>
        {/* Null when there is no earlier window to compare against — a first
            month has no trend, and 0% would claim it was flat. */}
        {data.change_percent != null && (
          <span
            className={`text-[11px] font-semibold tabular-nums ${
              data.change_percent < 0 ? 'text-emerald-500' : 'text-rose-500'
            }`}
          >
            {data.change_percent > 0 ? '+' : ''}{data.change_percent}%
          </span>
        )}
      </div>

      <div className="flex-1 overflow-auto -mx-2 px-2">
        <table className="w-full text-left border-collapse">
          <tbody>
            {categories.map((c) => (
              <tr key={c.category} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                <td className="py-2 flex items-center gap-2">
                  <span className="text-sm" aria-hidden="true">{ICONS[c.category] ?? '•'}</span>
                  <span className="text-[12px] font-medium text-slate-300">{c.category}</span>
                </td>
                <td className="py-2 text-right">
                  <span className="text-[12px] font-semibold tabular-nums text-white">
                    {formatMoney(c.amount, data.currency_code)}
                  </span>
                </td>
              </tr>
            ))}
            {categories.length === 0 && (
              <tr>
                <td className="py-3 text-[12px] text-slate-500">
                  Bu dönemde kategorili harcama yok.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
