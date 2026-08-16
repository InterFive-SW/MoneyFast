import { useState } from 'react'
import type { InvestmentBalance } from '../../data/mockData'

interface Props {
  data: InvestmentBalance
}

/**
 * Yatırım Hesabım (Investment Balance) Bileşeni
 * Toplam bakiyeyi TL ve Dolar cinsinden gösterir ve alt varlık dağılımını özetler.
 */
export default function InvestmentBalanceWidget({ data }: Props) {
  const [currency, setCurrency] = useState<'TRY' | 'USD'>('TRY')

  const formattedTotal =
    currency === 'TRY'
      ? data.totalTRY.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
      : data.totalUSD.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

  const symbol = currency === 'TRY' ? '₺' : '$'

  return (
    <div className="flex flex-col h-full bg-white/70 backdrop-blur-md rounded-2xl p-5 border border-white/50 shadow-sm">
      {/* Üst Kısım: Başlık ve Para Birimi Geçişi */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-500">Yatırım Hesabım</h3>
        <div className="flex bg-slate-100/50 p-1 rounded-lg">
          <button
            onClick={() => setCurrency('TRY')}
            className={`px-2 py-1 text-xs font-semibold rounded-md transition-colors ${
              currency === 'TRY' ? 'bg-white shadow-sm text-slate-900' : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            TL
          </button>
          <button
            onClick={() => setCurrency('USD')}
            className={`px-2 py-1 text-xs font-semibold rounded-md transition-colors ${
              currency === 'USD' ? 'bg-white shadow-sm text-slate-900' : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            USD
          </button>
        </div>
      </div>

      {/* Ana Bakiye */}
      <div className="flex-1 flex flex-col justify-center mb-6">
        <div className="text-3xl font-bold text-slate-900 tabular-nums">
          {symbol} {formattedTotal}
        </div>
      </div>

      {/* Varlık Kırılımı (Fintables tarzı yoğun veri listesi) */}
      <div className="grid grid-cols-3 gap-2 border-t border-slate-200/50 pt-4">
        <div className="flex flex-col">
          <span className="text-[10px] uppercase text-slate-400 font-medium mb-1">Nakit</span>
          <span className="text-sm font-semibold text-slate-700 tabular-nums">
            ₺{data.breakdown.cashTRY.toLocaleString('tr-TR', { minimumFractionDigits: 0 })}
          </span>
        </div>
        <div className="flex flex-col border-l border-slate-200/50 pl-2">
          <span className="text-[10px] uppercase text-slate-400 font-medium mb-1">BIST</span>
          <span className="text-sm font-semibold text-slate-700 tabular-nums">
            ₺{data.breakdown.stocksBIST.toLocaleString('tr-TR', { minimumFractionDigits: 0 })}
          </span>
        </div>
        <div className="flex flex-col border-l border-slate-200/50 pl-2">
          <span className="text-[10px] uppercase text-slate-400 font-medium mb-1">ABD (₺)</span>
          <span className="text-sm font-semibold text-slate-700 tabular-nums">
            ₺{data.breakdown.stocksUS.toLocaleString('tr-TR', { minimumFractionDigits: 0 })}
          </span>
        </div>
      </div>
    </div>
  )
}
