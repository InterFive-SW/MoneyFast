/**
 * Tooltip formatting.
 *
 * The rule these pin down: a value that is not a number is not zero. Recharts
 * hands the formatter `undefined` for a gap in a series, and rendering that as
 * "0" would draw a day the instrument did not trade as a day it was worthless.
 */
import { describe, expect, it } from 'vitest'
import { paddedDomain, seriesName, signedPercent, toNumber } from './chartFormat'

describe('toNumber', () => {
  it('passes a real number through', () => {
    expect(toNumber(12.5)).toBe(12.5)
  })

  it('parses a numeric string, because recharts sometimes hands one over', () => {
    expect(toNumber('12.5')).toBe(12.5)
  })

  it.each([undefined, null, '', '   ', 'abc', NaN, Infinity])(
    'returns null rather than 0 for %p',
    (value) => {
      expect(toNumber(value)).toBeNull()
    },
  )

  it('keeps a genuine zero', () => {
    // Distinct from "no value": 0% change is a measurement.
    expect(toNumber(0)).toBe(0)
  })
})

describe('signedPercent', () => {
  it('marks a gain with a plus so the direction is readable without colour', () => {
    expect(signedPercent(1.2)).toBe('+1.2%')
  })

  it('leaves a loss with its own minus', () => {
    expect(signedPercent(-1.2)).toBe('-1.2%')
  })

  it('does not sign a flat reading', () => {
    expect(signedPercent(0)).toBe('0%')
  })

  it('shows a dash when there is no value, not 0%', () => {
    expect(signedPercent(undefined)).toBe('—')
  })
})

describe('seriesName', () => {
  it('passes a string through', () => {
    expect(seriesName('THYAO')).toBe('THYAO')
  })

  it('stringifies a non-string label', () => {
    expect(seriesName(42)).toBe('42')
  })

  it('renders an absent label as empty rather than "undefined"', () => {
    expect(seriesName(undefined)).toBe('')
    expect(seriesName(null)).toBe('')
  })
})

describe('paddedDomain', () => {
  it('aralığı verinin kendisinden türetir, sıfırdan değil', () => {
    /* Recharts varsayılanı `[0, "auto"]`; 1,41-1,43 Mn arası gezinen bir
       seri o eksende düz çizgi oluyordu. */
    const [low, high] = paddedDomain([1_410_000, 1_425_000, 1_418_000])
    expect(low).toBeGreaterThan(1_400_000)
    expect(high).toBeLessThan(1_440_000)
    expect(low).toBeLessThan(1_410_000)
    expect(high).toBeGreaterThan(1_425_000)
  })

  it('boşluk aralığın yüzdesi kadar', () => {
    /* Sabit bir boşluk, dar bir seride geniş bir seriden farklı davranırdı. */
    const [low, high] = paddedDomain([100, 200])
    expect(high - 200).toBeCloseTo(8, 5)
    expect(100 - low).toBeCloseTo(8, 5)
  })

  it('hiç değişmemiş seride bile sıfır yükseklikte eksen üretmez', () => {
    const [low, high] = paddedDomain([500, 500])
    expect(high).toBeGreaterThan(low)
  })

  it('tek noktalı seride de aralık var', () => {
    const [low, high] = paddedDomain([42])
    expect(high).toBeGreaterThan(low)
  })

  it('küçük değerlerde taban boşluk devreye giriyor', () => {
    /* %1'i 1'den küçük olan bir değerde oransal boşluk görünmez kalırdı. */
    const [low, high] = paddedDomain([2, 2])
    expect(high - low).toBeGreaterThanOrEqual(2)
  })

  it('sayı olmayanları atar, hepsi geçersizse güvenli aralık döner', () => {
    expect(paddedDomain([Number.NaN, Infinity])).toEqual([0, 1])
    const [low, high] = paddedDomain([Number.NaN, 10, 20])
    expect(low).toBeLessThan(10)
    expect(high).toBeGreaterThan(20)
  })
})
