import { useState } from 'react'
import type { BankAccount } from '../../data/mockBankingData'

interface Props {
  accounts: BankAccount[]
  totalAssets: number
  onNavigateToAccounts: () => void
  onOpenTransfer: () => void
  onOpenBillPayment: () => void
  onFeatureNotReady: (featureName: string) => void
}

export default function AccountHeroWidget({ 
  accounts, 
  onNavigateToAccounts, 
  onOpenTransfer, 
  onOpenBillPayment, 
  onFeatureNotReady 
}: Props) {
  // Varsayılan olarak ilk hesabı göster
  const [selectedAccountId, setSelectedAccountId] = useState<string>(accounts[0]?.id || '')
  const [isDropdownOpen, setIsDropdownOpen] = useState(false)
  const [copied, setCopied] = useState(false)

  const selectedAccount = accounts.find(a => a.id === selectedAccountId) || accounts[0]

  const handleCopyIban = () => {
    if (selectedAccount) {
      navigator.clipboard.writeText(selectedAccount.accountNumber)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <div className="w-full max-w-4xl mx-auto relative overflow-hidden rounded-3xl mb-8 animate-fade-in shadow-2xl">
      {/* Arka Plan Gradyanı (İşCep Tarzı) */}
      <div className="absolute inset-0 bg-gradient-to-br from-slate-900 via-slate-800/80 to-slate-950"></div>
      
      {/* Arka plan süslemeleri (Glassmorphism blobs) */}
      <div className="absolute top-0 right-0 w-64 h-64 bg-brandBlue/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/3"></div>
      <div className="absolute bottom-0 left-0 w-80 h-80 bg-indigo-500/5 rounded-full blur-3xl translate-y-1/3 -translate-x-1/4"></div>

      <div className="relative p-6 sm:p-10 flex flex-col items-center">
        
        {/* Kopyalandı Bildirimi */}
        <div className={`absolute top-4 bg-emerald-500 text-white text-sm font-bold px-4 py-2 rounded-full transition-all duration-300 ${copied ? 'opacity-100 translate-y-0' : 'opacity-0 -translate-y-4 pointer-events-none'}`}>
          IBAN Kopyalandı!
        </div>

        {/* Hesap Seçici Dropdown */}
        <div className="relative mb-8 z-10 w-full max-w-xs">
          <button 
            onClick={() => setIsDropdownOpen(!isDropdownOpen)}
            className="w-full bg-white/10 hover:bg-white/20 border border-white/20 backdrop-blur-md rounded-2xl p-4 flex items-center justify-between transition-colors"
          >
            <div className="text-left">
              <div className="text-white font-bold tracking-wide uppercase text-sm">{selectedAccount?.name}</div>
              <div className="text-white/70 text-xs font-mono mt-1">{selectedAccount?.accountNumber}</div>
            </div>
            <svg className={`w-5 h-5 text-white transition-transform duration-300 ${isDropdownOpen ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          {isDropdownOpen && (
            <div className="absolute top-full left-0 right-0 mt-2 bg-slate-900/95 backdrop-blur-xl border border-white/10 rounded-2xl overflow-hidden shadow-2xl z-20">
              {accounts.map(acc => (
                <button 
                  key={acc.id}
                  onClick={() => {
                    setSelectedAccountId(acc.id)
                    setIsDropdownOpen(false)
                  }}
                  className={`w-full text-left p-4 hover:bg-white/10 transition-colors border-b border-white/5 last:border-0 ${selectedAccountId === acc.id ? 'bg-white/5' : ''}`}
                >
                  <div className="text-white font-bold text-sm">{acc.name}</div>
                  <div className="text-slate-400 text-xs font-mono mt-1">{acc.accountNumber}</div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Bakiye Görünümü */}
        <div className="text-center mb-6">
          <div className="text-white/80 text-sm mb-1">Bakiyeniz</div>
          <div className="text-5xl sm:text-6xl font-bold text-white tracking-tight flex items-center justify-center gap-2 cursor-pointer hover:scale-105 transition-transform" onClick={onNavigateToAccounts}>
            {selectedAccount?.balance.toLocaleString('tr-TR', { minimumFractionDigits: 2 })} <span className="text-3xl sm:text-4xl mt-2">TL</span>
            <svg className="w-8 h-8 text-white/50" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M9 5l7 7-7 7" />
            </svg>
          </div>
        </div>

        {/* Ek Hesap Başvurusu Linki */}
        <button 
          onClick={() => onFeatureNotReady('Ek Hesap Başvurusu')}
          className="flex items-center gap-2 text-white/80 hover:text-white text-sm mb-6 transition-colors"
        >
          <div className="w-5 h-5 rounded-full bg-white/20 flex items-center justify-center font-bold text-xs">+</div>
          Ek Hesap Başvurusu için tıklayınız.
        </button>

        {/* Tüm Hesaplar Butonu */}
        <button 
          onClick={onNavigateToAccounts}
          className="bg-white/10 hover:bg-white/20 border border-white/20 text-white font-semibold py-2 px-6 rounded-xl transition-colors mb-12"
        >
          TÜM HESAPLAR
        </button>

        {/* Hızlı İşlemler Butonları (4'lü) */}
        <div className="grid grid-cols-4 gap-2 sm:gap-4 w-full max-w-2xl">
          <button onClick={onOpenTransfer} className="group flex flex-col items-center">
            <div className="w-14 h-14 sm:w-16 sm:h-16 rounded-2xl bg-white/10 group-hover:bg-white/20 border border-white/10 backdrop-blur-md flex items-center justify-center shadow-lg transition-all group-hover:-translate-y-1">
              <svg className="w-6 h-6 sm:w-7 sm:h-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
              </svg>
            </div>
            <div className="text-white/90 text-xs sm:text-sm font-medium mt-2 text-center leading-tight">Para<br/>Aktar</div>
          </button>
          
          <button onClick={onOpenBillPayment} className="group flex flex-col items-center">
            <div className="w-14 h-14 sm:w-16 sm:h-16 rounded-2xl bg-white/10 group-hover:bg-white/20 border border-white/10 backdrop-blur-md flex items-center justify-center shadow-lg transition-all group-hover:-translate-y-1">
              <svg className="w-6 h-6 sm:w-7 sm:h-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <div className="text-white/90 text-xs sm:text-sm font-medium mt-2 text-center leading-tight">Ödeme<br/>Yap</div>
          </button>

          <button onClick={handleCopyIban} className="group flex flex-col items-center">
            <div className="w-14 h-14 sm:w-16 sm:h-16 rounded-2xl bg-white/10 group-hover:bg-white/20 border border-white/10 backdrop-blur-md flex items-center justify-center shadow-lg transition-all group-hover:-translate-y-1">
              <svg className="w-6 h-6 sm:w-7 sm:h-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
              </svg>
            </div>
            <div className="text-white/90 text-xs sm:text-sm font-medium mt-2 text-center leading-tight">IBAN<br/>Paylaş</div>
          </button>

          <button onClick={() => onFeatureNotReady('Daha Fazlası')} className="group flex flex-col items-center">
            <div className="w-14 h-14 sm:w-16 sm:h-16 rounded-2xl bg-white/10 group-hover:bg-white/20 border border-white/10 backdrop-blur-md flex items-center justify-center shadow-lg transition-all group-hover:-translate-y-1">
              <svg className="w-6 h-6 sm:w-7 sm:h-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" />
              </svg>
            </div>
            <div className="text-white/90 text-xs sm:text-sm font-medium mt-2 text-center leading-tight">Daha<br/>Fazlası</div>
          </button>
        </div>
      </div>
    </div>
  )
}
