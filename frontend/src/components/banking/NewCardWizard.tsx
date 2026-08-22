import { useState } from 'react'
import { useNavigate, useOutletContext } from 'react-router-dom'
import { BankingContextType } from '../../pages/Banking'

export default function NewCardWizard() {
  const navigate = useNavigate()
  const { data, handleCardCreate } = useOutletContext<BankingContextType>()
  const accounts = data.accounts
  
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1)

  // Step 1
  const [cardType, setCardType] = useState<'credit' | 'debit' | null>(null)
  
  // Step 2
  const [isDigital, setIsDigital] = useState<boolean>(true)
  const [brand, setBrand] = useState<'mastercard' | 'visa'>('mastercard')
  const [cardName, setCardName] = useState<string>('')
  
  // Step 3
  const [limit, setLimit] = useState<number>(10000)
  const [linkedAccountId, setLinkedAccountId] = useState<string>(accounts[0]?.id || '')

  const handleNext = () => {
    if (step < 3) setStep((prev) => (prev + 1) as 1 | 2 | 3 | 4)
  }
  
  const handleBack = () => {
    if (step > 1) setStep(s => (s - 1) as any)
    else navigate('/banking/cards')
  }

  const handleConfirm = () => {
    if (!cardType) return
    handleCardCreate(
      cardType, 
      brand, 
      cardType === 'credit' ? limit : 0, 
      isDigital, 
      cardName || (cardType === 'credit' ? 'Yeni Kredi Kartı' : 'Yeni Banka Kartı'), 
      cardType === 'debit' ? linkedAccountId : undefined
    )
    setStep(4)
  }

  const isStep1Valid = cardType !== null
  const isStep2Valid = cardName.trim().length > 0
  const isStep3Valid = cardType === 'credit' ? limit >= 1000 : !!linkedAccountId

  return (
    <div className="w-full max-w-6xl mx-auto flex flex-col gap-6 animate-fade-in-up">
      {/* Header & Stepper */}
      <div className="bg-slate-900/40 backdrop-blur-xl border border-white/5 rounded-3xl p-6 shadow-xl">
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-4">
            <button onClick={handleBack} className="p-2 hover:bg-white/10 rounded-full transition-colors">
              <svg className="w-6 h-6 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
            </button>
            <h2 className="text-2xl font-bold tracking-tight text-white/90">Yeni Kart Başvurusu</h2>
          </div>
        </div>

        <div className="flex w-full items-center justify-between gap-2 overflow-x-auto pb-4">
          {[
            { num: 1, title: 'KART TİPİ' },
            { num: 2, title: 'KART ÖZELLİKLERİ' },
            { num: 3, title: 'LİMİT / HESAP SEÇİMİ' }
          ].map((s) => (
            <div 
              key={s.num} 
              className={`flex-1 flex items-center justify-center gap-3 py-4 px-6 rounded-xl border whitespace-nowrap cursor-pointer transition-all ${
                step === s.num 
                  ? 'bg-brandBlue border-brandBlue text-white shadow-lg shadow-brandBlue/20'
                  : step > s.num 
                    ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                    : 'bg-slate-800/50 border-white/5 text-slate-400'
              }`}
              onClick={() => {
                if (s.num < step) setStep(s.num as 1 | 2 | 3 | 4)
              }}
            >
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                step === s.num ? 'bg-white text-brandBlue' : step > s.num ? 'bg-emerald-500/20 text-emerald-400' : 'bg-slate-700 text-slate-300'
              }`}>
                {step > s.num ? '✓' : s.num}
              </div>
              <span className="font-semibold tracking-wide text-sm">{s.title}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Step Content */}
      <div className={`backdrop-blur-xl border border-white/5 rounded-3xl p-8 shadow-xl ${step === 4 ? 'bg-emerald-500/10 border-emerald-500/30 text-center py-16' : 'bg-slate-900/40'}`}>
        
        {step === 4 && (
          <div className="flex flex-col items-center justify-center space-y-6 animate-fade-in-up">
            <div className="w-24 h-24 bg-emerald-500/20 rounded-full flex items-center justify-center shadow-lg shadow-emerald-500/20 mb-4">
              <svg className="w-12 h-12 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h2 className="text-3xl font-bold text-white tracking-tight">Kart Başvurunuz Alınmıştır</h2>
            <p className="text-slate-400 max-w-md mx-auto text-lg">
              {isDigital ? "Dijital kartınız anında oluşturuldu. Hemen kullanmaya başlayabilirsiniz." : "Fiziksel kart başvurunuz alınmıştır. Kartınız onaylandıktan sonra adresinize kurye ile teslim edilecektir."}
            </p>
            <button 
              onClick={() => navigate('/banking/cards')}
              className="mt-8 bg-white/10 hover:bg-white/20 text-white font-bold py-4 px-12 rounded-xl transition-all shadow-lg border border-white/10"
            >
              Kartlarıma Dön
            </button>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-8 animate-fade-in-up">
            <div className="text-center mb-6">
              <h3 className="text-2xl font-bold text-white mb-2">Kart Tipini Seçin</h3>
              <p className="text-slate-400">İhtiyacınıza uygun olan kart tipini belirleyin.</p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <button
                onClick={() => setCardType('credit')}
                className={`p-8 rounded-2xl border text-left transition-all relative overflow-hidden ${
                  cardType === 'credit'
                    ? 'bg-brandBlue/10 border-brandBlue shadow-lg shadow-brandBlue/10'
                    : 'bg-white/5 border-transparent hover:bg-white/10'
                }`}
              >
                <div className="w-16 h-16 bg-blue-500/20 text-blue-400 rounded-2xl flex items-center justify-center mb-6">
                  <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
                  </svg>
                </div>
                <h4 className="text-xl font-bold text-white mb-2">Kredi Kartı</h4>
                <p className="text-slate-400 text-sm leading-relaxed">Limitiniz dahilinde harcama yapın, taksitli alışveriş imkanlarından faydalanın.</p>
                {cardType === 'credit' && (
                  <div className="absolute top-6 right-6 w-8 h-8 bg-brandBlue rounded-full flex items-center justify-center text-white">
                    ✓
                  </div>
                )}
              </button>
              
              <button
                onClick={() => setCardType('debit')}
                className={`p-8 rounded-2xl border text-left transition-all relative overflow-hidden ${
                  cardType === 'debit'
                    ? 'bg-brandBlue/10 border-brandBlue shadow-lg shadow-brandBlue/10'
                    : 'bg-white/5 border-transparent hover:bg-white/10'
                }`}
              >
                <div className="w-16 h-16 bg-emerald-500/20 text-emerald-400 rounded-2xl flex items-center justify-center mb-6">
                  <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <h4 className="text-xl font-bold text-white mb-2">Banka Kartı</h4>
                <p className="text-slate-400 text-sm leading-relaxed">Vadesiz hesabınızdaki bakiyeyi kullanarak harcama yapın, ATM'lerden nakit çekin.</p>
                {cardType === 'debit' && (
                  <div className="absolute top-6 right-6 w-8 h-8 bg-brandBlue rounded-full flex items-center justify-center text-white">
                    ✓
                  </div>
                )}
              </button>
            </div>
            <div className="flex justify-end pt-6 border-t border-white/10 mt-8">
              <button
                onClick={handleNext}
                disabled={!isStep1Valid}
                className="bg-brandBlue hover:bg-blue-600 disabled:bg-slate-700 disabled:text-slate-500 text-white px-10 py-4 rounded-xl font-bold transition-all shadow-lg"
              >
                Devam Et
              </button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-8 animate-fade-in-up">
            <div className="text-center mb-6">
              <h3 className="text-2xl font-bold text-white mb-2">Kart Özellikleri</h3>
              <p className="text-slate-400">Kartınızın ismi, türü ve ödeme altyapısını belirleyin.</p>
            </div>
            
            <div className="max-w-2xl mx-auto space-y-8">
              {/* Kart İsmi */}
              <div className="space-y-3">
                <label className="text-sm font-medium text-slate-300">Kart İsmi</label>
                <input 
                  type="text" 
                  value={cardName}
                  onChange={e => setCardName(e.target.value)}
                  placeholder="Örn: İnternet Alışveriş Kartım"
                  className="w-full bg-[#1c1c1e] border border-white/10 rounded-xl px-4 py-4 text-white placeholder-slate-500 focus:outline-none focus:border-brandBlue focus:ring-1 focus:ring-brandBlue transition-all text-lg"
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                {/* Kullanım Türü */}
                <div className="space-y-3">
                  <label className="text-sm font-medium text-slate-300">Kullanım Türü</label>
                  <div className="grid grid-cols-1 gap-3">
                    <button
                      onClick={() => setIsDigital(true)}
                      className={`p-4 rounded-xl border ${isDigital ? 'border-brandBlue bg-brandBlue/10 text-white' : 'border-white/10 bg-[#1c1c1e] text-slate-400'} transition-all flex items-center justify-between`}
                    >
                      <div className="flex flex-col items-start text-left">
                        <span className="font-bold">Dijital Kart</span>
                        <span className="text-xs opacity-70">Anında kullanıma hazır</span>
                      </div>
                      {isDigital && <span className="text-brandBlue font-bold">✓</span>}
                    </button>
                    <button
                      onClick={() => setIsDigital(false)}
                      className={`p-4 rounded-xl border ${!isDigital ? 'border-brandBlue bg-brandBlue/10 text-white' : 'border-white/10 bg-[#1c1c1e] text-slate-400'} transition-all flex items-center justify-between`}
                    >
                      <div className="flex flex-col items-start text-left">
                        <span className="font-bold">Fiziksel Kart</span>
                        <span className="text-xs opacity-70">Adrese kurye teslim</span>
                      </div>
                      {!isDigital && <span className="text-brandBlue font-bold">✓</span>}
                    </button>
                  </div>
                </div>

                {/* Marka */}
                <div className="space-y-3">
                  <label className="text-sm font-medium text-slate-300">Ödeme Altyapısı</label>
                  <div className="grid grid-cols-1 gap-3">
                    <button
                      onClick={() => setBrand('mastercard')}
                      className={`p-4 rounded-xl border ${brand === 'mastercard' ? 'border-brandBlue bg-brandBlue/10 text-white' : 'border-white/10 bg-[#1c1c1e] text-slate-400'} transition-all flex items-center justify-between`}
                    >
                      <span className="font-bold">Mastercard</span>
                      {brand === 'mastercard' && <span className="text-brandBlue font-bold">✓</span>}
                    </button>
                    <button
                      onClick={() => setBrand('visa')}
                      className={`p-4 rounded-xl border ${brand === 'visa' ? 'border-brandBlue bg-brandBlue/10 text-white' : 'border-white/10 bg-[#1c1c1e] text-slate-400'} transition-all flex items-center justify-between`}
                    >
                      <span className="font-bold">Visa</span>
                      {brand === 'visa' && <span className="text-brandBlue font-bold">✓</span>}
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div className="flex justify-between pt-6 border-t border-white/10 mt-8">
              <button
                onClick={handleBack}
                className="bg-transparent border border-white/20 hover:bg-white/5 text-white px-8 py-4 rounded-xl font-bold transition-all"
              >
                Geri
              </button>
              <button
                onClick={handleNext}
                disabled={!isStep2Valid}
                className="bg-brandBlue hover:bg-blue-600 disabled:bg-slate-700 disabled:text-slate-500 text-white px-10 py-4 rounded-xl font-bold transition-all shadow-lg"
              >
                Devam Et
              </button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-8 animate-fade-in-up">
            <div className="text-center mb-6">
              <h3 className="text-2xl font-bold text-white mb-2">
                {cardType === 'credit' ? 'Limit Belirleme' : 'Hesap Seçimi'}
              </h3>
              <p className="text-slate-400">
                {cardType === 'credit' ? 'Kredi kartınızın başlangıç limitini belirleyin.' : 'Banka kartınızın bağlanacağı vadesiz hesabı seçin.'}
              </p>
            </div>
            
            <div className="max-w-2xl mx-auto space-y-8">
              {cardType === 'credit' && (
                <div className="space-y-6">
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium text-slate-300">İstenen Limit</label>
                    <span className="text-2xl font-bold text-white">{limit.toLocaleString('tr-TR')} ₺</span>
                  </div>
                  <input
                    type="range"
                    min="1000"
                    max="100000"
                    step="1000"
                    value={limit}
                    onChange={e => setLimit(Number(e.target.value))}
                    className="w-full h-3 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-brandBlue"
                  />
                  <div className="flex justify-between text-xs text-slate-500 font-medium">
                    <span>1.000 ₺</span>
                    <span>100.000 ₺</span>
                  </div>
                </div>
              )}

              {cardType === 'debit' && (
                <div className="space-y-4">
                  <label className="text-sm font-medium text-slate-300">Bağlanacak Vadesiz Hesap</label>
                  <div className="space-y-3">
                    {accounts.map(acc => (
                      <button
                        key={acc.id}
                        onClick={() => setLinkedAccountId(acc.id)}
                        className={`w-full p-6 rounded-2xl border text-left transition-all flex items-center justify-between ${
                          linkedAccountId === acc.id
                            ? 'bg-brandBlue/10 border-brandBlue shadow-lg shadow-brandBlue/10'
                            : 'bg-white/5 border-transparent hover:bg-white/10'
                        }`}
                      >
                        <div>
                          <h4 className="text-lg font-bold text-white">{acc.name}</h4>
                          <p className="text-slate-400 font-mono text-sm mt-1">{acc.accountNumber}</p>
                        </div>
                        <div className="text-right">
                          <span className="text-xl font-bold text-white">
                            {acc.balance.toLocaleString('tr-TR', { style: 'currency', currency: 'TRY' })}
                          </span>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="flex justify-between pt-6 border-t border-white/10 mt-8">
              <button
                onClick={handleBack}
                className="bg-transparent border border-white/20 hover:bg-white/5 text-white px-8 py-4 rounded-xl font-bold transition-all"
              >
                Geri
              </button>
              <button
                onClick={handleConfirm}
                disabled={!isStep3Valid}
                className="bg-brandBlue hover:bg-blue-600 disabled:bg-slate-700 disabled:text-slate-500 text-white px-10 py-4 rounded-xl font-bold transition-all shadow-lg"
              >
                Başvuruyu Tamamla
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
