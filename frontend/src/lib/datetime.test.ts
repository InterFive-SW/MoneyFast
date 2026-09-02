/**
 * Saat dilimi.
 *
 * `toLocaleTimeString('tr-TR')` diliml verilmezse TARAYICININ dilimini
 * kullanır. UTC saatli bir kapta çalıştığında ekrandaki her saat UTC
 * yazıyordu: BIST 10:00'da açılırken arayüz 07:00 diyordu.
 *
 * Testler `process.env.TZ`'yi UTC'ye zorluyor — kendi makinesi zaten
 * Istanbul olan biri, kırık bir kodu yeşil görürdü.
 */
import { describe, expect, it } from 'vitest'
import {
  APP_TIME_ZONE, formatDate, formatDateTime, formatLongDate, formatTime,
  msUntilLocalMidnight,
} from './datetime'

/* Test ortamının dilimi `vitest.config.ts`'te UTC'ye sabitli: kendi makinesi
   zaten Istanbul olan biri, kırık bir kodu yeşil görürdü. */

/** 31 Ağustos 2026, 21:32 UTC = 1 Eylül 00:32 Istanbul. */
const LATE_UTC = '2026-08-31T21:32:00Z'
/** 31 Ağustos 2026, 09:15 UTC = 12:15 Istanbul. */
const MID_UTC = '2026-08-31T09:15:00Z'

describe('formatTime', () => {
  it('UTC damgasını Türkiye saatiyle yazar', () => {
    expect(formatTime(MID_UTC)).toBe('12:15')
  })

  it('gün sınırını da doğru geçer', () => {
    /* 21:32 UTC ertesi günün 00:32'si. Tarayıcı dilimine bırakılsaydı
       "21:32" yazardı. */
    expect(formatTime(LATE_UTC)).toBe('00:32')
  })

  it('Date nesnesi de sayı da kabul eder', () => {
    expect(formatTime(new Date(MID_UTC))).toBe('12:15')
    expect(formatTime(new Date(MID_UTC).getTime())).toBe('12:15')
  })

  it('boş ve geçersiz değer "—" olur', () => {
    expect(formatTime(null)).toBe('—')
    expect(formatTime(undefined)).toBe('—')
    expect(formatTime('bir tarih değil')).toBe('—')
  })
})

describe('formatDate', () => {
  it('gün sınırını Türkiye saatine göre atar', () => {
    /* UTC'de hâlâ 31 Ağustos; Türkiye'de 1 Eylül. Tarihi tarayıcıya
       bırakmak, ekranın nerede açıldığına göre farklı GÜN göstermesi. */
    expect(formatDate(LATE_UTC)).toContain('01')
    expect(formatDate(LATE_UTC)).toContain('Eyl')
  })

  it('seçenekler geçirilebilir', () => {
    expect(formatDate(MID_UTC, { day: '2-digit', month: '2-digit' })).toBe('31/08')
  })

  it('boş değer "—" olur', () => {
    expect(formatDate(null)).toBe('—')
  })
})

describe('formatLongDate', () => {
  it('başlıktaki uzun biçim', () => {
    const text = formatLongDate(MID_UTC)
    expect(text).toContain('31')
    expect(text).toContain('Ağustos')
    expect(text).toContain('2026')
    expect(text.toLowerCase()).toContain('pazartesi')
  })
})

describe('formatDateTime', () => {
  it('tarih ve saati birlikte yazar', () => {
    expect(formatDateTime(MID_UTC)).toBe('31 Ağu 2026 12:15')
  })

  it('boş değer "—" olur', () => {
    expect(formatDateTime(null)).toBe('—')
  })
})

describe('msUntilLocalMidnight', () => {
  it('Türkiye gece yarısına kalan süreyi verir', () => {
    /* 09:15 UTC = 12:15 Istanbul -> 11 saat 45 dakika kaldı. */
    const ms = msUntilLocalMidnight(new Date(MID_UTC))
    expect(ms).toBe(((11 * 60 + 45) * 60) * 1000)
  })

  it('gece yarısını yeni geçmişse neredeyse tam gün verir', () => {
    const ms = msUntilLocalMidnight(new Date(LATE_UTC))
    expect(ms).toBe((23 * 3600 + 28 * 60) * 1000)
  })

  it('her zaman pozitif ve bir günü aşmaz', () => {
    const ms = msUntilLocalMidnight(new Date(MID_UTC))
    expect(ms).toBeGreaterThan(0)
    expect(ms).toBeLessThanOrEqual(24 * 60 * 60 * 1000)
  })

  it('dilim sabit', () => {
    expect(APP_TIME_ZONE).toBe('Europe/Istanbul')
  })
})
