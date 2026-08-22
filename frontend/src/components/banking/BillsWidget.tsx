import type { Bill } from '../../data/mockBankingData'

interface Props {
  bills: Bill[]
  onPayBill: (billId: string) => void
}

/**
 * BillsWidget Component
 * Bekleyen faturaları gösterir ve hızlı ödeme aksiyonu sunar.
 */
export default function BillsWidget({ bills, onPayBill }: Props) {
  // Sadece bekleyen faturaları alıyoruz
  const pendingBills = bills.filter(b => b.status === 'pending')

  return (
    <div className="flex flex-col rounded-2xl bg-slate-900/50 backdrop-blur-xl border border-white/10 p-6 shadow-2xl">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-white">Bekleyen Faturalar</h3>
        <span className="text-xs font-medium bg-rose-500/20 text-rose-400 px-2.5 py-1 rounded-full">
          {pendingBills.length} Adet
        </span>
      </div>

      <div className="flex flex-col gap-3">
        {pendingBills.length === 0 ? (
          <p className="text-sm text-slate-400 italic">Ödenecek fatura bulunmuyor.</p>
        ) : (
          pendingBills.map(bill => (
            <div key={bill.id} className="flex items-center justify-between p-4 rounded-xl bg-white/5 border border-white/5 hover:bg-white/10 transition-colors">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-slate-800 flex items-center justify-center border border-white/5">
                  {bill.type === 'water' && '💧'}
                  {bill.type === 'electricity' && '⚡'}
                  {bill.type === 'internet' && '🌐'}
                  {bill.type === 'phone' && '📱'}
                </div>
                <div>
                  <p className="text-sm font-semibold text-white">{bill.institution}</p>
                  <p className="text-xs text-rose-400 mt-0.5">Son: {new Date(bill.dueDate).toLocaleDateString('tr-TR')}</p>
                </div>
              </div>
              
              <div className="flex flex-col items-end gap-2">
                <span className="text-sm font-bold text-white">
                  ₺{bill.amount.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}
                </span>
                <button 
                  onClick={() => onPayBill(bill.id)}
                  className="text-xs font-medium bg-brandBlue hover:bg-blue-600 text-white px-3 py-1.5 rounded-lg transition-colors shadow-lg shadow-brandBlue/20"
                >
                  Öde
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
