/**
 * Emir akışı.
 *
 * Önceki akışta tek bir "ONAYLA" düğmesi vardı ve o tıklama hem öneriyi
 * hazırlıyor hem onaylıyordu: adet yazmakla paranın hareket etmesi arasında
 * hiçbir özet ekranı yoktu.
 *
 * Buradaki en önemli iddia: **hiçbir şey "Kabul et" tıklanmadan
 * gönderilmez.** Geri sayım o tıklamadan SONRA gelen bir mühlet, onun yerine
 * geçen bir şey değil.
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { GRACE_SECONDS, useTradeFlow } from './useTradeFlow'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

function setup(onSubmit = vi.fn().mockResolvedValue(undefined), initialStage?: 'entry' | 'review') {
  const view = renderHook(() =>
    useTradeFlow(initialStage ? { onSubmit, initialStage } : { onSubmit }),
  )
  return { ...view, onSubmit }
}

/** Sahte saati `seconds` kadar ilerletir. */
async function tick(seconds: number) {
  for (let i = 0; i < seconds; i += 1) {
    await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
  }
}

describe('nothing is sent without an accept', () => {
  it('girişte hiçbir şey gönderilmez', async () => {
    const { onSubmit } = setup()
    await tick(GRACE_SECONDS + 3)
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('özet ekranda beklemek emri göndermez', async () => {
    const { result, onSubmit } = setup()
    act(() => result.current.review())
    await tick(GRACE_SECONDS + 3)

    expect(result.current.stage).toBe('review')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('REDDET hiçbir şey göndermez ve akışı bitirir', async () => {
    const { result, onSubmit } = setup()
    act(() => result.current.review())
    act(() => result.current.reject())
    await tick(GRACE_SECONDS + 3)

    expect(result.current.stage).toBe('entry')
    expect(onSubmit).not.toHaveBeenCalled()
  })
})

describe('kabul ve mühlet', () => {
  it('kabul geri sayımı başlatır', () => {
    const { result } = setup()
    act(() => result.current.review())
    act(() => result.current.accept())

    expect(result.current.stage).toBe('countdown')
    expect(result.current.remaining).toBe(GRACE_SECONDS)
  })

  it('saniyeler işler ve sonunda gönderilir', async () => {
    const { result, onSubmit } = setup()
    act(() => result.current.review())
    act(() => result.current.accept())

    await tick(1)
    expect(result.current.remaining).toBe(GRACE_SECONDS - 1)
    expect(onSubmit).not.toHaveBeenCalled()

    await tick(GRACE_SECONDS)
    expect(onSubmit).toHaveBeenCalledTimes(1)
    expect(result.current.stage).toBe('done')
  })

  it('beklemeden onaylamak hemen gönderir', async () => {
    const { result, onSubmit } = setup()
    act(() => result.current.review())
    act(() => result.current.accept())
    await act(async () => { result.current.submitNow() })

    expect(onSubmit).toHaveBeenCalledTimes(1)
  })

  it('düğmeye iki kez basmak ÇİFT emir üretmez', async () => {
    /* Gerçek durum: kullanıcı "Onayla"ya çift tıklıyor. İkinci tıklama ilk
       gönderim daha durumu değiştirmeden gelirse iki emir giderdi. */
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    const { result } = setup(onSubmit)
    act(() => result.current.review())
    act(() => result.current.accept())

    await act(async () => {
      result.current.submitNow()
      result.current.submitNow()
    })

    expect(onSubmit).toHaveBeenCalledTimes(1)
  })

  it('geri sayım bitişi ile hemen onay ÇİFT emir üretmez', async () => {
    /* İkisi aynı ana denk gelirse kullanıcı iki kez alım yapmış olurdu. */
    const { result, onSubmit } = setup()
    act(() => result.current.review())
    act(() => result.current.accept())
    await act(async () => { result.current.submitNow() })
    await tick(GRACE_SECONDS + 2)

    expect(onSubmit).toHaveBeenCalledTimes(1)
  })
})

describe('geri sayım sırasında', () => {
  it('İŞLEMİ DÜZENLE saati durdurur ve girişe döner', async () => {
    const { result, onSubmit } = setup()
    act(() => result.current.review())
    act(() => result.current.accept())
    await tick(2)
    act(() => result.current.edit())
    await tick(GRACE_SECONDS + 3)

    expect(result.current.stage).toBe('entry')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('düzenlemeden sonra mühlet baştan başlar', () => {
    const { result } = setup()
    act(() => result.current.review())
    act(() => result.current.accept())
    act(() => result.current.edit())
    expect(result.current.remaining).toBe(GRACE_SECONDS)
  })

  it('İPTAL her şeyi bitirir', async () => {
    const { result, onSubmit } = setup()
    act(() => result.current.review())
    act(() => result.current.accept())
    await tick(2)
    act(() => result.current.cancel())
    await tick(GRACE_SECONDS + 3)

    expect(result.current.stage).toBe('entry')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('düzenleyip yeniden kabul etmek çalışır', async () => {
    const { result, onSubmit } = setup()
    act(() => result.current.review())
    act(() => result.current.accept())
    act(() => result.current.edit())
    act(() => result.current.review())
    act(() => result.current.accept())
    await tick(GRACE_SECONDS + 1)

    expect(onSubmit).toHaveBeenCalledTimes(1)
  })
})

describe('hata', () => {
  it('başarısız emir hatayı gösterir ve akışı bitirmez', async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error('Bakiye yetersiz.'))
    const { result } = setup(onSubmit)
    act(() => result.current.review())
    act(() => result.current.accept())
    await tick(GRACE_SECONDS + 1)

    expect(result.current.stage).toBe('error')
    expect(result.current.error).toBe('Bakiye yetersiz.')
  })

  it('mesajsız bir hata da bir şey söyler', async () => {
    const onSubmit = vi.fn().mockRejectedValue('kim bilir')
    const { result } = setup(onSubmit)
    act(() => result.current.review())
    act(() => result.current.accept())
    await tick(GRACE_SECONDS + 1)

    expect(result.current.error).toBeTruthy()
  })

  it('iptal hatayı temizler', async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error('boom'))
    const { result } = setup(onSubmit)
    act(() => result.current.review())
    act(() => result.current.accept())
    await tick(GRACE_SECONDS + 1)
    expect(result.current.error).toBeTruthy()

    act(() => result.current.cancel())
    expect(result.current.error).toBeNull()
  })
})

describe('sohbet widget başlangıcı', () => {
  it('özetten başlayabilir', () => {
    /* Öneriyi ajan zaten hazırladı; kullanıcının girecek bir şeyi yok. */
    const { result } = setup(vi.fn(), 'review')
    expect(result.current.stage).toBe('review')
  })
})
