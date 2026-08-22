import { useParams, useNavigate, useOutletContext, Navigate } from 'react-router-dom'
import { BankingContextType } from '../../pages/Banking'

export default function AccountTransactionsView() {
  const { accountId } = useParams<{ accountId: string }>()
  const navigate = useNavigate()
  const { data } = useOutletContext<BankingContextType>()
  
  const account = data.accounts.find(a => a.id === accountId)
  const transactions = data.recentTransactions // we can filter if needed, but mock shows all

  if (!account) {
    return <Navigate to="/banking/accounts" replace />
  }
  return (
    <div className="w-full max-w-5xl mx-auto flex flex-col gap-6 animate-fade-in-up">
      
      {/* Üst Navigasyon & Geri Butonu */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/banking/accounts')}
            className="group flex items-center gap-2 px-4 py-2 bg-slate-900/50 hover:bg-slate-800/80 backdrop-blur-md border border-white/5 rounded-xl transition-all"
          >
            <svg className="w-5 h-5 text-slate-400 group-hover:text-white transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            <span className="text-slate-300 font-medium group-hover:text-white transition-colors">
              Geri
            </span>
          </button>
          
          <div>
            <h2 className="text-xl font-bold tracking-tight text-white/90">Hesap Hareketleri</h2>
            <p className="text-sm text-slate-400 font-mono mt-0.5">{account.accountNumber}</p>
          </div>
        </div>

        <div className="bg-slate-900/40 border border-white/5 rounded-xl px-4 py-2 text-right">
          <div className="text-xs text-slate-400 uppercase tracking-wide">Mevcut Bakiye</div>
          <div className="text-lg font-bold text-brandBlue">
            {account.balance.toLocaleString('tr-TR', { style: 'currency', currency: account.currency })}
          </div>
        </div>
      </div>

      {/* Hesap Hareketleri Listesi */}
      <div className="bg-slate-900/40 backdrop-blur-xl border border-white/5 rounded-3xl p-6 shadow-xl">
        <div className="flex items-center justify-between mb-6 pb-4 border-b border-white/5">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400">Son İşlemler</h3>
          <div className="flex gap-2">
            <button className="px-3 py-1 text-xs font-medium bg-white/5 hover:bg-white/10 rounded-lg text-slate-300 transition-colors">Tümü</button>
            <button className="px-3 py-1 text-xs font-medium bg-white/5 hover:bg-white/10 rounded-lg text-slate-300 transition-colors">Gelen</button>
            <button className="px-3 py-1 text-xs font-medium bg-white/5 hover:bg-white/10 rounded-lg text-slate-300 transition-colors">Giden</button>
          </div>
        </div>

        {transactions.length === 0 ? (
          <div className="py-12 text-center text-slate-400 flex flex-col items-center gap-3">
            <svg className="w-12 h-12 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <p>Bu hesaba ait henüz bir işlem bulunmuyor.</p>
          </div>
        ) : (
          <div className="space-y-4">
            {transactions.map(tx => {
              const isIncome = tx.type === 'income'
              return (
                <div key={tx.id} className="group flex items-center justify-between p-4 bg-white/5 hover:bg-white/10 border border-transparent hover:border-white/5 rounded-2xl transition-all">
                  <div className="flex items-center gap-4">
                    <div className="w-12 h-12 rounded-xl bg-slate-800 flex items-center justify-center text-2xl shadow-inner border border-white/5">
                      {tx.icon}
                    </div>
                    <div>
                      <div className="font-semibold text-slate-200 group-hover:text-white transition-colors">{tx.title}</div>
                      <div className="text-sm text-slate-400 mt-0.5">{tx.category} • {tx.date}</div>
                    </div>
                  </div>
                  
                  <div className={`text-right font-bold tracking-tight ${isIncome ? 'text-emerald-400' : 'text-slate-300'}`}>
                    {isIncome ? '+' : '-'} {tx.amount.toLocaleString('tr-TR', { style: 'currency', currency: account.currency })}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

    </div>
  )
}
