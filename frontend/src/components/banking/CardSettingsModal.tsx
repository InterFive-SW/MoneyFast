import React, { useState } from 'react'

interface Props {
  isOpen: boolean
  onClose: () => void
  cardName?: string
}

export default function CardSettingsModal({ isOpen, onClose, cardName }: Props) {
  const [onlineShopping, setOnlineShopping] = useState(true)
  const [contactless, setContactless] = useState(true)

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
      <div className="bg-slate-900 border border-white/10 rounded-2xl w-full max-w-md shadow-2xl overflow-hidden">
        <div className="flex items-center justify-between p-4 border-b border-white/10">
          <h3 className="text-lg font-semibold text-white">Kart Ayarları</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="p-6 space-y-6">
          <div>
            <h4 className="text-sm font-medium text-white mb-1">{cardName || 'Seçili Kart'}</h4>
            <p className="text-xs text-slate-400">Bu karta ait güvenlik ve işlem ayarlarını yönetin.</p>
          </div>

          <div className="space-y-4">
            {/* Online Alışveriş */}
            <div className="flex items-center justify-between p-4 bg-white/5 rounded-xl border border-white/5">
              <div>
                <p className="text-sm font-medium text-white">İnternet Alışverişi</p>
                <p className="text-xs text-slate-400 mt-0.5">Kartınızı e-ticaret sitelerinde kullanıma açın.</p>
              </div>
              <button 
                onClick={() => setOnlineShopping(!onlineShopping)}
                className={`w-12 h-6 rounded-full transition-colors relative flex items-center ${onlineShopping ? 'bg-brandBlue' : 'bg-slate-700'}`}
              >
                <div className={`w-4 h-4 bg-white rounded-full transition-transform absolute ${onlineShopping ? 'translate-x-7' : 'translate-x-1'}`} />
              </button>
            </div>

            {/* Temassız Ödeme */}
            <div className="flex items-center justify-between p-4 bg-white/5 rounded-xl border border-white/5">
              <div>
                <p className="text-sm font-medium text-white">Temassız Ödeme</p>
                <p className="text-xs text-slate-400 mt-0.5">POS cihazlarında temassız işlem yetkisi.</p>
              </div>
              <button 
                onClick={() => setContactless(!contactless)}
                className={`w-12 h-6 rounded-full transition-colors relative flex items-center ${contactless ? 'bg-brandBlue' : 'bg-slate-700'}`}
              >
                <div className={`w-4 h-4 bg-white rounded-full transition-transform absolute ${contactless ? 'translate-x-7' : 'translate-x-1'}`} />
              </button>
            </div>
            
            {/* Limit Güncelleme */}
            <button className="w-full flex items-center justify-between p-4 bg-white/5 hover:bg-white/10 transition-colors rounded-xl border border-white/5 group">
              <div className="text-left">
                <p className="text-sm font-medium text-white">Limit Güncelleme</p>
                <p className="text-xs text-slate-400 mt-0.5">Kart limitinizi artırın veya azaltın.</p>
              </div>
              <svg className="w-5 h-5 text-slate-500 group-hover:text-white transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </button>
            
            {/* Sanal Kart */}
            <button className="w-full flex items-center justify-between p-4 bg-white/5 hover:bg-white/10 transition-colors rounded-xl border border-white/5 group">
              <div className="text-left">
                <p className="text-sm font-medium text-white">Sanal Kart Oluştur</p>
                <p className="text-xs text-slate-400 mt-0.5">İnternet harcamalarınız için güvenli kart.</p>
              </div>
              <svg className="w-5 h-5 text-slate-500 group-hover:text-white transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
            </button>
          </div>

          <button 
            onClick={onClose}
            className="w-full bg-slate-800 hover:bg-slate-700 text-white font-medium py-3 rounded-xl transition-colors border border-white/10"
          >
            Kapat
          </button>
        </div>
      </div>
    </div>
  )
}
