import { useNavigate } from 'react-router-dom'

/**
 * BankingMenu Bileşeni
 * 
 * Bankacılık işlemlerinin ana giriş noktasıdır. Kullanıcıya "Öne Çıkanlar" ve
 * tüm "İşlemler" kategorilerini asimetrik, modern bir glassmorphism kart yapısıyla sunar.
 * Tıklanan işleme göre üst bileşene (Router) ilgili modalı veya alt sayfayı açması için sinyal gönderir.
 */

interface BankingMenuProps {
  onNavigateToAccounts: () => void
  onOpenTransfer: () => void
  onOpenBillPayment: () => void
  onFeatureNotReady: (featureName: string) => void
}

export default function BankingMenu({
  onNavigateToAccounts,
  onOpenTransfer,
  onOpenBillPayment,
  onFeatureNotReady
}: BankingMenuProps) {
  const navigate = useNavigate()

  // Tüm işlemler kategorileri listesi
  const operations = [
    { id: 'accounts', title: 'Hesaplarım', isNew: false, action: onNavigateToAccounts },
    { id: 'transfers_all', title: 'Para Transferleri', isNew: false, action: onOpenTransfer },
    { id: 'cards', title: 'Kartlarım', isNew: false, action: () => navigate('/banking/cards') },
    { id: 'loans', title: 'Krediler', isNew: false, action: () => onFeatureNotReady('Krediler') },
    { id: 'payments', title: 'Ödemeler', isNew: false, action: onOpenBillPayment },
    { id: 'investments', title: 'Yatırım ve Borsa', isNew: false, action: () => navigate('/investment') },
    { id: 'saved_tx', title: 'Kayıtlı İşlemlerim', isNew: false, action: () => onFeatureNotReady('Kayıtlı İşlemlerim') }
  ]

  return (
    <div className="w-full max-w-7xl mx-auto flex flex-col gap-10 animate-fade-in">
      
      {/* İşlemler (Operations) Alanı */}
      <section>
        <h2 className="text-xl font-bold tracking-tight text-white/90 mb-6">İşlemler</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-4">
          {operations.map(op => (
            <button
              key={op.id}
              onClick={op.action}
              className="group flex items-center justify-between py-4 px-4 
                         bg-slate-900/20 hover:bg-slate-800/40 border border-transparent 
                         hover:border-white/5 rounded-xl transition-all duration-200"
            >
              <div className="flex items-center gap-4">
                <div className="w-8 h-8 rounded-full bg-slate-800/80 flex items-center justify-center text-slate-400 group-hover:text-brandBlue group-hover:bg-brandBlue/10 transition-colors">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 5l7 7-7 7M5 5l7 7-7 7" />
                  </svg>
                </div>
                <span className="text-slate-300 font-medium group-hover:text-white text-left transition-colors">
                  {op.title}
                </span>
              </div>
              
              {/* YENİ Etiketi */}
              {op.isNew && (
                <span className="px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-white bg-gradient-to-r from-red-500 to-rose-600 rounded-md shadow-lg shadow-red-500/20">
                  Yeni
                </span>
              )}
            </button>
          ))}
        </div>
      </section>

    </div>
  )
}
