/**
 * RecentTransactionsWidget — Son İşlemler Tablosu Bileşeni
 */

import { useEffect, useState } from 'react'
import { apiClient, type Movement } from '../../api/client'
import { formatMoney } from '../../lib/money'
// Yerel bir `formatDate` vardı ve paylaşılan adı gölgeliyordu; saat dilimi
// vermediği için ekranda UTC yazıyordu.
import { formatShortDateTime } from '../../lib/datetime'

export default function RecentTransactionsWidget() {
  // Real movements from the banking ledger. This widget was mounted with
  // `transactions={[]}` — permanently empty, so it could never show anything.
  const [movements, setMovements] = useState<Movement[]>([])
  const [currency, setCurrency] = useState('TRY')

  useEffect(() => {
    // Two steps: the account, then its statement. A user has one deposit
    // account, so there is nothing to choose between.
    apiClient
      .getBankAccounts()
      .then((accounts) => {
        const account = accounts[0]
        if (!account) return
        setCurrency(account.currency_code)
        return apiClient
          .getStatement(account.account_number, 8)
          .then((statement) => setMovements(statement.movements ?? []))
      })
      .catch((error) => console.error('Failed to load recent transactions', error))
  }, [])

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[11px] uppercase tracking-wider font-medium text-slate-400">Son İşlemler</h3>
        <button className="text-[11px] font-semibold text-emerald-600 hover:text-emerald-700 uppercase tracking-wider transition-colors">
          Tümünü Gör
        </button>
      </div>

      <div className="flex-1 overflow-auto -mx-2 px-2">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-white/10">
              <th className="pb-2 text-[10px] font-semibold text-slate-400 uppercase tracking-wider">İşlem / Tarih</th>
              <th className="pb-2 text-[10px] font-semibold text-slate-400 uppercase tracking-wider text-right">Tutar</th>
            </tr>
          </thead>
          <tbody>
            {movements.map((tx) => {
              // The ledger records direction rather than a signed amount, so
              // an incoming transfer is a CREDIT rather than a positive number.
              const isPositive = tx.direction === 'CREDIT'
              const amountColorClass = isPositive ? 'text-emerald-500' : 'text-white'

              return (
                <tr key={tx.reference_number} className="border-b border-white/5 hover:bg-white/5 transition-colors group">
                  <td className="py-2.5 flex items-center gap-3">
                    <div className="flex flex-col">
                      <span className="text-[12px] font-semibold text-white line-clamp-1">
                        {tx.description || tx.counterparty_iban || tx.reference_number}
                      </span>
                      <span className="text-[10px] text-slate-400 font-medium tabular-nums uppercase tracking-wider">{formatShortDateTime(tx.created_at)}</span>
                    </div>
                  </td>
                  <td className="py-2.5 text-right align-middle">
                    <span className={`text-[12px] font-bold tabular-nums ${amountColorClass}`}>
                      {isPositive ? '+' : '−'}{formatMoney(tx.amount, currency)}
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
