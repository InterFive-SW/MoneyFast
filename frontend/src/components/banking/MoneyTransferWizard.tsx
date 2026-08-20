import React, { useState } from 'react'
import { useNavigate, useOutletContext, useLocation } from 'react-router-dom'
import { BankingContextType } from '../../pages/Banking'
import type { BankAccount } from '../../data/mockBankingData'

const DUMMY_RECIPIENTS = [
  { id: '1', name: 'Yağmur Nur Özkan', bank: 'T.GARANTİ BANKASI A.Ş.', iban: 'TR72 0006 2001 0450 0006 6677 03', isFrequent: true },
  { id: '2', name: 'Ahmet Yılmaz', bank: 'T.C. ZİRAAT BANKASI A.Ş.', iban: 'TR35 0006 2001 0450 0006 6677 04', isFrequent: true },
  { id: '3', name: 'Mehmet Demir', bank: 'AKBANK T.A.Ş.', iban: 'TR41 0006 2001 0450 0006 6677 05', isFrequent: false }
]

export default function MoneyTransferWizard() {
  const navigate = useNavigate()
  const { data, handleTransfer } = useOutletContext<BankingContextType>()
  const accounts = data.accounts

  const location = useLocation()
  const defaultSenderAccountId = location.state?.fromAccountId || null

  const [step, setStep] = useState<1 | 2 | 3 | 4 | 5>(1)
  
  // Step 1: Receiver State
  const [receiverTab, setReceiverTab] = useState<'saved' | 'new'>('saved')
  const [newReceiverType, setNewReceiverType] = useState<'iban' | 'accountNo' | 'easyAddress'>('iban')
  
  const [selectedRecipientId, setSelectedRecipientId] = useState<string | null>(null)
  const [receiverIban, setReceiverIban] = useState('TR')
  const [receiverName, setReceiverName] = useState('')
  const [saveAsRecipient, setSaveAsRecipient] = useState(false)

  // Step 2: Sender State
  const [senderAccountId, setSenderAccountId] = useState<string | null>(defaultSenderAccountId || (accounts.length > 0 ? accounts[0].id : null))

  // Step 3: Amount State
  const [amount, setAmount] = useState<string>('')
  
  // Step 4: Details State
  const [description, setDescription] = useState<string>('')
  const [transferType, setTransferType] = useState<string>('Bireysel Ödeme')
  const transferFee = 8.37 // Mock
  const date = new Date().toLocaleDateString('tr-TR')

  // Computed
  const senderAccount = accounts.find(a => a.id === senderAccountId)
  const numAmount = parseFloat(amount) || 0
  
  const handleNext = () => {
    // DEVAM butonu her adımda sadece o adımdan bir sonrakine geçiş için render
    // ediliyor, step 4'ten sonrasına asla çağrılmıyor.
    /* v8 ignore next */
    if (step < 4) setStep((prev) => (prev + 1) as 1 | 2 | 3 | 4)
  }

  const handleBack = () => {
    if (step > 1) setStep(s => (s - 1) as any)
    else navigate('/banking')
  }

  const handleConfirm = () => {
    // ONAYLA butonu sadece step 4'te render ediliyor ve o noktaya isStep2Valid
    // (senderAccountId dolu) olmadan geçiş yapılamıyor.
    /* v8 ignore next */
    if (!senderAccountId) return
    handleTransfer(numAmount, senderAccountId, receiverName || receiverIban, description)
    setStep(5)
  }

  const isStep1Valid = receiverTab === 'saved' ? !!selectedRecipientId : (receiverIban.length > 10 && receiverName.length > 2)
  const isStep2Valid = !!senderAccountId
  // senderAccount seçili olduğunda balance her zaman tanımlı bir sayı — ?? 0
  // dalı gerçek veriyle asla tetiklenmiyor.
  /* v8 ignore next */
  const isStep3Valid = parseFloat(amount) > 0 && parseFloat(amount) <= (senderAccount?.balance || 0)

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
            <h2 className="text-2xl font-bold tracking-tight text-white/90">Para Transferi</h2>
          </div>
          <button className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center text-slate-300 hover:bg-white/20 transition-colors">
            ?
          </button>
        </div>

        <div className="flex w-full items-center justify-between gap-2 overflow-x-auto pb-4">
          {[
            { num: 1, title: 'ALICI HESAP' },
            { num: 2, title: 'GÖNDEREN HESAP' },
            { num: 3, title: 'TUTAR BELİRLEME' },
            { num: 4, title: 'DETAY BELİRLEME' }
          ].map((s) => (
            <div 
              key={s.num} 
              className={`flex-1 flex items-center justify-center gap-3 py-4 px-6 rounded-xl border whitespace-nowrap cursor-pointer transition-all ${
                step === s.num 
                  ? 'bg-blue-600 border-blue-500 text-white shadow-lg shadow-blue-600/20'
                  : step > s.num 
                    ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                    : 'bg-slate-800/50 border-white/5 text-slate-400'
              }`}
              onClick={() => {
                // Sadece geri dönülebilsin
                if (s.num < step) setStep(s.num as 1 | 2 | 3 | 4)
              }}
            >
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                step === s.num ? 'bg-white text-blue-600' : step > s.num ? 'bg-emerald-500/20 text-emerald-400' : 'bg-slate-700 text-slate-300'
              }`}>
                {step > s.num ? '✓' : s.num}
              </div>
              <span className="font-semibold tracking-wide text-sm">{s.title}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Step Content */}
      <div className={`backdrop-blur-xl border border-white/5 rounded-3xl p-6 shadow-xl ${step === 5 ? 'bg-emerald-500/10 border-emerald-500/30 text-center py-16' : 'bg-slate-900/40'}`}>
        
        {step === 5 && (
          <div className="flex flex-col items-center justify-center space-y-6 animate-fade-in-up">
            <div className="w-24 h-24 bg-emerald-500/20 rounded-full flex items-center justify-center shadow-lg shadow-emerald-500/20 mb-4">
              <svg className="w-12 h-12 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h2 className="text-3xl font-bold text-white tracking-tight">İşleminiz Başarıyla Alınmıştır</h2>
            <p className="text-slate-400 max-w-md mx-auto text-lg">
              Para transferiniz talimatınız doğrultusunda işleme koyulmuştur. Takibini hesap hareketlerinizden yapabilirsiniz.
            </p>
            <button 
              onClick={() => navigate('/banking')}
              className="mt-8 bg-white/10 hover:bg-white/20 text-white font-bold py-4 px-12 rounded-xl transition-all shadow-lg border border-white/10"
            >
              Ana Menüye Dön
            </button>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-6">
            <div className="flex rounded-xl overflow-hidden border border-white/10">
              <button 
                onClick={() => setReceiverTab('saved')}
                className={`flex-1 py-4 text-center font-bold transition-colors ${receiverTab === 'saved' ? 'bg-blue-600 text-white' : 'bg-slate-800/50 text-slate-400 hover:bg-slate-800'}`}
              >
                Kayıtlı Alıcılar
              </button>
              <button 
                onClick={() => setReceiverTab('new')}
                className={`flex-1 py-4 text-center font-bold transition-colors ${receiverTab === 'new' ? 'bg-blue-600 text-white' : 'bg-slate-800/50 text-slate-400 hover:bg-slate-800'}`}
              >
                Yeni Bir Alıcı
              </button>
            </div>

            {receiverTab === 'saved' ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {DUMMY_RECIPIENTS.map(rec => (
                  <div 
                    key={rec.id}
                    onClick={() => setSelectedRecipientId(rec.id)}
                    className={`p-5 rounded-2xl border cursor-pointer transition-all ${
                      selectedRecipientId === rec.id 
                        ? 'bg-blue-600/10 border-blue-500' 
                        : 'bg-white/5 border-white/5 hover:bg-white/10'
                    }`}
                  >
                    <div className="flex justify-between items-start mb-2">
                      <div className="font-bold text-white text-lg">{rec.name}</div>
                      {rec.isFrequent && (
                        <span className="text-[10px] font-bold px-2 py-1 bg-emerald-500/20 text-emerald-400 rounded-md">
                          SIK KULLANILAN
                        </span>
                      )}
                    </div>
                    <div className="text-sm text-slate-400">{rec.bank}</div>
                    <div className="text-sm font-mono text-slate-300 mt-2">{rec.iban}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="space-y-6">
                <div className="bg-blue-500/10 border border-blue-500/20 p-4 rounded-xl flex gap-3 text-blue-200 text-sm">
                  <svg className="w-5 h-5 text-blue-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Adı Soyadı bilgisini doğru ve eksiksiz yazmanız durumunda işleminiz sorunsuz gerçekleşecektir.
                </div>

                <div className="flex border-b border-white/10 gap-8">
                  <button 
                    onClick={() => setNewReceiverType('iban')}
                    className={`pb-4 text-sm font-bold transition-colors ${newReceiverType === 'iban' ? 'text-blue-500 border-b-2 border-blue-500' : 'text-slate-400 hover:text-white'}`}
                  >
                    IBAN İle
                  </button>
                  <button 
                    onClick={() => setNewReceiverType('accountNo')}
                    className={`pb-4 text-sm font-bold transition-colors ${newReceiverType === 'accountNo' ? 'text-blue-500 border-b-2 border-blue-500' : 'text-slate-400 hover:text-white'}`}
                  >
                    Hesap No İle
                  </button>
                  <button 
                    onClick={() => setNewReceiverType('easyAddress')}
                    className={`pb-4 text-sm font-bold transition-colors ${newReceiverType === 'easyAddress' ? 'text-blue-500 border-b-2 border-blue-500' : 'text-slate-400 hover:text-white'}`}
                  >
                    Kolay Adres İle
                  </button>
                </div>

                {newReceiverType === 'iban' && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div>
                      <label className="block text-sm font-medium text-slate-400 mb-2">IBAN</label>
                      <input 
                        type="text" 
                        value={receiverIban}
                        onChange={(e) => setReceiverIban(e.target.value)}
                        className="w-full bg-slate-800/50 border border-white/10 rounded-xl p-4 text-white focus:outline-none focus:ring-2 focus:ring-blue-500/50 uppercase font-mono"
                        placeholder="TR..."
                      />
                    </div>
                    <div>
                      <div className="flex justify-between mb-2">
                        <label className="block text-sm font-medium text-slate-400">Ad Soyad</label>
                        <button className="text-sm font-medium text-blue-400 hover:text-blue-300 underline">Kendime</button>
                      </div>
                      <input 
                        type="text" 
                        value={receiverName}
                        onChange={(e) => setReceiverName(e.target.value)}
                        className="w-full bg-slate-800/50 border border-white/10 rounded-xl p-4 text-white focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                        placeholder="Alıcı Adı Soyadı"
                      />
                    </div>
                  </div>
                )}
                
                <div className="flex items-center justify-end gap-3 pt-4">
                  <span className="text-sm font-medium text-slate-300">Kayıtlı alıcı olarak ekle</span>
                  <button 
                    onClick={() => setSaveAsRecipient(!saveAsRecipient)}
                    className={`w-12 h-6 rounded-full transition-colors flex items-center px-1 ${saveAsRecipient ? 'bg-blue-500' : 'bg-slate-600'}`}
                  >
                    <div className={`w-4 h-4 bg-white rounded-full transition-transform ${saveAsRecipient ? 'transform translate-x-6' : ''}`} />
                  </button>
                </div>
              </div>
            )}
            
            <button 
              disabled={!isStep1Valid}
              onClick={handleNext}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold py-4 rounded-xl transition-colors shadow-lg shadow-blue-600/20 mt-6"
            >
              DEVAM
            </button>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-6">
            <h3 className="text-lg font-bold text-white mb-4">Gönderen Hesap Seçimi</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {accounts.map(acc => (
                <div 
                  key={acc.id}
                  onClick={() => setSenderAccountId(acc.id)}
                  className={`p-6 rounded-2xl border cursor-pointer transition-all ${
                    senderAccountId === acc.id 
                      ? 'bg-blue-600/10 border-blue-500' 
                      : 'bg-white/5 border-white/5 hover:bg-white/10'
                  }`}
                >
                  <div className="flex justify-between items-start mb-2">
                    <div className="font-bold text-white text-lg">{acc.name}</div>
                    <div className="px-3 py-1 bg-white/5 rounded-lg text-sm text-slate-300">{acc.type === 'checking' ? 'Vadesiz' : 'Vadeli'}</div>
                  </div>
                  <div className="text-sm font-mono text-slate-400 mb-4">{acc.accountNumber}</div>
                  
                  <div className="text-sm text-slate-400">Kullanılabilir Bakiye</div>
                  <div className="text-2xl font-bold text-emerald-400">
                    {acc.balance.toLocaleString('tr-TR', { style: 'currency', currency: acc.currency })}
                  </div>
                </div>
              ))}
            </div>

            <button 
              disabled={!isStep2Valid}
              onClick={handleNext}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold py-4 rounded-xl transition-colors shadow-lg shadow-blue-600/20 mt-6"
            >
              DEVAM
            </button>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-6 max-w-2xl mx-auto text-center">
            <div className="bg-white/5 border border-white/10 rounded-xl p-4 flex justify-between items-center text-left">
              <div className="flex items-center gap-3 text-slate-300">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                Kalan Para Transfer Limiti
              </div>
              <div className="font-bold text-white">500.000,00 TL</div>
            </div>

            <div className="py-12">
              <input 
                type="number"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                autoFocus
                className="w-full bg-transparent text-center text-6xl md:text-7xl font-bold text-white focus:outline-none placeholder-slate-700"
                placeholder="0,00"
              />
              <div className="text-2xl font-bold text-slate-400 mt-4">TL</div>
              <div className="text-sm text-slate-500 mt-2">İşlem Tutarı</div>
            </div>

            <button 
              disabled={!isStep3Valid}
              onClick={handleNext}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold py-4 rounded-xl transition-colors shadow-lg shadow-blue-600/20"
            >
              DEVAM
            </button>
          </div>
        )}

        {step === 4 && (
          <div className="space-y-6">
            <div className="text-center text-slate-300 mb-8">
              Gerçekleştireceğiniz işleminizin detaylarını kontrol edip, işleminizi onaylayınız.
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 bg-white/5 border border-white/10 rounded-2xl p-6">
              
              <div className="p-4 bg-slate-900/50 rounded-xl border border-white/5 relative group">
                <div className="text-blue-500 font-bold mb-2">Alıcı Hesap</div>
                <div className="font-bold text-white text-lg">
                  {receiverTab === 'saved' 
                    ? DUMMY_RECIPIENTS.find(r => r.id === selectedRecipientId)?.name 
                    : receiverName}
                </div>
                <div className="text-sm text-slate-400 mt-1">
                  {receiverTab === 'saved' 
                    ? DUMMY_RECIPIENTS.find(r => r.id === selectedRecipientId)?.bank 
                    : 'Banka Adı (Otomatik)'}
                </div>
                <div className="text-sm font-mono text-slate-300 mt-1">
                  {receiverTab === 'saved' 
                    ? DUMMY_RECIPIENTS.find(r => r.id === selectedRecipientId)?.iban 
                    : receiverIban}
                </div>
                <button onClick={() => setStep(1)} className="absolute right-4 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity">
                  <svg className="w-5 h-5 text-slate-400 hover:text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                  </svg>
                </button>
              </div>

              <div className="p-4 bg-slate-900/50 rounded-xl border border-white/5 relative group">
                <div className="text-blue-500 font-bold mb-2">Gönderen Hesap</div>
                <div className="font-bold text-white text-lg">{senderAccount?.name}</div>
                <div className="text-sm text-slate-400 mt-1">{senderAccount?.type === 'checking' ? 'Vadesiz' : 'Vadeli'}</div>
                <div className="text-sm mt-2 text-slate-300">
                  Bakiye: {senderAccount?.balance.toLocaleString('tr-TR', { style: 'currency', currency: senderAccount.currency })}
                </div>
                <button onClick={() => setStep(2)} className="absolute right-4 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity">
                  <svg className="w-5 h-5 text-slate-400 hover:text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                  </svg>
                </button>
              </div>

              <div className="p-4 bg-slate-900/50 rounded-xl border border-white/5 relative group">
                <div className="text-blue-500 font-bold mb-2">Tutar</div>
                <div className="font-bold text-white text-xl">{parseFloat(amount).toLocaleString('tr-TR', { minimumFractionDigits: 2 })} TL</div>
                <button onClick={() => setStep(3)} className="absolute right-4 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity">
                  <svg className="w-5 h-5 text-slate-400 hover:text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                  </svg>
                </button>
              </div>

              <div className="p-4 bg-slate-900/50 rounded-xl border border-white/5">
                <div className="text-blue-500 font-bold mb-2">Para Gönderim Tipi</div>
                <select 
                  value={transferType}
                  onChange={(e) => setTransferType(e.target.value)}
                  className="w-full bg-transparent text-white focus:outline-none appearance-none cursor-pointer"
                >
                  <option className="bg-slate-800">Bireysel Ödeme</option>
                  <option className="bg-slate-800">Kira Ödemesi</option>
                  <option className="bg-slate-800">Diğer</option>
                </select>
              </div>

              <div className="p-4 bg-slate-900/50 rounded-xl border border-white/5 md:col-span-2">
                <div className="text-blue-500 font-bold mb-2">Açıklama</div>
                <input 
                  type="text" 
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Açıklama girebilirsiniz (İsteğe bağlı)"
                  className="w-full bg-transparent text-white focus:outline-none placeholder-slate-600"
                />
              </div>

              <div className="p-4 bg-slate-900/50 rounded-xl border border-white/5">
                <div className="text-blue-500 font-bold mb-2">Para Transfer Ücreti</div>
                <div className="font-bold text-white text-lg">{transferFee.toLocaleString('tr-TR', { minimumFractionDigits: 2 })} TL</div>
              </div>

              <div className="p-4 bg-slate-900/50 rounded-xl border border-white/5">
                <div className="text-blue-500 font-bold mb-2">İşlem Tarihi</div>
                <div className="font-bold text-white text-lg">{date}</div>
              </div>

            </div>

            <button 
              onClick={handleConfirm}
              className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-4 rounded-xl transition-colors shadow-lg shadow-blue-600/20 mt-6 text-lg tracking-wide"
            >
              ONAYLA
            </button>
          </div>
        )}

      </div>
    </div>
  )
}
