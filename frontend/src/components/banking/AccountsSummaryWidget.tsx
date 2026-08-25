import type { BankAccount } from '../../data/mockBankingData'

interface Props {
  accounts: BankAccount[]
  totalAssets: number
  onOpenTransfer: (accountId: string) => void
  onActionClick?: (featureName: string) => void
}

export default function AccountsSummaryWidget({ accounts, totalAssets, onOpenTransfer, onActionClick }: Props) {
  return (
    <div className="flex flex-col rounded-2xl bg-slate-900/50 backdrop-blur-xl border border-white/10 p-6 shadow-2xl">
      <div className="mb-6">
        <h3 className="text-sm font-medium text-slate-400">Toplam Varlık</h3>
        <p className="mt-1 text-3xl font-bold text-white">
          ₺{totalAssets.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}
        </p>
      </div>

      <div className="flex flex-col gap-4">
        <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Hesaplarım</h4>
        {accounts.map(acc => (
          <div key={acc.id} className="flex flex-col p-5 rounded-xl bg-white/5 border border-white/10 hover:border-white/20 transition-colors">
            
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className={`w-10 h-10 rounded-full flex items-center justify-center ${acc.type === 'checking' ? 'bg-brandBlue/20 text-brandBlue' : 'bg-purple-500/20 text-purple-400'}`}>
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    {acc.type === 'checking' 
                      ? <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
                      : <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    }
                  </svg>
                </div>
                <div>
                  <p className="text-sm font-semibold text-white">{acc.name}</p>
                  <p className="text-xs text-slate-400 mt-0.5">IBAN: {acc.accountNumber.slice(0,4)}...{acc.accountNumber.slice(-4)}</p>
                </div>
              </div>
              <div className="text-right">
                <p className="text-lg font-bold text-white">
                  ₺{acc.balance.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}
                </p>
              </div>
            </div>

            {/* Aksiyon Butonları */}
            <div className="flex flex-wrap gap-2 pt-3 border-t border-white/5">
              <button 
                onClick={() => onOpenTransfer(acc.name)}
                className="text-xs font-medium bg-brandBlue/10 text-brandBlue hover:bg-brandBlue hover:text-white px-3 py-1.5 rounded-lg transition-colors border border-brandBlue/20 hover:border-brandBlue"
              >
                Para Transferi
              </button>
              
              {acc.type === 'checking' && (
                <button onClick={() => onActionClick && onActionClick('Nakit Avans')} className="text-xs font-medium bg-white/5 text-slate-300 hover:bg-white/10 hover:text-white px-3 py-1.5 rounded-lg transition-colors border border-white/10">
                  Nakit Avans
                </button>
              )}
              
              {acc.type === 'savings' && (
                <button onClick={() => onActionClick && onActionClick('Hisse Al/Sat')} className="text-xs font-medium bg-purple-500/10 text-purple-400 hover:bg-purple-500 hover:text-white px-3 py-1.5 rounded-lg transition-colors border border-purple-500/20 hover:border-purple-500">
                  Hisse Al/Sat
                </button>
              )}

              {acc.type === 'foreign_currency' && (
                <button onClick={() => onActionClick && onActionClick('Döviz Al/Sat')} className="text-xs font-medium bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500 hover:text-white px-3 py-1.5 rounded-lg transition-colors border border-emerald-500/20 hover:border-emerald-500">
                  Döviz Al/Sat
                </button>
              )}
            </div>

          </div>
        ))}
      </div>
    </div>
  )
}
