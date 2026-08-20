import React, { useState } from 'react'

import type { Bill } from '../../data/mockBankingData'

interface Props {
  isOpen: boolean
  onClose: () => void
  bills?: Bill[]
  onPay?: (billId: string) => void
}

export default function BillPaymentModal({ isOpen, onClose, bills = [], onPay }: Props) {
  const [step, setStep] = useState<1 | 2>(1)
  
  // Sadece bekleyen faturaları gösterelim
  const pendingBills = bills.filter(b => b.status === 'pending')
  const [selectedBillId, setSelectedBillId] = useState(pendingBills.length > 0 ? pendingBills[0].id : '')
  
  const selectedBill = bills.find(b => b.id === selectedBillId)

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm overflow-y-auto">
      <div className="bg-slate-900 border border-white/10 rounded-2xl w-full max-w-md shadow-2xl overflow-hidden my-auto">
        <div className="flex items-center justify-between p-4 border-b border-white/10">
          <h3 className="text-lg font-semibold text-white">Fatura Öde</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="p-6">
          {step === 1 ? (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-400 mb-1">Kayıtlı Faturalarınız</label>
                {pendingBills.length === 0 ? (
                  <div className="p-3 text-slate-400 text-sm bg-slate-800/50 rounded-xl border border-white/10">Ödenecek faturanız bulunmamaktadır.</div>
                ) : (
                  <select 
                    value={selectedBillId}
                    onChange={(e) => setSelectedBillId(e.target.value)}
                    className="w-full bg-slate-800/50 border border-white/10 rounded-xl p-3 text-white focus:outline-none focus:ring-2 focus:ring-brandBlue/50 appearance-none"
                  >
                    {pendingBills.map(b => (
                      <option key={b.id} value={b.id}>{b.institution} - ₺{b.amount.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}</option>
                    ))}
                  </select>
                )}
              </div>

              <div className="pt-4">
                <button 
                  disabled={!selectedBillId}
                  onClick={() => setStep(2)}
                  className="w-full bg-brandBlue hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium py-3 rounded-xl transition-colors shadow-lg shadow-brandBlue/20"
                >
                  Faturayı Getir
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-5">
              <div className="bg-white/5 rounded-xl p-5 border border-white/5 space-y-4">
                <div className="text-center mb-2">
                  <div className="w-12 h-12 bg-slate-800 rounded-full mx-auto flex items-center justify-center text-xl border border-white/10 mb-2">
                    📄
                  </div>
                  <h4 className="text-white font-semibold">{selectedBill?.institution}</h4>
                  <p className="text-xs text-slate-400">Son Ödeme: {selectedBill?.dueDate}</p>
                </div>
                
                <div className="h-px w-full bg-white/10" />
                
                <div className="flex justify-center items-center">
                  <div className="text-center">
                    <div className="text-xs text-slate-400 mb-0.5">Ödenecek Tutar</div>
                    <div className="text-3xl font-bold text-white">₺{selectedBill?.amount.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}</div>
                  </div>
                </div>
              </div>

              <div className="pt-2">
                <button 
                  onClick={() => {
                    if (onPay && selectedBillId) {
                      onPay(selectedBillId)
                    }
                    onClose()
                    setTimeout(() => setStep(1), 300)
                  }}
                  className="w-full bg-emerald-500 hover:bg-emerald-600 text-white font-medium py-3 rounded-xl transition-colors shadow-lg shadow-emerald-500/20"
                >
                  Ödemeyi Tamamla
                </button>
                <button 
                  onClick={() => setStep(1)}
                  className="w-full mt-3 text-slate-400 hover:text-white text-sm font-medium py-2"
                >
                  Geri Dön
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
