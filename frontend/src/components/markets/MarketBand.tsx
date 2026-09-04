import { useEffect, useMemo, useRef, useState } from 'react'

import type { QuoteFrame } from '../../hooks/useMarketStream'
import { formatWithBase } from '../../lib/money'

interface MarketBandProps {
  symbols: string[]
  quotes: Record<string, QuoteFrame>
  rates: Record<string, number>
}

/** Bir kopyanın kabı aşması için gereken asgari kat. */
const MIN_TRACK_RATIO = 2

/** Kaydırma hızı: saniyede kaç piksel. Süre, içerik uzunluğundan türetilir. */
const PIXELS_PER_SECOND = 45

/**
 * Haber bandı gibi kesintisiz akan fiyat şeridi.
 *
 * Üç ayrı kusuru vardı:
 *
 * 1. **Tekrar görünüyordu.** Dikişsiz bir döngü için içerik iki kez basılır ve
 *    şerit tam yarısı kadar kaydırılır; beş sembolle iki kopya da aynı anda
 *    ekrana sığdığı için teknik `XU100 … AAPL XU100 … AAPL` diye görünür hâle
 *    geliyordu.
 * 2. **Sıfırlanıyordu.** Şerit kabından darsa arta kalan boşluk da kayıyor ve
 *    döngü görünür bir sıçramayla başa dönüyordu.
 * 3. Sabit bir listeydi; kullanıcının izlediğiyle ilgisi yoktu.
 *
 * Çözüm ölçmek: bir kopyanın genişliği kabın en az iki katı olana kadar liste
 * tekrarlanıyor. Böylece kopya sınırı hiçbir zaman ekranda olmuyor ve
 * kaydırılacak boşluk kalmıyor. Süre içerik uzunluğuyla orantılı, yani liste
 * uzadıkça hız değil yalnızca tur süresi artıyor.
 */
export default function MarketBand({ symbols, quotes, rates }: MarketBandProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const measureRef = useRef<HTMLDivElement>(null)
  const [repeats, setRepeats] = useState(MIN_TRACK_RATIO)
  const [duration, setDuration] = useState(30)

  const entries = useMemo(
    () =>
      symbols.map((symbol) => {
        const quote = quotes[symbol]
        return {
          symbol,
          // Fiyat kendi para biriminde, yanında yaklaşık TL karşılığı.
          // Birimsiz bir fiyat, okuyanı tahmine zorlar.
          text: quote
            ? formatWithBase(quote.price, quote.currency ?? 'TRY', rates)
            : '—',
          changePercent: quote?.changePercent ?? null,
        }
      }),
    [symbols, quotes, rates],
  )

  // Bir kopya kabın iki katına ulaşana kadar tekrarla.
  useEffect(() => {
    const container = containerRef.current
    const copy = measureRef.current
    if (!container || !copy) return

    function measure() {
      const width = copy!.scrollWidth / repeats
      const target = container!.clientWidth * MIN_TRACK_RATIO
      if (width <= 0) return
      const needed = Math.max(MIN_TRACK_RATIO, Math.ceil(target / width))
      if (needed !== repeats) setRepeats(needed)
      setDuration(Math.max(20, (width * needed) / PIXELS_PER_SECOND))
    }

    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(container)
    return () => observer.disconnect()
  }, [entries.length, repeats])

  if (entries.length === 0) return null

  // İki kopya: biri kayarken diğeri arkasından geliyor, translateX(-50%) tam
  // bir kopya kadar sürüyor ve döngü dikişsiz kapanıyor.
  const track = Array.from({ length: repeats }, (_, index) => index)

  return (
    <div
      ref={containerRef}
      className="group relative overflow-hidden rounded-xl border border-slate-800 bg-black/40 py-2.5"
      aria-label="Canlı piyasa şeridi"
    >
      <div
        className="flex w-max animate-marquee group-hover:[animation-play-state:paused] motion-reduce:animate-none"
        style={{ animationDuration: `${duration}s` }}
      >
        {[0, 1].map((half) => (
          <div key={half} ref={half === 0 ? measureRef : undefined} className="flex">
            {track.map((copy) => (
              <div key={copy} className="flex shrink-0">
                {entries.map((entry) => (
                  <div
                    key={`${copy}-${entry.symbol}`}
                    className="flex shrink-0 items-baseline gap-2 px-4"
                    aria-hidden={half === 1 || copy > 0}
                  >
                    <span className="text-xs font-semibold text-slate-400">
                      {entry.symbol}
                    </span>
                    <span className="text-sm font-semibold tabular-nums text-white">
                      {entry.text}
                    </span>
                    {entry.changePercent !== null && (
                      <span
                        className={`text-xs tabular-nums ${
                          entry.changePercent >= 0 ? 'text-emerald-400' : 'text-rose-400'
                        }`}
                      >
                        %{entry.changePercent.toFixed(2)}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}
