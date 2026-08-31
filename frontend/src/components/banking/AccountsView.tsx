import React from 'react'
import { useState } from 'react'
import { useNavigate, useOutletContext } from 'react-router-dom'
import { BankingContextType } from '../../pages/Banking'
import type { BankAccount } from '../../data/mockBankingData'
import { apiClient } from '../../api/client'

/**
 * AccountsView Bileşeni
 * 
 * Kullanıcının hesaplarını detaylı olarak inceleyebildiği, Bento Grid yapısında tasarlanmış,
 * Premium Dark Mode'a uygun hesap detay ekranıdır. 
 * "Hesaplarım" seçildiğinde bu bileşen aktif olur.
 */

/**
 * Hesap türünün ekranda görünen adı.
 *
 * Eskiden iki dallı bir üçlü operatördü ve son dalı `'Döviz'`di: `checking` ve
 * `savings` dışındaki HER tür oradan düşüyordu, dolayısıyla yatırım hesabı
 * "Döviz" diye etiketleniyordu. Tanınmayan bir tür artık `—` gösterir --
 * bilinmediğini söylemek, son dalın cevabını vermekten iyidir.
 */
const ACCOUNT_TYPE_LABELS: Record<BankAccount['type'], string> = {
  checking: 'Vadesiz',
  savings: 'Vadeli',
  investment: 'Yatırım',
  foreign_currency: 'Döviz',
}

export default function AccountsView() {
  const navigate = useNavigate()
  const { data, openFeatureNotReadyModal } = useOutletContext<BankingContextType>()
  const accounts = data.accounts

  // Varsayılan olarak ilk hesabı seçili yapıyoruz
  const [selectedAccountId, setSelectedAccountId] = useState<string>(accounts[0]?.id || '')

  /**
   * Hesap sahibi, oturumdaki kullanıcının kendisi.
   *
   * Bu iki alan sabit yazılıydı: adı "Bireysel Müşteri", müşteri numarası
   * `84938201`. İkincisi daha kötüsüydü -- her müşteride aynı olan bir
   * "müşteri numarası", müşteriyi ayırt etmeyen bir numaradır.
   */
  const [holder, setHolder] = useState<{ name: string; customerNo: string } | null>(null)

  React.useEffect(() => {
    let cancelled = false
    void apiClient
      .getCurrentUser()
      .then((user) => {
        if (cancelled) return
        setHolder({
          name: `${user.first_name} ${user.last_name}`.trim(),
          customerNo: user.customer_no ?? '—',
        })
      })
      // Kimlik alınamazsa alanlar boş görünür. Sabit bir isim yazmak, o ismi
      // doğrulanmış bir bilgi gibi göstermek olurdu.
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])

  // Yeni bir hesap eklendiğinde onu otomatik seç
  const prevLengthRef = React.useRef(accounts.length)
  React.useEffect(() => {
    if (accounts.length > prevLengthRef.current) {
      // Diziye yeni eleman eklendi, sonuncuyu (yeni olanı) seç
      const newAccount = accounts[accounts.length - 1]
      if (newAccount) {
        setSelectedAccountId(newAccount.id)
      }
    }
    prevLengthRef.current = accounts.length
  }, [accounts.length, accounts])

  const selectedAccount = accounts.find(a => a.id === selectedAccountId)

  // Toplam varlık hesaplaması (sadece gösterim amaçlı, mock data'dan da gelebilirdi)

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

        <h2 className="text-xl font-bold tracking-tight text-white/90">Hesaplarım</h2>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Sol Kolon: Hesap Listesi */}
        <div className="lg:col-span-4 flex flex-col gap-4">
          <div className="bg-slate-900/40 backdrop-blur-xl border border-white/5 rounded-3xl p-6 shadow-xl flex flex-col gap-6">
            
            <div className="flex items-center justify-between">
              <h3 className="text-sm uppercase tracking-wider font-semibold text-slate-400">Tüm Hesaplar</h3>
              <span className="text-xs font-medium text-brandBlue bg-brandBlue/10 px-2 py-1 rounded-md">
                {accounts.length} Hesap
              </span>
            </div>

            {/* Hesap Kartları */}
            <div className="flex flex-col gap-3">
              {accounts.map(acc => {
                const isSelected = acc.id === selectedAccountId
                return (
                  <button
                    key={acc.id}
                    onClick={() => setSelectedAccountId(acc.id)}
                    className={`text-left w-full p-4 rounded-2xl transition-all duration-300 border ${
                      isSelected 
                        ? 'bg-gradient-to-br from-brandBlue/20 to-blue-900/20 border-brandBlue/50 shadow-lg shadow-brandBlue/10'
                        : 'bg-white/5 hover:bg-white/10 border-transparent'
                    }`}
                  >
                    <div className="flex justify-between items-start mb-2">
                      <span className={`font-semibold ${isSelected ? 'text-white' : 'text-slate-300'}`}>
                        {acc.name}
                      </span>
                      {acc.type === 'savings' && (
                        <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-400 bg-emerald-400/10 px-2 py-0.5 rounded">Vadeli</span>
                      )}
                    </div>
                    <div className={`text-sm ${isSelected ? 'text-blue-200' : 'text-slate-400'}`}>
                      {acc.balance.toLocaleString('tr-TR', { style: 'currency', currency: acc.currency })}
                    </div>
                  </button>
                )
              })}
            </div>

            {/*
              Yeni Hesap Aç.

              Sihirbaza değil "yakında" kutusuna gidiyor: backend'de hesap
              açma ucu yok, sihirbaz hesabı yalnızca bu bileşenin state'ine
              ekliyordu. Hesaplar artık gerçek olduğu için o sahte satır
              listede gerçeklerin yanında duruyor ve ilk tazelemede
              kayboluyordu — kullanıcıya "başarıyla oluşturuldu" deyip hiçbir
              yere yazmamak, özelliği kapatmaktan daha kötü.

              AccountHeroWidget'taki "Ek Hesap Başvurusu" zaten böyle
              davranıyordu; burası ona hizalandı. Uç eklendiğinde
              NewAccountWizard yerinde duruyor, tek satırla geri bağlanır.
            */}
            <button
              onClick={() => openFeatureNotReadyModal('Yeni Hesap Açma')}
              className="mt-2 w-full py-3 border border-dashed border-slate-600 rounded-2xl text-slate-400 font-medium hover:bg-white/5 hover:text-white transition-colors hover:border-slate-500 flex items-center justify-center gap-2"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Yeni Hesap Aç
            </button>
          </div>
        </div>

        {/* Sağ Kolon: Seçili Hesap Detayları (Bento Grid) */}
        <div className="lg:col-span-8 flex flex-col gap-6">
          {selectedAccount ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 h-full">
              
              {/* Hesap Sahibi & Bakiye Bilgisi (Büyük Kart) */}
              <div className="md:col-span-2 bg-gradient-to-br from-slate-900/60 to-slate-800/40 backdrop-blur-xl border border-white/10 rounded-3xl p-8 shadow-2xl relative overflow-hidden group">
                <div className="absolute top-0 right-0 p-12 opacity-5 pointer-events-none group-hover:opacity-10 transition-opacity duration-500">
                  <svg className="w-64 h-64 text-white" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z" />
                  </svg>
                </div>
                
                <h3 className="text-sm uppercase tracking-widest font-semibold text-brandBlue mb-2">Bakiye ve Hareket Bilgileri</h3>
                <div className="text-4xl sm:text-5xl font-extrabold tracking-tight text-white mb-2">
                  {selectedAccount.balance.toLocaleString('tr-TR', { style: 'currency', currency: selectedAccount.currency })}
                </div>
                <div className="text-slate-400 text-sm font-medium">
                  Kullanılabilir Bakiye: <span className="text-slate-300">{selectedAccount.balance.toLocaleString('tr-TR', { style: 'currency', currency: selectedAccount.currency })}</span>
                </div>

                <div className="mt-8 flex flex-col sm:flex-row gap-4">
                  <button 
                    onClick={() => navigate(`/banking/accounts/${selectedAccount.id}/transactions`)}
                    className="flex-1 bg-white hover:bg-slate-100 text-slate-900 font-bold py-3 px-6 rounded-xl transition-all shadow-lg shadow-white/10 flex items-center justify-center gap-2"
                  >
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    Hesap Hareketleri
                  </button>
                  {/* Kapatma da aynı sebeple "yakında": kapatılan hesap
                      tazelemede geri geliyordu. */}
                  <button
                    onClick={() => openFeatureNotReadyModal('Hesap Kapama')}
                    className="flex-1 bg-rose-500/10 border border-rose-500/30 text-rose-400 hover:bg-rose-500/20 font-bold py-3 px-6 rounded-xl transition-all flex items-center justify-center gap-2"
                  >
                    Hesap Kapama
                  </button>
                </div>
              </div>

              {/* Hesap Bilgileri Kutu 1 */}
              <div className="bg-slate-900/40 backdrop-blur-xl border border-white/5 rounded-3xl p-6 shadow-lg">
                <h3 className="text-xs uppercase tracking-wider font-semibold text-slate-500 mb-4 flex items-center gap-2">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Hesap Bilgileri
                </h3>
                
                <div className="flex flex-col gap-4">
                  <div>
                    <div className="text-[11px] text-slate-400 uppercase tracking-wide">Hesap Adı</div>
                    <div className="text-slate-200 font-medium">{selectedAccount.name}</div>
                  </div>
                  <div>
                    <div className="text-[11px] text-slate-400 uppercase tracking-wide">IBAN</div>
                    <div className="text-slate-200 font-mono text-sm tracking-tight">{selectedAccount.accountNumber}</div>
                  </div>
                  <div className="flex justify-between">
                    <div>
                      <div className="text-[11px] text-slate-400 uppercase tracking-wide">Hesap Türü</div>
                      <div className="text-slate-200 font-medium capitalize">
                        {ACCOUNT_TYPE_LABELS[selectedAccount.type] ?? '—'}
                      </div>
                    </div>
                    <div>
                      <div className="text-[11px] text-slate-400 uppercase tracking-wide">Döviz Kodu</div>
                      <div className="text-slate-200 font-medium font-mono">{selectedAccount.currency}</div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Hesap Sahibi / Vadeli Bilgileri Kutu 2 */}
              <div className="bg-slate-900/40 backdrop-blur-xl border border-white/5 rounded-3xl p-6 shadow-lg flex flex-col justify-between">
                <div>
                  <h3 className="text-xs uppercase tracking-wider font-semibold text-slate-500 mb-4 flex items-center gap-2">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                    </svg>
                    Hesap Sahibi
                  </h3>
                  
                  <div className="flex flex-col gap-4">
                    <div>
                      <div className="text-[11px] text-slate-400 uppercase tracking-wide">Ad Soyad</div>
                      <div className="text-slate-200 font-medium">
                        {holder?.name ?? '—'}
                      </div>
                    </div>
                    <div>
                      <div className="text-[11px] text-slate-400 uppercase tracking-wide">Müşteri No</div>
                      <div className="text-slate-200 font-mono text-sm">
                        {holder?.customerNo ?? '—'}
                      </div>
                    </div>
                    
                    {/* Vadeli hesabın oranı ve vadesi -- kayıttan.

                        Bu iki alan sabit metindi (`%42.50`, `32 Gün`) ve
                        arkalarında ne bir sütun ne de bir faiz işletmesi
                        vardı: vadenin sonunda bakiyeye hiçbir şey olmuyordu.
                        Ürün günlük hesaba çevrildi; oran da kaydın kendisi. */}
                    {selectedAccount.type === 'savings' &&
                      selectedAccount.interestRate != null && (
                      <div className="pt-4 mt-2 border-t border-white/5 grid grid-cols-2 gap-4">
                        <div>
                          <div className="text-[11px] text-brandBlue uppercase tracking-wide font-bold">Faiz Oranı</div>
                          <div className="text-slate-200 font-medium tabular-nums">
                            %{selectedAccount.interestRate.toLocaleString('tr-TR', {
                              minimumFractionDigits: 2,
                              maximumFractionDigits: 2,
                            })}
                          </div>
                        </div>
                        <div>
                          <div className="text-[11px] text-brandBlue uppercase tracking-wide font-bold">Vade Süresi</div>
                          <div className="text-slate-200 font-medium tabular-nums">
                            {selectedAccount.termDays != null
                              ? `${selectedAccount.termDays} Gün`
                              : '—'}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>

            </div>
          ) : (
            <div className="h-full bg-slate-900/20 backdrop-blur-md border border-white/5 rounded-3xl flex items-center justify-center p-8 text-center text-slate-400">
              Detaylarını görmek için soldan bir hesap seçin.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

