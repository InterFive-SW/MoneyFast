import { useState } from 'react'
import { CreditCard, type CreditCardUpdate } from '../../data/mockBankingData'

interface CardSettingsModalProps {
  isOpen: boolean
  onClose: () => void
  card: CreditCard | null
  updateCard: (cardId: string, updates: CreditCardUpdate) => void
}

type DialogType = 'none' | 'pin' | 'limit' | 'emergency' | 'physical' | 'renewal' | 'success'

export default function CardSettingsModal({ isOpen, onClose, card, updateCard }: CardSettingsModalProps) {
  const [activeDialog, setActiveDialog] = useState<DialogType>('none')
  const [inputValue, setInputValue] = useState('')
  const [successMessage, setSuccessMessage] = useState('')
  const [errorMessage, setErrorMessage] = useState('')

  if (!isOpen || !card) return null

  const showSuccess = (msg: string) => {
    setSuccessMessage(msg)
    setErrorMessage('')
    setActiveDialog('success')
    // Automatically close success after 2 seconds
    setTimeout(() => {
      setActiveDialog('none')
    }, 2000)
  }

  const showError = (msg: string) => {
    setErrorMessage(msg)
  }

  const handleAction = () => {
    setErrorMessage('')
    
    if (activeDialog === 'pin') {
      const pin = inputValue;
      if (!/^\d{4}$/.test(pin)) {
        return showError("Şifre 4 haneli rakamlardan oluşmalıdır.");
      }
      if (new Set(pin).size === 1) {
        return showError("Şifre ardışık aynı rakamlardan (örn: 1111) oluşamaz.");
      }
      
      const isAscending = "0123456789".includes(pin);
      const isDescending = "9876543210".includes(pin);
      if (isAscending || isDescending) {
        return showError("Şifre ardışık rakamlardan (örn: 1234, 9876) oluşamaz.");
      }

      showSuccess("Kart şifreniz başarıyla güncellendi.");
    } 
    else if (activeDialog === 'emergency') {
      const isCurrentlyFrozen = card.settings?.isFrozen;
      updateCard(card.id, { settings: { isFrozen: !isCurrentlyFrozen } });
      showSuccess(isCurrentlyFrozen ? "Kart blokesi kaldırıldı." : "Kartınız donduruldu.")
    }
    else if (activeDialog === 'physical') {
      updateCard(card.id, { isDigital: false });
      showSuccess("Fiziksel kart talebiniz alınmıştır.")
    }
    else if (activeDialog === 'renewal') {
      showSuccess("Kart yenileme talebiniz başarıyla alındı.")
    }
    else if (activeDialog === 'limit') {
      const newLimit = Number(inputValue);
      if (!isNaN(newLimit) && newLimit > 0 && newLimit < card.limit) {
        updateCard(card.id, { limit: newLimit, availableLimit: newLimit - card.currentDebt });
        showSuccess(`Kart limitiniz ${newLimit} TL'ye düşürülmüştür.`)
      } else {
        showError("Geçersiz limit! Yeni limit mevcut limitten düşük ve 0'dan büyük olmalıdır.")
      }
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-black/60 backdrop-blur-md animate-fade-in"
        onClick={onClose}
      />
      
      {/* Main Modal */}
      <div className="relative w-full max-w-md bg-slate-900/40 backdrop-blur-2xl border border-white/10 rounded-3xl shadow-[0_0_40px_rgba(0,0,0,0.5)] overflow-hidden flex flex-col max-h-[85vh] animate-slide-up">
        
        {/* Header */}
        <div className="flex items-center px-6 py-5 border-b border-white/10 bg-white/5">
          <button 
            onClick={onClose}
            className="p-2 -ml-2 text-slate-400 hover:text-white hover:bg-white/5 rounded-full transition-colors"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
          </button>
          <h2 className="text-lg font-semibold text-white ml-2">Tüm Kart Ayarları</h2>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-6 scrollbar-hide">
          
          {/* Kullanım Ayarları */}
          <div>
            <h3 className="text-xs uppercase tracking-wider font-semibold text-slate-400 px-2 mb-3">Kullanım Ayarları</h3>
            <div className="bg-white/5 border border-white/5 rounded-2xl overflow-hidden">
              <button className="w-full flex items-center justify-between p-4 text-left hover:bg-white/10 transition-colors border-b border-white/5">
                <span className="text-slate-200 font-medium text-sm">Hesap Özeti Tercihleri</span>
                <svg className="w-4 h-4 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </button>
              <button className="w-full flex items-center justify-between p-4 text-left hover:bg-white/10 transition-colors">
                <span className="text-slate-200 font-medium text-sm">Kullanım Tercihleri</span>
                <svg className="w-4 h-4 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </button>
            </div>
          </div>

          {/* Güvenlik Ayarları */}
          <div>
            <h3 className="text-xs uppercase tracking-wider font-semibold text-slate-400 px-2 mb-3">Güvenlik Ayarları</h3>
            <div className="bg-white/5 border border-white/5 rounded-2xl overflow-hidden">
              <button onClick={() => { setActiveDialog('pin'); setInputValue(''); setErrorMessage(''); }} className="w-full flex items-center justify-between p-4 text-left hover:bg-white/10 transition-colors border-b border-white/5">
                <span className="text-slate-200 font-medium text-sm">Kart Şifre Belirleme</span>
                <svg className="w-4 h-4 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </button>
              <button onClick={() => { setActiveDialog('emergency'); setErrorMessage(''); }} className="w-full flex items-center justify-between p-4 text-left hover:bg-white/10 transition-colors">
                <span className="text-slate-200 font-medium text-sm">Acil Durum İşlemleri</span>
                <svg className="w-4 h-4 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </button>
            </div>
          </div>

          {/* Diğer İşlemler */}
          <div>
            <h3 className="text-xs uppercase tracking-wider font-semibold text-slate-400 px-2 mb-3">Diğer İşlemler</h3>
            <div className="bg-white/5 border border-white/5 rounded-2xl overflow-hidden">
              {card.isDigital && (
                <button onClick={() => { setActiveDialog('physical'); setErrorMessage(''); }} className="w-full flex items-center justify-between p-4 text-left hover:bg-white/10 transition-colors border-b border-white/5">
                  <span className="text-slate-200 font-medium text-sm">Fiziksel Kart Talebi</span>
                  <svg className="w-4 h-4 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </button>
              )}
              <button onClick={() => { setActiveDialog('renewal'); setErrorMessage(''); }} className="w-full flex items-center justify-between p-4 text-left hover:bg-white/10 transition-colors border-b border-white/5">
                <span className="text-slate-200 font-medium text-sm">Kart Yenileme İşlemleri</span>
                <svg className="w-4 h-4 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </button>
              {card.limit > 0 && (
                <button onClick={() => { setActiveDialog('limit'); setInputValue(''); setErrorMessage(''); }} className="w-full flex items-center justify-between p-4 text-left hover:bg-white/10 transition-colors">
                  <span className="text-slate-200 font-medium text-sm">Kart Limit İndirimi</span>
                  <svg className="w-4 h-4 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Sub-Dialog Layer (Rendered over the main modal) */}
      {activeDialog !== 'none' && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/80 backdrop-blur-xl animate-fade-in" onClick={() => setActiveDialog('none')} />
          <div className="relative w-full max-w-sm bg-slate-900/40 backdrop-blur-2xl border border-white/10 rounded-3xl shadow-[0_0_40px_rgba(0,0,0,0.5)] overflow-hidden p-6 animate-slide-up">
            
            {activeDialog === 'success' ? (
              <div className="text-center space-y-4">
                <div className="w-16 h-16 bg-emerald-500/20 border border-emerald-500/30 rounded-full flex items-center justify-center mx-auto text-emerald-400">
                  <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
                <h3 className="text-lg font-medium text-white">{successMessage}</h3>
              </div>
            ) : (
              <div className="space-y-6">
                <div>
                  <h3 className="text-lg font-medium text-white mb-2">
                    {activeDialog === 'pin' && "Kart Şifre Belirleme"}
                    {activeDialog === 'limit' && "Limit İndirimi"}
                    {activeDialog === 'emergency' && "Acil Durum"}
                    {activeDialog === 'physical' && "Fiziksel Kart Talebi"}
                    {activeDialog === 'renewal' && "Kart Yenileme"}
                  </h3>
                  <p className="text-sm text-slate-400">
                    {activeDialog === 'pin' && "Yeni 4 haneli kart şifrenizi girin:"}
                    {activeDialog === 'limit' && `Mevcut limitiniz: ${card.limit.toLocaleString('tr-TR')} TL. Lütfen yeni ve daha düşük bir limit girin.`}
                    {activeDialog === 'emergency' && (card.settings?.isFrozen ? "Kartınızın geçici blokesini kaldırmak istiyor musunuz?" : "Kartınızı geçici olarak kullanıma kapatmak istiyor musunuz?")}
                    {activeDialog === 'physical' && "Bu dijital kartınız için fiziksel basım talep etmek istiyor musunuz? Kartınız basılıp sistemde kayıtlı adresinize gönderilecektir."}
                    {activeDialog === 'renewal' && "Kartınızın yenilenmesini talep ediyor musunuz? Mevcut kartınız iptal edilip yenisi gönderilecektir."}
                  </p>
                </div>

                {(activeDialog === 'pin' || activeDialog === 'limit') && (
                  <div>
                    <input 
                      type={activeDialog === 'pin' ? 'password' : 'number'}
                      maxLength={activeDialog === 'pin' ? 4 : undefined}
                      value={inputValue}
                      onChange={(e) => {
                        const val = e.target.value;
                        if (activeDialog === 'pin') {
                          setInputValue(val.replace(/\D/g, '').slice(0, 4));
                        } else {
                          setInputValue(val);
                        }
                      }}
                      placeholder={activeDialog === 'pin' ? '****' : 'Örn: 5000'}
                      className="w-full bg-black/40 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:border-brandBlue focus:ring-1 focus:ring-brandBlue transition-all text-center tracking-widest text-xl font-medium"
                    />
                    {errorMessage && <p className="text-rose-400 text-xs mt-2 text-center">{errorMessage}</p>}
                  </div>
                )}

                <div className="flex gap-3 pt-2">
                  <button 
                    onClick={() => setActiveDialog('none')}
                    className="flex-1 py-3 bg-white/5 border border-white/10 text-white rounded-xl font-medium hover:bg-white/10 transition-colors"
                  >
                    İptal
                  </button>
                  <button 
                    onClick={handleAction}
                    className="flex-1 py-3 bg-brandBlue text-white rounded-xl font-medium hover:bg-blue-600 transition-colors shadow-lg shadow-brandBlue/30"
                  >
                    Onayla
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
