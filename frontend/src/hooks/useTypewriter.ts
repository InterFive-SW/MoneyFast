import { useEffect, useRef, useState } from 'react'

/** Karakter/saniye. Okuma hızının biraz üzerinde: metin "yazılıyor" hissi
 *  versin ama kullanıcıyı bekletmesin. */
const CHARS_PER_SECOND = 900

/** Bu uzunluğun üzerindeki yanıtlar anında gösterilir. Uzun bir tabloyu
 *  harf harf yazdırmak gösteri olur, bilgi değil. */
const INSTANT_ABOVE = 2200

/**
 * Tamamlanmış bir metni yazılıyormuş gibi ortaya çıkarır.
 *
 * Model token'ları DEĞİL, onaylanmış metin yazılır. Graf fail-closed:
 * uygunluk kapısının engellediği bir taslak kullanıcıya ulaşmamalı. Üretim
 * anında akıtılsaydı, kapının sonradan geri alacağı bir metin çoktan ekranda
 * olurdu. Gerçek ilerleme `stage` olaylarıyla ayrıca akıyor; buradaki etki
 * yalnızca sunum.
 *
 * `prefers-reduced-motion` açıksa animasyon tamamen atlanır.
 */
export function useTypewriter(full: string, enabled = true): string {
  const [shown, setShown] = useState(enabled ? '' : full)
  const frame = useRef<number>(0)

  useEffect(() => {
    const reduced =
      typeof window !== 'undefined' &&
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches

    if (!enabled || reduced || full.length > INSTANT_ABOVE) {
      setShown(full)
      return
    }

    setShown('')
    const startedAt = performance.now()

    const tick = () => {
      const elapsed = (performance.now() - startedAt) / 1000
      const count = Math.floor(elapsed * CHARS_PER_SECOND)
      if (count >= full.length) {
        setShown(full)
        return
      }
      setShown(full.slice(0, count))
      frame.current = requestAnimationFrame(tick)
    }
    frame.current = requestAnimationFrame(tick)

    return () => cancelAnimationFrame(frame.current)
  }, [full, enabled])

  return shown
}
