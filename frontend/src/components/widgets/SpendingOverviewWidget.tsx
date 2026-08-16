/**
 * SpendingOverviewWidget — Harcama Özeti Bileşeni
 */

import type { SpendingOverviewData } from '../../data/mockData'

export default function SpendingOverviewWidget({ data }: { data: SpendingOverviewData }) {
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[11px] uppercase tracking-wider font-medium text-slate-500">Aylık Harcama ({data.month})</h3>
      </div>
      
      <div className="flex items-baseline gap-2 mb-4">
        <span className="text-2xl font-bold text-slate-900 tabular-nums">
          ₺{data.totalExpense.toLocaleString('tr-TR', { minimumFractionDigits: 0 })}
        </span>
        <span className={`text-[11px] font-semibold tabular-nums ${data.changePercent < 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
          {data.changePercent > 0 ? '+' : ''}{data.changePercent}%
        </span>
      </div>

      <div className="flex-1 overflow-auto -mx-2 px-2">
        <table className="w-full text-left border-collapse">
          <tbody>
            {data.categories.map(c => (
              <tr key={c.label} className="border-b border-slate-50 hover:bg-slate-50/50 transition-colors">
                <td className="py-2 flex items-center gap-2">
                  <span className="text-sm" aria-hidden="true">{c.icon}</span>
                  <span className="text-[12px] font-medium text-slate-700">{c.label}</span>
                </td>
                <td className="py-2 text-right">
                  <span className="text-[12px] font-semibold tabular-nums text-slate-900">₺{c.amount.toLocaleString('tr-TR')}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
