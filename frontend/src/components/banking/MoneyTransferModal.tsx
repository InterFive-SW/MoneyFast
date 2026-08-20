import React, { useState } from 'react'

interface Props {
  isOpen: boolean
  onClose: () => void
  defaultSenderAccountId?: string
  onTransfer?: (amount: number, fromAccountId: string, toIban: string, description: string) => void
}

export default function MoneyTransferModal({ isOpen, onClose, defaultSenderAccountId, onTransfer }: Props) {
  const [step, setStep] = useState<1 | 2>(1)
  
  // Form State
  const [senderAccount, setSenderAccount] = useState(defaultSenderAccountId || 'Vadesiz Maaş Hesabı')
  const [receiverIban, setReceiverIban] = useState('TR')
  const [receiverName, setReceiverName] = useState('')
  const [amount, setAmount] = useState('')
  const [description, setDescription] = useState('')

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm overflow-y-auto">
      <div className="bg-slate-900 border border-white/10 rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden my-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-white/10">
          <h3 className="text-lg font-semibold text-white">
            {step === 1 ? 'Para Transferi' : 'Para Transferi Özet'}
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
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-400 mb-1">Gönderen Hesap</label>
                <select 
                  value={senderAccount}
                  onChange={(e) => setSenderAccount(e.target.value)}
                  className="w-full bg-slate-800/50 border border-white/10 rounded-xl p-3 text-white appearance-none focus:outline-none focus:ring-2 focus:ring-brandBlue/50"
                >
                  <option value="Vadesiz Maaş Hesabı">Vadesiz Maaş Hesabı - 12.500,50 TL</option>
                  <option value="Birikim Hesabı">Birikim Hesabı - 130.000,00 TL</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-400 mb-1">Alıcı IBAN</label>
                <input 
                  type="text" 
                  value={receiverIban}
                  onChange={(e) => setReceiverIban(e.target.value)}
                  className="w-full bg-slate-800/50 border border-white/10 rounded-xl p-3 text-white focus:outline-none focus:ring-2 focus:ring-brandBlue/50 uppercase placeholder-slate-600"
                  placeholder="TR..."
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-400 mb-1">Alıcı Ad-Soyad</label>
                <input 
                  type="text" 
                  value={receiverName}
                  onChange={(e) => setReceiverName(e.target.value)}
                  className="w-full bg-slate-800/50 border border-white/10 rounded-xl p-3 text-white focus:outline-none focus:ring-2 focus:ring-brandBlue/50 placeholder-slate-600"
                  placeholder="İsim Soyisim"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-400 mb-1">Tutar (TL)</label>
                <input 
                  type="number" 
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  className="w-full bg-slate-800/50 border border-white/10 rounded-xl p-3 text-white focus:outline-none focus:ring-2 focus:ring-brandBlue/50 placeholder-slate-600"
                  placeholder="0.00"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-400 mb-1">Açıklama (İsteğe Bağlı)</label>
                <textarea 
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="w-full bg-slate-800/50 border border-white/10 rounded-xl p-3 text-white focus:outline-none focus:ring-2 focus:ring-brandBlue/50 placeholder-slate-600 resize-none h-20"
                  placeholder="Açıklama giriniz..."
                />
              </div>

              <div className="pt-2">
                <button 
                  disabled={!receiverIban || receiverIban === 'TR' || !receiverName || !amount}
                  onClick={() => setStep(2)}
                  className="w-full bg-brandBlue hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium py-3 rounded-xl transition-colors shadow-lg shadow-brandBlue/20"
                >
                  Devam Et
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-5">
              <div className="bg-white/5 rounded-xl p-5 border border-white/5 space-y-4">
                <div>
                  <div className="text-xs text-slate-400 mb-0.5">Gönderen Hesap</div>
                  <div className="text-sm font-medium text-white">{senderAccount}</div>
                </div>
                
                <div className="h-px w-full bg-white/10" />
                
                <div>
                  <div className="text-xs text-slate-400 mb-0.5">Alıcı IBAN</div>
                  <div className="text-sm font-medium text-white">{receiverIban}</div>
                </div>

                <div>
                  <div className="text-xs text-slate-400 mb-0.5">Alıcı Ad-Soyad</div>
                  <div className="text-sm font-medium text-white">{receiverName}</div>
                </div>

                <div className="h-px w-full bg-white/10" />
                
                <div className="flex justify-between items-end">
                  <div>
                    <div className="text-xs text-slate-400 mb-0.5">Tutar</div>
                    <div className="text-xl font-bold text-white">₺{parseFloat(amount).toLocaleString('tr-TR', { minimumFractionDigits: 2 })}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-xs text-slate-400 mb-0.5">İşlem Ücreti</div>
                    <div className="text-sm font-medium text-slate-300">₺0,00</div>
                  </div>
                </div>
                
                {description && (
                  <div className="pt-2">
                    <div className="text-xs text-slate-400 mb-0.5">Açıklama</div>
                    <div className="text-sm text-slate-300 italic">{description}</div>
                  </div>
                )}
              </div>

              <div className="pt-2">
                <button 
                  onClick={() => {
                    // İşlem tamamlandı
                    if (onTransfer) {
                      onTransfer(parseFloat(amount), senderAccount, receiverIban, description)
                    }
                    onClose()
                    setTimeout(() => setStep(1), 300) // Animasyon bitince sıfırla
                  }}
                  className="w-full bg-emerald-500 hover:bg-emerald-600 text-white font-medium py-3 rounded-xl transition-colors shadow-lg shadow-emerald-500/20"
                >
                  Onayla
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
