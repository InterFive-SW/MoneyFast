import type { CreditCard } from '../../data/mockBankingData'

interface Props {
  cards: CreditCard[]
  onPayDebt: (cardId: string) => void
  onSettings: (cardName: string) => void
}

export default function CreditCardsWidget({ cards, onPayDebt, onSettings }: Props) {
  return (
    <div className="flex flex-col gap-6 h-full">
      {cards.map(card => {
        const usagePercentage = (card.currentDebt / card.limit) * 100
        const isHighUsage = usagePercentage > 80

        return (
          <div key={card.id} className="rounded-2xl bg-slate-900/50 backdrop-blur-xl border border-white/10 p-5 shadow-2xl flex flex-col gap-5 h-full justify-between">
            {/* Kart Görseli (CSS ile) */}
            <div className={`relative h-40 rounded-xl bg-gradient-to-br ${card.color} p-5 flex flex-col justify-between overflow-hidden shadow-lg border border-white/10 shrink-0`}>
              {/* Parlaklık Efekti */}
              <div className="absolute top-0 right-0 w-64 h-64 bg-white/5 rounded-full blur-3xl -mr-10 -mt-10 pointer-events-none"></div>
              
              <div className="flex justify-between items-start relative z-10">
                <div className="text-white/80 font-medium tracking-widest text-sm uppercase">MoneyFast</div>
                <div className="text-white/90 font-bold italic">
                  {card.brand === 'mastercard' ? 'mastercard' : 'VISA'}
                </div>
              </div>
              
              <div className="relative z-10">
                <div className="text-white text-xl tracking-[0.2em] font-mono mb-2">{card.cardNumber}</div>
                <div className="flex justify-between items-end">
                  <div className="text-white/90 text-sm font-medium">{card.name}</div>
                  <div className="text-white/70 text-xs">Son: <span className="text-white">{new Date(card.dueDate).toLocaleDateString('tr-TR')}</span></div>
                </div>
              </div>
            </div>

            {/* Limit ve Borç Özeti */}
            <div className="flex-1">
              <div className="flex justify-between items-end mb-2">
                <div>
                  <p className="text-xs text-slate-400">Güncel Borç</p>
                  <p className="text-lg font-bold text-white">₺{card.currentDebt.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}</p>
                </div>
                <div className="text-right">
                  <p className="text-xs text-slate-400">Kullanılabilir Limit</p>
                  <p className="text-sm font-semibold text-slate-300">₺{card.availableLimit.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}</p>
                </div>
              </div>

              {/* İnce Progress Bar */}
              <div className="w-full h-1.5 bg-white/10 rounded-full overflow-hidden mb-4">
                <div 
                  className={`h-full rounded-full ${isHighUsage ? 'bg-rose-500' : 'bg-brandBlue'}`} 
                  style={{ width: `${Math.min(usagePercentage, 100)}%` }}
                />
              </div>
              
              {/* Aksiyon Butonları */}
              <div className="flex gap-2 pt-2 border-t border-white/5">
                <button 
                  onClick={() => onPayDebt(card.id)}
                  className="flex-1 text-xs font-medium bg-brandBlue/10 text-brandBlue hover:bg-brandBlue hover:text-white py-2 rounded-lg transition-colors border border-brandBlue/20 hover:border-brandBlue text-center"
                >
                  Borç Öde
                </button>
                <button 
                  onClick={() => onSettings(card.name)}
                  className="flex-1 text-xs font-medium bg-white/5 text-slate-300 hover:bg-white/10 hover:text-white py-2 rounded-lg transition-colors border border-white/10 text-center"
                >
                  Kart Ayarları
                </button>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
