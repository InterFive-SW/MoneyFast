import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Emir akışının durumu: gir -> gözden geçir -> kabul et -> 5 sn -> gerçekleşir.
 *
 * Önceki akışta tek bir "ONAYLA" düğmesi vardı ve o tıklama hem öneriyi
 * hazırlıyor hem onaylıyordu: adet yazmakla paranın hareket etmesi arasında
 * hiçbir özet ekranı yoktu.
 *
 * **Yetkilendiren şey "Kabul et" tıklaması.** Geri sayım ondan SONRA gelen bir
 * mühlet; onun yerine geçen bir şey değil. CLAUDE.md'nin kuralı böyle
 * korunuyor: onay kullanıcının kendi eylemiyle veriliyor.
 *
 * Mantık burada, bileşende değil: kapsama kapısı (`vitest.config.ts`)
 * `src/hooks/**` altını sayıyor, JSX'i saymıyor -- ve paranın hareket
 * ettiği yer, test edilebilir olan taraf olmalı.
 */

/** Kabul ile gerçekleşme arasındaki mühlet. */
export const GRACE_SECONDS = 5

export type TradeStage =
  /** Adım 1: enstrüman, yön ve tutar giriliyor. */
  | 'entry'
  /** Adım 2: özet ekranda, "Reddet" ve "Kabul et" bekliyor. */
  | 'review'
  /** Kabul edildi; geri sayım işliyor. */
  | 'countdown'
  /** Sunucuya gidiliyor. */
  | 'submitting'
  | 'done'
  | 'error'

export interface TradeFlowOptions {
  /** Emri gerçekleştirir. Yalnızca geri sayım bittiğinde ya da kullanıcı
   *  beklemeden onayladığında çağrılır. */
  onSubmit: () => Promise<void>
  /** Hangi adımdan başlanacağı. Sohbet widget'ı `review`'dan başlıyor:
   *  öneriyi ajan zaten hazırladı, kullanıcının girecek bir şeyi yok. */
  initialStage?: TradeStage
}

export interface TradeFlow {
  stage: TradeStage
  /** Geri sayımda kalan saniye. Diğer adımlarda `GRACE_SECONDS`. */
  remaining: number
  error: string | null
  /** Adım 1'den özete. */
  review: () => void
  /** Özetten geri sayıma. Yetkilendiren tıklama BU. */
  accept: () => void
  /** Özette "Reddet": hiçbir şey gönderilmez. */
  reject: () => void
  /** Geri sayımda "İşlemi düzenle": saat durur, girilenler korunur. */
  edit: () => void
  /** Her yerden "İptal": akış biter. */
  cancel: () => void
  /** Geri sayımı beklemeden gönder. */
  submitNow: () => void
}

export function useTradeFlow({
  onSubmit,
  initialStage = 'entry',
}: TradeFlowOptions): TradeFlow {
  const [stage, setStage] = useState<TradeStage>(initialStage)
  const [remaining, setRemaining] = useState(GRACE_SECONDS)
  const [error, setError] = useState<string | null>(null)
  // Gönderim tek sefer. Geri sayım bitişi ile "hemen onayla" tıklaması aynı
  // ana denk gelirse iki emir gider ve kullanıcı iki kez alım yapmış olur.
  const submitted = useRef(false)

  const send = useCallback(async () => {
    if (submitted.current) return
    submitted.current = true
    setStage('submitting')
    try {
      await onSubmit()
      setStage('done')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Emir iletilemedi.')
      setStage('error')
    }
  }, [onSubmit])

  useEffect(() => {
    if (stage !== 'countdown') return
    if (remaining <= 0) {
      void send()
      return
    }
    const timer = setTimeout(() => setRemaining((value) => value - 1), 1000)
    return () => clearTimeout(timer)
  }, [stage, remaining, send])

  const review = useCallback(() => {
    setError(null)
    setStage('review')
  }, [])

  const accept = useCallback(() => {
    submitted.current = false
    setRemaining(GRACE_SECONDS)
    setStage('countdown')
  }, [])

  const reject = useCallback(() => {
    // Hiçbir şey hazırlanmadı ve hiçbir şey gönderilmiyor. Adım 1'e dönmek,
    // reddi "biraz daha düşün" gibi okuyacaktı; reddetmek bitirmektir.
    setStage('entry')
    setRemaining(GRACE_SECONDS)
  }, [])

  const edit = useCallback(() => {
    // Saat durur ve girilenler KORUNUR: düzenlemek için baştan yazmak
    // gerekseydi, düğme "iptal"in başka bir adı olurdu.
    setStage('entry')
    setRemaining(GRACE_SECONDS)
  }, [])

  const cancel = useCallback(() => {
    setStage('entry')
    setRemaining(GRACE_SECONDS)
    setError(null)
  }, [])

  const submitNow = useCallback(() => { void send() }, [send])

  return {
    stage, remaining, error,
    review, accept, reject, edit, cancel, submitNow,
  }
}
