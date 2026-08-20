import { describe, expect, it } from 'vitest'
import { buildComparisonChartData, generateComparisonSeries } from './comparisonSeries'

describe('generateComparisonSeries', () => {
  it('ilk değer her zaman 0 ile başlar', () => {
    const series = generateComparisonSeries('THYAO', 30)
    expect(series[0]).toBe(0)
  })

  it('istenen gün sayısı kadar değer üretir', () => {
    const series = generateComparisonSeries('THYAO', 30)
    expect(series).toHaveLength(30)
  })

  it('days=1 verildiğinde sadece başlangıç değerini döner', () => {
    const series = generateComparisonSeries('THYAO', 1)
    expect(series).toEqual([0])
  })

  it('aynı seed ve gün sayısı her zaman aynı seriyi üretir (deterministik)', () => {
    const first = generateComparisonSeries('GARAN', 90)
    const second = generateComparisonSeries('GARAN', 90)
    expect(first).toEqual(second)
  })

  it('farklı seed farklı bir seri üretir', () => {
    const thyao = generateComparisonSeries('THYAO', 90)
    const garan = generateComparisonSeries('GARAN', 90)
    expect(thyao).not.toEqual(garan)
  })

  it('boş string seed ile bile hata vermeden çalışır (hash fallback)', () => {
    const series = generateComparisonSeries('', 10)
    expect(series).toHaveLength(10)
    expect(Number.isFinite(series[9])).toBe(true)
  })
})

describe('buildComparisonChartData', () => {
  it('anahtar listesi boşken bile her gün için bir date noktası döner', () => {
    const data = buildComparisonChartData([], 5)
    expect(data).toHaveLength(5)
    for (const point of data) {
      expect(Object.keys(point)).toEqual(['date'])
    }
  })

  it('her seçili anahtar için sayısal bir seri kolonu ekler', () => {
    const data = buildComparisonChartData(['THYAO', 'GARAN'], 10)
    expect(data).toHaveLength(10)
    for (const point of data) {
      expect(typeof point.date).toBe('string')
      expect(typeof point.THYAO).toBe('number')
      expect(typeof point.GARAN).toBe('number')
    }
  })

  it('son nokta bugünün tarihini (gg.aa formatında) taşır', () => {
    const data = buildComparisonChartData(['THYAO'], 3)
    const expectedToday = new Date().toLocaleDateString('tr-TR', { day: '2-digit', month: '2-digit' })
    expect(data[data.length - 1].date).toBe(expectedToday)
  })

  it('değerler en fazla 2 ondalık basamağa yuvarlanır', () => {
    const data = buildComparisonChartData(['THYAO'], 40)
    for (const point of data) {
      const value = point.THYAO as number
      expect(value).toBe(Number(value.toFixed(2)))
    }
  })
})
