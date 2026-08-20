import { describe, expect, it } from 'vitest'
import { COLUMN_SETS, formatMetricValue } from './columnSets'
import { findInstrument } from './mockData'

// THYAO: tüm finansal metrikler dolu bir BIST hissesi (pe/pb/evEbitda/totalAssets vb.)
const thyao = findInstrument('THYAO')!
// BTC: kripto — finansal rasyo alanları (pe, pb, ...) kasıtlı olarak tanımsız
const btc = findInstrument('BTC')!

describe('COLUMN_SETS', () => {
  it('8 hazır kolon seti tanımlıdır', () => {
    expect(COLUMN_SETS).toHaveLength(8)
  })

  it('her set benzersiz bir key taşır', () => {
    const keys = COLUMN_SETS.map((set) => set.key)
    expect(new Set(keys).size).toBe(keys.length)
  })

  it('"getiri" seti özel render edildiği için boş metrics dizisine sahiptir', () => {
    const getiri = COLUMN_SETS.find((set) => set.key === 'getiri')
    expect(getiri?.metrics).toEqual([])
  })

  it('getiri dışındaki her set en az bir metrik içerir', () => {
    const others = COLUMN_SETS.filter((set) => set.key !== 'getiri')
    for (const set of others) {
      expect(set.metrics.length).toBeGreaterThan(0)
    }
  })

  it('her metriğin key alanı gerçek bir MarketInstrument alanına karşılık gelir', () => {
    for (const set of COLUMN_SETS) {
      for (const metric of set.metrics) {
        expect(Object.prototype.hasOwnProperty.call(thyao, metric.key)).toBe(true)
      }
    }
  })
})

describe('formatMetricValue', () => {
  it('değer sayı değilse (örn. kripto varlıkta F/K tanımsızsa) "—" döner', () => {
    const result = formatMetricValue(btc, { key: 'pe', label: 'F/K', suffix: 'x' })
    expect(result).toBe('—')
  })

  it('compact=true ise değeri Mn/Mr/Tn kısaltmasıyla ve birimle birlikte döner', () => {
    const expected =
      new Intl.NumberFormat('tr-TR', { notation: 'compact', maximumFractionDigits: 1 }).format(thyao.totalAssets!) +
      ' ' +
      thyao.unit
    const result = formatMetricValue(thyao, { key: 'totalAssets', label: 'Toplam Varlıklar', compact: true })
    expect(result).toBe(expected)
  })

  it('suffix tanımlıysa formatlanmış değerin sonuna eklenir', () => {
    const expected = thyao.pe!.toLocaleString('tr-TR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + 'x'
    const result = formatMetricValue(thyao, { key: 'pe', label: 'F/K', suffix: 'x' })
    expect(result).toBe(expected)
  })

  it('ne suffix ne compact varsa sadece formatlanmış sayıyı döner', () => {
    const expected = thyao.price.toLocaleString('tr-TR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
    const result = formatMetricValue(thyao, { key: 'price', label: 'Fiyat' })
    expect(result).toBe(expected)
  })
})
