import { useState, useMemo } from 'react'

interface Props {
  isOpen: boolean
  onClose: () => void
  onApply?: (amount: number) => void
}

export default function LoanApplicationModal({ isOpen, onClose, onApply }: Props) {
  const [step, setStep] = useState<1 | 2>(1)
  const [amount, setAmount] = useState<number>(10000)
  const [months, setMonths] = useState<number>(12)
  const interestRate = 3.59 // Sabit aylık faiz

  // Basit hesaplama
  const calculation = useMemo(() => {
    const r = interestRate / 100
    // Basit taksit hesabı: P * (r*(1+r)^n)/((1+r)^n - 1) 
    const monthlyRate = Math.pow(1 + r, months)
    const installment = amount * ((r * monthlyRate) / (monthlyRate - 1))
    const total = installment * months

    return {
      installment,
      total,
      interestRate
    }
  }, [amount, months])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm overflow-y-auto">
      <div className="bg-slate-900 border border-white/10 rounded-2xl w-full max-w-md shadow-2xl overflow-hidden my-auto">
        <div className="flex items-center justify-between p-4 border-b border-white/10">
          <h3 className="text-lg font-semibold text-white">
            {step === 1 ? 'Kredi Başvurusu' : 'Başvuru Onayı'}
          </h3>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="p-6">
          {step === 1 ? (
            <div className="space-y-6">
              <div>
                <label className="block text-sm font-medium text-slate-400 mb-2">
                  Kredi Tutarı: <span className="text-white font-bold">₺{amount.toLocaleString('tr-TR')}</span>
                </label>
                <input 
                  type="range" 
                  min="1000" 
                  max="100000" 
                  step="1000"
                  value={amount}
                  onChange={(e) => setAmount(Number(e.target.value))}
                  className="w-full accent-brandBlue"
                />
                <div className="flex justify-between text-xs text-slate-500 mt-1">
                  <span>₺1.000</span>
                  <span>₺100.000</span>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-400 mb-2">
                  Vade: <span className="text-white font-bold">{months} Ay</span>
                </label>
                <input 
                  type="range" 
                  min="3" 
                  max="36" 
                  step="3"
                  value={months}
                  onChange={(e) => setMonths(Number(e.target.value))}
                  className="w-full accent-brandBlue"
                />
                <div className="flex justify-between text-xs text-slate-500 mt-1">
                  <span>3 Ay</span>
                  <span>36 Ay</span>
                </div>
              </div>

              <div className="bg-white/5 rounded-xl p-4 border border-white/5 space-y-2">
                <div className="flex justify-between items-center text-sm">
                  <span className="text-slate-400">Aylık Faiz Oranı</span>
                  <span className="text-white font-medium">%{(calculation.interestRate).toFixed(2)}</span>
                </div>
                <div className="flex justify-between items-center text-sm">
                  <span className="text-slate-400">Aylık Taksit</span>
                  <span className="text-emerald-400 font-bold">₺{calculation.installment.toLocaleString('tr-TR', { maximumFractionDigits: 2 })}</span>
                </div>
                <div className="flex justify-between items-center text-sm pt-2 border-t border-white/10">
                  <span className="text-slate-400">Toplam Geri Ödeme</span>
                  <span className="text-white font-medium">₺{calculation.total.toLocaleString('tr-TR', { maximumFractionDigits: 2 })}</span>
                </div>
              </div>

              <button 
                onClick={() => {
                  if (onApply) {
                    onApply(amount)
                  }
                  setStep(2)
                }}
                className="w-full bg-brandBlue hover:bg-blue-600 text-white font-medium py-3 rounded-xl transition-colors shadow-lg shadow-brandBlue/20"
              >
                Başvuruyu İlerle
              </button>
            </div>
          ) : (
            <div className="space-y-6 text-center">
              <div className="w-16 h-16 bg-brandBlue/20 rounded-full mx-auto flex items-center justify-center mb-4 border border-brandBlue/50 shadow-[0_0_15px_rgba(75,123,229,0.3)]">
                <svg className="w-8 h-8 text-brandBlue" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              
              <h4 className="text-xl font-bold text-white mb-2">Başvurunuz Alındı!</h4>
              <p className="text-sm text-slate-400 leading-relaxed mb-6">
                <strong>₺{amount.toLocaleString('tr-TR')}</strong> tutarındaki <strong>{months} ay</strong> vadeli kredi başvurunuz değerlendirmeye alınmıştır. Sonuç tarafınıza SMS ile bildirilecektir.
              </p>

              <button 
                onClick={() => {
                  onClose()
                  setTimeout(() => setStep(1), 300)
                }}
                className="w-full bg-slate-800 hover:bg-slate-700 text-white font-medium py-3 rounded-xl transition-colors border border-white/10"
              >
                Kapat
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
