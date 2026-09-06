import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiClient, type InvestmentBalance } from '../../api/client'

/**
 * Yatırım Hesabım (Investment Balance) Bileşeni
 *
 * Kendi verisini çeker. Bir süre `MOCK_INVESTMENT_BALANCE` sabitiyle
 * besleniyordu — oysa `/api/investment/portfolio/summary` tam olarak bu şekli
 * canlı fiyatlardan hesaplayıp döndürüyordu ve hiçbir yerden çağrılmıyordu.
 *
 * Başlığa tıklayınca portföye gider; bu davranış bankacılık dalından geldi ve
 * korundu.
 */
export default function InvestmentBalanceWidget() {
  const navigate = useNavigate()
  const [currency, setCurrency] = useState<'TRY' | 'USD'>('TRY')
  const [data, setData] = useState<InvestmentBalance | null>(null)

  useEffect(() => {
    apiClient
      .getPortfolioSummary()
      .then(setData)
      .catch((error) => console.error('Failed to load investment balance', error))
  }, [])

  if (!data) {
    return (
      <div className="flex flex-col h-full items-center justify-center bg-transparent">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500"></div>
      </div>
    )
  }

  const formattedTotal =
    currency === 'TRY'
      ? data.totalTRY.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
      : data.totalUSD.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

  const symbol = currency === 'TRY' ? '₺' : '$'

  return (
    <div className="flex flex-col h-full flex-col h-full bg-transparent p-1">
      {/* Üst Kısım: Başlık ve Para Birimi Geçişi */}
      <div className="flex items-center justify-between mb-4">
        <h3 
          className="text-[11px] uppercase tracking-wider font-semibold text-slate-400 cursor-pointer hover:text-brandBlue transition-colors"
          onClick={() => navigate('/portfolio')}
        >
          Yatırım Hesabım <span className="text-[9px] opacity-70 ml-1">↗</span>
        </h3>
        <div className="flex bg-white/5/10/50 p-1 rounded-lg">
          <button
            onClick={() => setCurrency('TRY')}
            className={`px-2 py-1 text-xs font-semibold rounded-md transition-colors ${
              currency === 'TRY' ? 'bg-white/5 shadow-sm text-white' : 'text-slate-400 hover:text-slate-300'
            }`}
          >
            TL
          </button>
          <button
            onClick={() => setCurrency('USD')}
            className={`px-2 py-1 text-xs font-semibold rounded-md transition-colors ${
              currency === 'USD' ? 'bg-white/5 shadow-sm text-white' : 'text-slate-400 hover:text-slate-300'
            }`}
          >
            USD
          </button>
        </div>
      </div>

      {/* Ana Bakiye */}
      <div className="flex-1 flex flex-col justify-center mb-6">
        <div className="text-3xl font-bold text-white tabular-nums">
          {symbol} {formattedTotal}
        </div>
      </div>

      {/* Varlık Kırılımı (Fintables tarzı yoğun veri listesi) */}
      <div className="grid grid-cols-3 gap-2 border-t border-white/10 pt-4">
        <div className="flex flex-col">
          <span className="text-[10px] uppercase text-slate-400 font-medium mb-1">Nakit</span>
          <span className="text-sm font-semibold text-slate-300 tabular-nums">
            ₺{data.breakdown.cashTRY.toLocaleString('tr-TR', { minimumFractionDigits: 0 })}
          </span>
        </div>
        <div className="flex flex-col border-l border-white/10 pl-2">
          <span className="text-[10px] uppercase text-slate-400 font-medium mb-1">BIST</span>
          <span className="text-sm font-semibold text-slate-300 tabular-nums">
            ₺{data.breakdown.stocksBIST.toLocaleString('tr-TR', { minimumFractionDigits: 0 })}
          </span>
        </div>
        <div className="flex flex-col border-l border-white/10 pl-2">
          <span className="text-[10px] uppercase text-slate-400 font-medium mb-1">ABD (₺)</span>
          <span className="text-sm font-semibold text-slate-300 tabular-nums">
            ₺{data.breakdown.stocksUS.toLocaleString('tr-TR', { minimumFractionDigits: 0 })}
          </span>
        </div>
      </div>

      {/* Bekleyen emirlerin tuttuğu para.
          Yalnızca bir şey tutulurken görünüyor: sıfır bir satır, hiç emri
          olmayan kullanıcıya cevaplamadığı bir soru sormak olurdu.

          Toplama DAHİL DEĞİL -- bakiyeden zaten düşüldü. Ayrı yazılıyor
          çünkü sorulan soru "toplamım ne" değil, nakit neden eksildi:
          nedeni yazılmayan bir eksilme bir hataya benziyor. */}
      {data.blockedTRY > 0 && (
        <p className="mt-3 border-t border-white/10 pt-3 text-[11px] text-slate-400">
          Bekleyen emirler için{' '}
          <span className="font-semibold tabular-nums text-amber-400">
            ₺{data.blockedTRY.toLocaleString('tr-TR', { minimumFractionDigits: 0 })}
          </span>{' '}
          bloke edildi.
        </p>
      )}
    </div>
  )
}
