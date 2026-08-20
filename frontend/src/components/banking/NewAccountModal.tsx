import React, { useState } from 'react'

interface Props {
  isOpen: boolean
  onClose: () => void
  onSuccess?: (currency: string, type: 'checking' | 'savings' | 'foreign_currency') => void
}

export default function NewAccountModal({ isOpen, onClose, onSuccess }: Props) {
  const [step, setStep] = useState<1 | 2>(1)
  const [currency, setCurrency] = useState<'TL' | 'Dolar' | 'Euro'>('TL')
  const [branch] = useState('Online Şube') // Sabit

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
      <div className="bg-slate-900 border border-white/10 rounded-2xl w-full max-w-md shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-white/10">
          <h3 className="text-lg font-semibold text-white">
            {step === 1 ? 'Hesap Açılışı' : 'Hesap Açılışı Özet'}
          </h3>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          {step === 1 ? (
            <div className="space-y-5">
              <div>
                <label className="block text-sm font-medium text-slate-400 mb-1">Şube</label>
                <div className="w-full bg-slate-800/50 border border-white/10 rounded-xl p-3 text-slate-300">
                  {branch} <span className="text-xs text-brandBlue ml-2">(Tek seçenek)</span>
                </div>
              </div>
              
              <div>
                <label className="block text-sm font-medium text-slate-400 mb-2">Para Birimi</label>
                <div className="flex gap-3">
                  {['TL', 'Dolar', 'Euro'].map(c => (
                    <button
                      key={c}
                      onClick={() => setCurrency(c as any)}
                      className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors border ${
                        currency === c 
                          ? 'bg-brandBlue/20 text-brandBlue border-brandBlue/50' 
                          : 'bg-white/5 text-slate-400 border-white/10 hover:bg-white/10'
                      }`}
                    >
                      {c}
                    </button>
                  ))}
                </div>
              </div>

              <div className="pt-4">
                <button 
                  onClick={() => setStep(2)}
                  className="w-full bg-brandBlue hover:bg-blue-600 text-white font-medium py-3 rounded-xl transition-colors shadow-lg shadow-brandBlue/20"
                >
                  Devam Et
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-5">
              <div className="bg-white/5 rounded-xl p-4 border border-white/5 space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-sm text-slate-400">Şube</span>
                  <span className="text-sm font-medium text-white">{branch}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-sm text-slate-400">Para Birimi</span>
                  <span className="text-sm font-medium text-white">{currency}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-sm text-slate-400">Hesap Tipi</span>
                  <span className="text-sm font-medium text-white">Vadesiz Hesap</span>
                </div>
              </div>

              <div className="pt-2">
                <button 
                  onClick={() => {
                    // İşlem tamamlandı
                    if (onSuccess) {
                      const type = currency === 'TL' ? 'checking' : 'foreign_currency'
                      onSuccess(currency, type)
                    }
                    onClose()
                    setStep(1)
                  }}
                  className="w-full bg-brandBlue hover:bg-blue-600 text-white font-medium py-3 rounded-xl transition-colors shadow-lg shadow-brandBlue/20"
                >
                  Onayla ve Aç
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
