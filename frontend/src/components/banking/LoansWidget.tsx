import React from 'react'
import type { Loan } from '../../data/mockBankingData'

interface Props {
  loans: Loan[]
  onApplyLoan: () => void
}

/**
 * LoansWidget Component
 * Aktif kredileri listeler ve yeni kredi başvuru imkanı sunar.
 */
export default function LoansWidget({ loans, onApplyLoan }: Props) {
  return (
    <div className="flex flex-col rounded-2xl bg-slate-900/50 backdrop-blur-xl border border-white/10 p-6 shadow-2xl">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-white">Aktif Kredilerim</h3>
        <button 
          onClick={onApplyLoan}
          className="text-xs font-medium text-brandBlue hover:text-blue-400 transition-colors flex items-center gap-1"
        >
          <span>Kredi Başvurusu</span>
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
        </button>
      </div>

      <div className="flex flex-col gap-4">
        {loans.length === 0 ? (
          <p className="text-sm text-slate-400 italic">Aktif krediniz bulunmuyor.</p>
        ) : (
          loans.map(loan => (
            <div key={loan.id} className="bg-white/5 rounded-xl border border-white/5 p-4 flex flex-col gap-4">
              <div className="flex justify-between items-start">
                <div>
                  <h4 className="text-sm font-medium text-white">{loan.title}</h4>
                  <p className="text-xs text-slate-400 mt-0.5">Kalan: {loan.remainingMonths} ay</p>
                </div>
                <div className="text-right">
                  <p className="text-xs text-slate-400">Kalan Borç</p>
                  <p className="text-sm font-bold text-white">
                    ₺{loan.remainingAmount.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}
                  </p>
                </div>
              </div>

              {/* İlerleme Çubuğu */}
              <div>
                <div className="flex justify-between text-[10px] text-slate-400 mb-1.5">
                  <span>Ödenen</span>
                  <span>Toplam: ₺{loan.totalAmount.toLocaleString('tr-TR')}</span>
                </div>
                <div className="w-full h-1.5 bg-white/10 rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-emerald-500 rounded-full" 
                    style={{ width: `${loan.progressPercentage}%` }}
                  />
                </div>
              </div>

              {/* Sıradaki Taksit */}
              <div className="flex items-center justify-between bg-slate-800/50 rounded-lg p-3 mt-1">
                <div>
                  <p className="text-[10px] text-slate-400 uppercase tracking-wider">Sıradaki Taksit</p>
                  <p className="text-xs font-semibold text-white mt-0.5">
                    {new Date(loan.nextInstallmentDate).toLocaleDateString('tr-TR')}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-bold text-rose-400">
                    ₺{loan.nextInstallmentAmount.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}
                  </p>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
