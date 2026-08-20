import React from 'react'
import type { BankTransaction } from '../../data/mockBankingData'

interface Props {
  transactions: BankTransaction[]
}

export default function RecentTransactionsWidget({ transactions }: Props) {
  return (
    <div className="flex flex-col rounded-2xl bg-slate-900/50 backdrop-blur-xl border border-white/10 p-6 shadow-2xl h-full">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-white">Son İşlemler</h3>
        <button className="text-xs font-medium text-brandBlue hover:text-blue-400 transition-colors">Tümünü Gör</button>
      </div>

      <div className="flex flex-col gap-4">
        {transactions.map(tx => (
          <div key={tx.id} className="flex items-center justify-between group">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-slate-800/80 border border-white/5 flex items-center justify-center text-lg shadow-inner">
                {tx.icon}
              </div>
              <div>
                <p className="text-sm font-medium text-white group-hover:text-brandBlue transition-colors">{tx.title}</p>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-[11px] text-slate-400">{tx.date}</span>
                  <span className="w-1 h-1 rounded-full bg-slate-600"></span>
                  <span className="text-[11px] text-slate-400">{tx.category}</span>
                </div>
              </div>
            </div>
            
            <div className={`text-sm font-semibold ${tx.type === 'income' ? 'text-emerald-400' : 'text-white'}`}>
              {tx.type === 'income' ? '+' : '-'}₺{tx.amount.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
