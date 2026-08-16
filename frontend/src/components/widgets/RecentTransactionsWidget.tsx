/**
 * RecentTransactionsWidget — Son İşlemler Tablosu Bileşeni
 */

import type { TransactionData } from '../../data/mockData'

interface RecentTransactionsWidgetProps {
  transactions: TransactionData[]
}

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('tr-TR', {
    style: 'currency',
    currency: 'TRY',
  }).format(amount)
}

function formatDate(isoString: string): string {
  const date = new Date(isoString)
  return new Intl.DateTimeFormat('tr-TR', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

export default function RecentTransactionsWidget({
  transactions,
}: RecentTransactionsWidgetProps) {
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[11px] uppercase tracking-wider font-medium text-slate-500">Son İşlemler</h3>
        <button className="text-[11px] font-semibold text-emerald-600 hover:text-emerald-700 uppercase tracking-wider transition-colors">
          Tümünü Gör
        </button>
      </div>

      <div className="flex-1 overflow-auto -mx-2 px-2">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-slate-100">
              <th className="pb-2 text-[10px] font-semibold text-slate-400 uppercase tracking-wider">İşlem / Tarih</th>
              <th className="pb-2 text-[10px] font-semibold text-slate-400 uppercase tracking-wider text-right">Tutar</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((tx) => {
              const isPositive = tx.amount >= 0
              const amountColorClass = isPositive ? 'text-emerald-600' : 'text-slate-900'
              
              // We don't have icon/title in TransactionData right now, it has description, category.
              // So we will just use description and category text.
              
              return (
                <tr key={tx.id} className="border-b border-slate-50 hover:bg-slate-50/50 transition-colors group">
                  <td className="py-2.5 flex items-center gap-3">
                    <div className="flex flex-col">
                      <span className="text-[12px] font-semibold text-slate-900 line-clamp-1">{tx.description}</span>
                      <span className="text-[10px] text-slate-400 font-medium tabular-nums uppercase tracking-wider">{formatDate(tx.date)}</span>
                    </div>
                  </td>
                  <td className="py-2.5 text-right align-middle">
                    <span className={`text-[12px] font-bold tabular-nums ${amountColorClass}`}>
                      {isPositive ? '+' : ''}{formatCurrency(tx.amount)}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
