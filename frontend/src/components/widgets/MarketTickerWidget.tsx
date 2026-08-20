import { useEffect, useState } from 'react'
import { apiClient } from '../../api/client'
import type { MarketTicker } from '../../api/client'
import { useLiveRows } from '../../hooks/useLiveRows'

/**
 * Piyasa özeti şeridi — endeks ve kur başlıkları.
 *
 * Açılışta `/api/market/tickers`'tan çekilir, ardından canlı akışla güncellenir.
 * Sunucu ham sembolü döndürür (`XU100`, `USDTRY`); ekranda görünen ad ve birim
 * burada eşlenir, çünkü bunlar sunum tercihi — veri değil.
 */

const DISPLAY: Record<string, { label: string; unit: string }> = {
  XU100: { label: 'BIST 100', unit: 'puan' },
  USDTRY: { label: 'USD/TRY', unit: '₺' },
  EURTRY: { label: 'EUR/TRY', unit: '₺' },
  XAUUSD: { label: 'Altın (ons)', unit: '$' },
}

export default function MarketTickerWidget() {
  const [fetched, setFetched] = useState<MarketTicker[]>([])
  const tickers = useLiveRows(fetched)

  useEffect(() => {
    apiClient
      .getMarketTickers()
      .then(setFetched)
      .catch((error) => console.error('Failed to load tickers', error))
  }, [])

  return (
    <div className="flex flex-col h-full">
      <h3 className="text-sm font-semibold text-slate-400 mb-4">Piyasa Özeti</h3>
      <div className="grid grid-cols-2 gap-4">
        {tickers.map(t => {
          const display = DISPLAY[t.symbol] ?? { label: t.symbol, unit: '' }
          const changePercent = t.changePercent ?? 0
          return (
            <div key={t.symbol} className="flex flex-col p-3 bg-white/5 rounded-xl border border-white/10">
              <span className="text-xs text-slate-400 font-medium">{display.label}</span>
              <span className="text-sm font-bold text-white mt-1">
                {t.price.toLocaleString('tr-TR', { maximumFractionDigits: 2 })} {display.unit}
              </span>
              <span className={`text-xs font-semibold mt-1 ${changePercent < 0 ? 'text-rose-500' : 'text-emerald-500'}`}>
                {changePercent > 0 ? '+' : ''}{changePercent.toFixed(2)}%
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
