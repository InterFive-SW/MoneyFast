import React, { useState } from 'react'
import { useNavigate, useOutletContext } from 'react-router-dom'
import { BankingContextType } from '../../pages/Banking'

export default function NewAccountWizard() {
  const navigate = useNavigate()
  const { handleAccountCreate } = useOutletContext<BankingContextType>()
  
  const [step, setStep] = useState<1 | 2 | 3 | 4 | 5>(1)
  
  // Form State
  const [accountType, setAccountType] = useState<'checking' | 'savings'>('checking')
  const [currency, setCurrency] = useState<'TRY' | 'USD' | 'EUR' | 'GBP'>('TRY')
  const [accountName, setAccountName] = useState('')
  const [acceptedTerms, setAcceptedTerms] = useState(false)

  const handleNext = () => setStep(s => (s + 1) as any)
  const handleBack = () => {
    if (step > 1) setStep(s => (s - 1) as any)
    else navigate('/banking')
  }

  const handleCreate = () => {
    // Hesabı Oluştur butonu zaten acceptedTerms false iken disabled oluyor,
    // bu koruma UI üzerinden testle ulaşılamıyor.
    /* v8 ignore next */
    if (!acceptedTerms) return
    const fakeIban = `TR${Math.floor(Math.random() * 90 + 10)} 0006 2001 0450 0006 6677 ${Math.floor(Math.random() * 90 + 10)}`
    handleAccountCreate(
      currency,
      accountType,
      accountName || `${currency} ${accountType === 'checking' ? 'Vadesiz' : 'Vadeli'} Hesap`,
      fakeIban
    )
    setStep(5) // Başarı Ekranı
  }

  return (
    <div className="w-full max-w-4xl mx-auto flex flex-col gap-6 animate-fade-in-up">
      {/* Üst Navigasyon & Geri Butonu */}
      <div className="flex items-center justify-between">
        <button
          onClick={handleBack}
          className="group flex items-center gap-2 px-4 py-2 bg-slate-900/50 hover:bg-slate-800/80 backdrop-blur-md border border-white/5 rounded-xl transition-all"
        >
          <svg className="w-5 h-5 text-slate-400 group-hover:text-white transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          <span className="text-slate-300 font-medium group-hover:text-white transition-colors">
            {step === 1 ? 'Menüye Dön' : 'Geri'}
          </span>
        </button>

        <h2 className="text-xl font-bold tracking-tight text-white/90">Yeni Hesap Aç</h2>
      </div>

      {/* İlerleme Çubuğu (Step 5 Hariç) */}
      {step < 5 && (
        <div className="flex items-center justify-center gap-2 mb-4">
          {[1, 2, 3, 4].map(s => (
            <div key={s} className="flex items-center">
              <div className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold transition-all ${
                step === s 
                  ? 'bg-brandBlue text-white shadow-lg shadow-brandBlue/20 scale-110' 
                  : step > s 
                    ? 'bg-brandBlue/20 text-brandBlue' 
                    : 'bg-slate-800 text-slate-500'
              }`}>
                {step > s ? '✓' : s}
              </div>
              {s < 4 && (
                <div className={`w-16 h-1 mx-2 rounded-full transition-all ${
                  step > s ? 'bg-brandBlue/40' : 'bg-slate-800'
                }`} />
              )}
            </div>
          ))}
        </div>
      )}

      {/* Step İçerikleri */}
      <div className="bg-slate-900/40 backdrop-blur-xl border border-white/5 rounded-3xl p-8 shadow-2xl relative overflow-hidden">
        
        {step === 1 && (
          <div className="flex flex-col gap-8 animate-fade-in">
            <div className="text-center">
              <h3 className="text-2xl font-bold text-white mb-2">Hesap Türünü Seçin</h3>
              <p className="text-slate-400">İhtiyacınıza en uygun hesap türünü belirleyin.</p>
            </div>
            
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              <button
                onClick={() => setAccountType('checking')}
                className={`p-6 rounded-2xl border text-left transition-all ${
                  accountType === 'checking'
                    ? 'bg-brandBlue/10 border-brandBlue/50 shadow-lg shadow-brandBlue/10'
                    : 'bg-white/5 border-transparent hover:bg-white/10'
                }`}
              >
                <div className="w-12 h-12 bg-blue-500/20 text-blue-400 rounded-xl flex items-center justify-center mb-4">
                  <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
                  </svg>
                </div>
                <h4 className="text-lg font-bold text-white mb-2">Vadesiz Hesap</h4>
                <p className="text-sm text-slate-400 leading-relaxed">
                  Günlük bankacılık işlemleriniz, para transferleriniz ve fatura ödemeleriniz için kullanabileceğiniz vadesiz hesabınız.
                </p>
              </button>

              <button
                onClick={() => setAccountType('savings')}
                className={`p-6 rounded-2xl border text-left transition-all ${
                  accountType === 'savings'
                    ? 'bg-brandBlue/10 border-brandBlue/50 shadow-lg shadow-brandBlue/10'
                    : 'bg-white/5 border-transparent hover:bg-white/10'
                }`}
              >
                <div className="w-12 h-12 bg-emerald-500/20 text-emerald-400 rounded-xl flex items-center justify-center mb-4">
                  <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <h4 className="text-lg font-bold text-white mb-2">Vadeli Hesap</h4>
                <p className="text-sm text-slate-400 leading-relaxed">
                  Birikimlerinizi değerlendirebileceğiniz, yüksek faiz oranlarıyla kazancınızı artırabileceğiniz vadeli hesabınız.
                </p>
              </button>
            </div>
            
            <button
              onClick={handleNext}
              className="mt-4 w-full bg-brandBlue hover:bg-blue-600 text-white font-bold py-4 rounded-xl transition-all shadow-lg shadow-brandBlue/20"
            >
              Devam Et
            </button>
          </div>
        )}

        {step === 2 && (
          <div className="flex flex-col gap-8 animate-fade-in">
            <div className="text-center">
              <h3 className="text-2xl font-bold text-white mb-2">Para Birimi Seçimi</h3>
              <p className="text-slate-400">Hesabınızın hangi para biriminde olacağını seçin.</p>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              {[
                { code: 'TRY', name: 'Türk Lirası', symbol: '₺' },
                { code: 'USD', name: 'Amerikan Doları', symbol: '$' },
                { code: 'EUR', name: 'Euro', symbol: '€' },
                { code: 'GBP', name: 'İngiliz Sterlini', symbol: '£' },
              ].map(curr => (
                <button
                  key={curr.code}
                  onClick={() => setCurrency(curr.code as any)}
                  className={`p-4 rounded-2xl border flex flex-col items-center justify-center gap-3 transition-all ${
                    currency === curr.code
                      ? 'bg-brandBlue/10 border-brandBlue/50 shadow-lg shadow-brandBlue/10'
                      : 'bg-white/5 border-transparent hover:bg-white/10'
                  }`}
                >
                  <div className={`w-12 h-12 rounded-full flex items-center justify-center text-xl font-bold ${
                    currency === curr.code ? 'bg-brandBlue text-white' : 'bg-slate-800 text-slate-400'
                  }`}>
                    {curr.symbol}
                  </div>
                  <div className="text-center">
                    <div className={`font-bold ${currency === curr.code ? 'text-white' : 'text-slate-300'}`}>{curr.code}</div>
                    <div className="text-[10px] text-slate-500 uppercase tracking-wide mt-1">{curr.name}</div>
                  </div>
                </button>
              ))}
            </div>
            
            <button
              onClick={handleNext}
              className="mt-4 w-full bg-brandBlue hover:bg-blue-600 text-white font-bold py-4 rounded-xl transition-all shadow-lg shadow-brandBlue/20"
            >
              Devam Et
            </button>
          </div>
        )}

        {step === 3 && (
          <div className="flex flex-col gap-8 animate-fade-in">
            <div className="text-center">
              <h3 className="text-2xl font-bold text-white mb-2">Hesap İsimlendirme</h3>
              <p className="text-slate-400">Hesabınızı kolayca tanıyabilmek için bir isim verin (Opsiyonel).</p>
            </div>

            <div className="max-w-md mx-auto w-full">
              <label className="block text-sm font-medium text-slate-400 mb-2">Hesap Adı</label>
              <input 
                type="text" 
                value={accountName}
                onChange={(e) => setAccountName(e.target.value)}
                placeholder={`Örn: ${currency} ${accountType === 'checking' ? 'Vadesiz' : 'Vadeli'} Birikim`}
                className="w-full bg-slate-900/50 border border-white/10 rounded-xl px-4 py-4 text-white placeholder-slate-500 focus:outline-none focus:border-brandBlue/50 focus:ring-1 focus:ring-brandBlue/50 transition-all text-lg"
              />
            </div>
            
            <button
              onClick={handleNext}
              className="mt-4 w-full bg-brandBlue hover:bg-blue-600 text-white font-bold py-4 rounded-xl transition-all shadow-lg shadow-brandBlue/20"
            >
              Devam Et
            </button>
          </div>
        )}

        {step === 4 && (
          <div className="flex flex-col gap-8 animate-fade-in">
            <div className="text-center">
              <h3 className="text-2xl font-bold text-white mb-2">Sözleşme ve Onay</h3>
              <p className="text-slate-400">Lütfen hesap açılışı için gerekli sözleşmeleri onaylayın.</p>
            </div>

            <div className="bg-slate-900/50 border border-white/5 rounded-2xl p-6">
              <h4 className="text-lg font-semibold text-white mb-4">Hesap Özeti</h4>
              <div className="space-y-3 mb-6">
                <div className="flex justify-between items-center py-2 border-b border-white/5">
                  <span className="text-slate-400">Hesap Türü</span>
                  <span className="text-white font-medium capitalize">{accountType === 'checking' ? 'Vadesiz Hesap' : 'Vadeli Hesap'}</span>
                </div>
                <div className="flex justify-between items-center py-2 border-b border-white/5">
                  <span className="text-slate-400">Para Birimi</span>
                  <span className="text-white font-medium">{currency}</span>
                </div>
                <div className="flex justify-between items-center py-2 border-b border-white/5">
                  <span className="text-slate-400">Hesap Adı</span>
                  <span className="text-white font-medium">{accountName || `${currency} ${accountType === 'checking' ? 'Vadesiz' : 'Vadeli'} Hesap`}</span>
                </div>
              </div>

              <label className="flex items-start gap-4 cursor-pointer group">
                <div className="relative flex items-center justify-center mt-1">
                  <input 
                    type="checkbox" 
                    checked={acceptedTerms}
                    onChange={(e) => setAcceptedTerms(e.target.checked)}
                    className="sr-only"
                  />
                  <div className={`w-6 h-6 rounded border flex items-center justify-center transition-all ${
                    acceptedTerms 
                      ? 'bg-brandBlue border-brandBlue' 
                      : 'bg-slate-800 border-white/20 group-hover:border-brandBlue/50'
                  }`}>
                    {acceptedTerms && (
                      <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                      </svg>
                    )}
                  </div>
                </div>
                <div className="text-sm text-slate-300 leading-relaxed">
                  <a href="#" className="text-brandBlue hover:underline">Temel Bankacılık Hizmet Sözleşmesi</a>'ni ve <a href="#" className="text-brandBlue hover:underline">Aydınlatma Metni</a>'ni okudum, anladım ve onaylıyorum.
                </div>
              </label>
            </div>
            
            <button
              onClick={handleCreate}
              disabled={!acceptedTerms}
              className={`mt-4 w-full font-bold py-4 rounded-xl transition-all shadow-lg ${
                acceptedTerms 
                  ? 'bg-brandBlue hover:bg-blue-600 text-white shadow-brandBlue/20' 
                  : 'bg-slate-800 text-slate-500 cursor-not-allowed'
              }`}
            >
              Hesabı Oluştur
            </button>
          </div>
        )}

        {step === 5 && (
          <div className="flex flex-col items-center text-center gap-6 animate-fade-in py-12">
            <div className="w-24 h-24 bg-emerald-500/20 rounded-full flex items-center justify-center mb-4 relative">
              <div className="absolute inset-0 bg-emerald-500/20 rounded-full animate-ping opacity-75"></div>
              <svg className="w-12 h-12 text-emerald-400 relative z-10" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            
            <div>
              <h3 className="text-3xl font-extrabold text-white tracking-tight mb-2">Tebrikler!</h3>
              <p className="text-slate-400 text-lg">
                Yeni {accountType === 'checking' ? 'Vadesiz' : 'Vadeli'} {currency} hesabınız başarıyla oluşturuldu.
              </p>
            </div>
            
            <button 
              onClick={() => navigate('/banking/accounts')}
              className="mt-8 bg-white/10 hover:bg-white/20 text-white font-bold py-4 px-12 rounded-xl transition-all shadow-lg border border-white/10"
            >
              Hesaplarıma Git
            </button>
          </div>
        )}

      </div>
    </div>
  )
}
