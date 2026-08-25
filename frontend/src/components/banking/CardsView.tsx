import React from 'react'
import { useState } from 'react'
import { useNavigate, useOutletContext } from 'react-router-dom'
import { BankingContextType } from '../../pages/Banking'
import CardSettingsModal from './CardSettingsModal'

export default function CardsView() {
  const navigate = useNavigate()
  const { data, updateCard } = useOutletContext<BankingContextType>()
  const cards = data.creditCards

  const [selectedCardId, setSelectedCardId] = useState<string>(cards[0]?.id || '')
  const [isSettingsModalOpen, setIsSettingsModalOpen] = useState(false)

  React.useEffect(() => {
    if (!cards.find(c => c.id === selectedCardId) && cards.length > 0) {
      setSelectedCardId(cards[cards.length - 1].id)
    }
  }, [cards, selectedCardId])

  const selectedCard = cards.find(c => c.id === selectedCardId)

  return (
    <div className="w-full max-w-7xl mx-auto flex flex-col gap-6 animate-fade-in-up">
      {/* Üst Navigasyon & Geri Butonu */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => navigate('/banking')}
          className="group flex items-center gap-2 px-4 py-2 bg-slate-900/50 hover:bg-slate-800/80 backdrop-blur-md border border-white/5 rounded-xl transition-all"
        >
          <svg className="w-5 h-5 text-slate-400 group-hover:text-white transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          <span className="text-slate-300 font-medium group-hover:text-white transition-colors">
            Menüye Dön
          </span>
        </button>

        <h2 className="text-xl font-bold tracking-tight text-white/90">Kartlarım</h2>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Sol Kolon: Kart Listesi */}
        <div className="lg:col-span-4 flex flex-col gap-4">
          <div className="bg-slate-900/40 backdrop-blur-xl border border-white/5 rounded-3xl p-6 shadow-xl flex flex-col gap-6">
            <div className="flex items-center justify-between">
              <h3 className="text-sm uppercase tracking-wider font-semibold text-slate-400">Tüm Kartlar</h3>
              <span className="text-xs font-medium text-brandBlue bg-brandBlue/10 px-2 py-1 rounded-md">
                {cards.length} Kart
              </span>
            </div>

            <div className="flex flex-col gap-3">
              {cards.map(card => {
                const isSelected = card.id === selectedCardId
                return (
                  <button
                    key={card.id}
                    onClick={() => setSelectedCardId(card.id)}
                    className={`text-left w-full p-4 rounded-2xl transition-all duration-300 border flex items-center justify-between ${
                      isSelected 
                        ? 'bg-gradient-to-br from-brandBlue/20 to-blue-900/20 border-brandBlue/50 shadow-lg shadow-brandBlue/10'
                        : 'bg-white/5 hover:bg-white/10 border-transparent'
                    }`}
                  >
                    <div>
                      <div className={`font-semibold ${isSelected ? 'text-white' : 'text-slate-300'} flex items-center gap-2`}>
                        {card.name}
                        {card.isDigital && (
                          <span className="px-1.5 py-0.5 rounded text-[9px] uppercase tracking-wider font-bold bg-brandBlue/20 text-brandBlue">
                            DİJİTAL
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-slate-400 font-mono mt-1">
                        {card.cardNumber}
                      </div>
                    </div>
                    <div className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center p-1 shrink-0">
                      {card.brand === 'mastercard' ? (
                        <svg viewBox="0 0 24 24" fill="none" className="w-full h-full">
                          <circle cx="8" cy="12" r="6" fill="#EA001B" />
                          <circle cx="16" cy="12" r="6" fill="#FFA200" fillOpacity="0.8" />
                        </svg>
                      ) : (
                        <div className="text-[10px] font-bold text-white uppercase italic">VISA</div>
                      )}
                    </div>
                  </button>
                )
              })}
            </div>

            {/* Yeni Kart Ekle Butonu */}
            <button 
              onClick={() => navigate('/banking/new-card')}
              className="mt-2 w-full py-3 border border-dashed border-slate-600 rounded-2xl text-slate-400 font-medium hover:bg-white/5 hover:text-white transition-colors hover:border-slate-500 flex items-center justify-center gap-2"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Yeni Kart Başvurusu
            </button>
          </div>
        </div>

        {/* Sağ Kolon: Kart Detayları */}
        <div className="lg:col-span-8 flex flex-col gap-6">
          {selectedCard ? (
            <div className="flex flex-col gap-6">
              
              {/* Kredi Kartı Görseli */}
              <div className={`w-full max-w-md mx-auto aspect-[1.586/1] rounded-2xl p-6 text-white shadow-2xl relative overflow-hidden bg-gradient-to-br ${selectedCard.color}`}>
                
                {selectedCard.isDigital && (
                  <div className="absolute top-4 right-4 bg-white/20 backdrop-blur-sm px-2 py-1 rounded text-xs font-bold tracking-widest uppercase">
                    DİJİTAL KART
                  </div>
                )}
                
                {/* Chip & NFC */}
                <div className="flex items-center justify-between mt-4">
                  <div className="w-12 h-10 bg-yellow-200/80 rounded-md border border-yellow-400/50 flex flex-col justify-around py-1 px-2">
                    <div className="w-full h-px bg-yellow-400/50"></div>
                    <div className="w-full h-px bg-yellow-400/50"></div>
                    <div className="w-full h-px bg-yellow-400/50"></div>
                  </div>
                  {!selectedCard.isDigital && (
                    <svg className="w-6 h-6 opacity-80" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v1m6 11h2m-6 0h-2v4m0-11v3m0 0h.01M12 12h4.01M16 20h4M4 12h4m12 0h.01M5 8h2a1 1 0 001-1V5a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1zm12 0h2a1 1 0 001-1V5a1 1 0 00-1-1h-2a1 1 0 00-1 1v2a1 1 0 001 1zM5 20h2a1 1 0 001-1v-2a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1z" />
                    </svg>
                  )}
                </div>
                
                {/* Card Number */}
                <div className="mt-8 font-mono text-2xl tracking-widest text-white/90">
                  {selectedCard.cardNumber}
                </div>
                
                {/* Footer Info */}
                <div className="absolute bottom-6 left-6 right-6 flex items-end justify-between">
                  <div className="flex flex-col">
                    <span className="text-[10px] uppercase tracking-wider text-white/60">Cardholder Name</span>
                    <span className="font-medium tracking-widest">ARDAN KAYA</span>
                  </div>
                  <div className="flex flex-col items-center mr-4">
                    <span className="text-[8px] uppercase tracking-wider text-white/60">Valid Thru</span>
                    <span className="font-mono text-sm">12/28</span>
                  </div>
                  <div className="w-12 h-12 relative flex items-center justify-center">
                    {selectedCard.brand === 'mastercard' ? (
                      <svg viewBox="0 0 24 24" fill="none" className="w-full h-full">
                        <circle cx="8" cy="12" r="6" fill="#EA001B" />
                        <circle cx="16" cy="12" r="6" fill="#FFA200" fillOpacity="0.8" />
                      </svg>
                    ) : (
                      <div className="text-sm font-bold italic text-white uppercase">VISA</div>
                    )}
                  </div>
                </div>
              </div>

              {/* Bilgi Kutuları */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-slate-900/40 backdrop-blur-xl border border-white/5 rounded-3xl p-6 shadow-lg">
                  <h3 className="text-xs uppercase tracking-wider font-semibold text-slate-500 mb-4">Kart Bilgileri</h3>
                  <div className="space-y-4">
                    <div>
                      <div className="text-[11px] text-slate-400 uppercase tracking-wide">Kart Adı</div>
                      <div className="text-slate-200 font-medium">{selectedCard.name}</div>
                    </div>
                    <div>
                      <div className="text-[11px] text-slate-400 uppercase tracking-wide">Kart Türü</div>
                      <div className="text-slate-200 font-medium">
                        {selectedCard.isDigital ? 'Dijital Kart' : 'Fiziksel Kart'}
                      </div>
                    </div>
                    {selectedCard.limit > 0 && (
                      <div>
                        <div className="text-[11px] text-slate-400 uppercase tracking-wide">Kart Limiti</div>
                        <div className="text-slate-200 font-medium">
                          {selectedCard.limit.toLocaleString('tr-TR', { style: 'currency', currency: 'TRY' })}
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                <div className="bg-slate-900/40 backdrop-blur-xl border border-white/5 rounded-3xl p-6 shadow-lg">
                  <h3 className="text-xs uppercase tracking-wider font-semibold text-slate-500 mb-4">Kart Ayarları</h3>
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="text-slate-200 font-medium">İnternet Alışverişi</div>
                        <div className="text-xs text-slate-400">Online ödemelere izin ver</div>
                      </div>
                      <div 
                        onClick={() => updateCard(selectedCard.id, { settings: { onlineShopping: !(selectedCard.settings?.onlineShopping !== false) } })}
                        className={`w-12 h-6 rounded-full p-1 cursor-pointer transition-colors ${selectedCard.settings?.onlineShopping !== false ? 'bg-brandBlue' : 'bg-slate-700'}`}>
                        <div className={`w-4 h-4 rounded-full bg-white transition-transform ${selectedCard.settings?.onlineShopping !== false ? 'translate-x-6' : 'translate-x-0'}`}></div>
                      </div>
                    </div>
                    {!selectedCard.isDigital && (
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="text-slate-200 font-medium">Temassız Ödeme</div>
                          <div className="text-xs text-slate-400">POS cihazlarında temassız kullan</div>
                        </div>
                        <div 
                          onClick={() => updateCard(selectedCard.id, { settings: { contactless: !(selectedCard.settings?.contactless !== false) } })}
                          className={`w-12 h-6 rounded-full p-1 cursor-pointer transition-colors ${selectedCard.settings?.contactless !== false ? 'bg-brandBlue' : 'bg-slate-700'}`}>
                          <div className={`w-4 h-4 rounded-full bg-white transition-transform ${selectedCard.settings?.contactless !== false ? 'translate-x-6' : 'translate-x-0'}`}></div>
                        </div>
                      </div>
                    )}
                    <div className="flex items-center justify-between pt-2 border-t border-white/10">
                      <div>
                        <div className="text-rose-400 font-medium">Kartı Dondur</div>
                        <div className="text-xs text-slate-400">Geçici olarak kullanıma kapat</div>
                      </div>
                      <div 
                        onClick={() => updateCard(selectedCard.id, { settings: { isFrozen: !selectedCard.settings?.isFrozen } })}
                        className={`w-12 h-6 rounded-full p-1 cursor-pointer transition-colors ${selectedCard.settings?.isFrozen ? 'bg-rose-500' : 'bg-slate-700'}`}>
                        <div className={`w-4 h-4 rounded-full bg-white transition-transform ${selectedCard.settings?.isFrozen ? 'translate-x-6' : 'translate-x-0'}`}></div>
                      </div>
                    </div>
                    
                    <button 
                      onClick={() => setIsSettingsModalOpen(true)}
                      className="w-full mt-2 py-3 bg-white/5 hover:bg-white/10 border border-white/10 rounded-xl text-slate-300 text-sm font-medium transition-colors flex items-center justify-center gap-2"
                    >
                      <span>Tüm Kart Ayarları</span>
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                    </button>
                  </div>
                </div>

                <div className="bg-slate-900/40 backdrop-blur-xl border border-white/5 rounded-3xl p-6 shadow-lg md:col-span-2">
                  <h3 className="text-xs uppercase tracking-wider font-semibold text-slate-500 mb-4">Finansal Durum</h3>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    {selectedCard.limit > 0 ? (
                      <>
                        <div>
                          <div className="text-[11px] text-rose-400 uppercase tracking-wide font-bold">Güncel Borç</div>
                          <div className="text-rose-300 font-medium">
                            {selectedCard.currentDebt.toLocaleString('tr-TR', { style: 'currency', currency: 'TRY' })}
                          </div>
                        </div>
                        <div>
                          <div className="text-[11px] text-emerald-400 uppercase tracking-wide font-bold">Kullanılabilir Limit</div>
                          <div className="text-emerald-300 font-medium">
                            {selectedCard.availableLimit.toLocaleString('tr-TR', { style: 'currency', currency: 'TRY' })}
                          </div>
                        </div>
                        <div>
                          <div className="text-[11px] text-slate-400 uppercase tracking-wide">Son Ödeme Tarihi</div>
                          <div className="text-slate-200 font-medium">{selectedCard.dueDate}</div>
                        </div>
                      </>
                    ) : (
                      <div className="text-sm text-slate-400 sm:col-span-3">
                        Banka kartınızın limiti doğrudan bağlı olduğu vadesiz hesabınızın bakiyesidir.
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="h-full min-h-[400px] bg-slate-900/20 backdrop-blur-md border border-white/5 rounded-3xl flex items-center justify-center p-8 text-center text-slate-400">
              Detaylarını görmek için soldan bir kart seçin.
            </div>
          )}
        </div>
      </div>
      
      <CardSettingsModal 
        isOpen={isSettingsModalOpen} 
        onClose={() => setIsSettingsModalOpen(false)} 
        card={selectedCard || null} 
        updateCard={updateCard}
      />
    </div>
  )
}
