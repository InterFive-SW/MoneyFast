import { describe, expect, it } from 'vitest'
import {
  RANGE_PRESETS,
  SERIES_END,
  SERIES_START,
  dateInputToSeconds,
  getSeries,
  presetRange,
  secondsToDateInput,
} from './portfolioSeries'

const DAY = 24 * 60 * 60
const PRESET_DAYS: Record<string, number> = { 'Gün': 1, 'Hafta': 7, 'Ay': 30, '3 Ay': 90, 'Yıl': 365 }

describe('SERIES_START / SERIES_END', () => {
  it('başlangıç bitişten önce gelir', () => {
    expect(SERIES_START).toBeLessThan(SERIES_END)
  })
})

describe('getSeries', () => {
  it('geçersiz (NaN) from/to verildiğinde boş dizi döner', () => {
    expect(getSeries(NaN, SERIES_END)).toEqual([])
    expect(getSeries(SERIES_START, NaN)).toEqual([])
  })

  it('to, from\'dan küçük veya eşitse boş dizi döner', () => {
    expect(getSeries(SERIES_END, SERIES_START)).toEqual([])
    expect(getSeries(SERIES_START, SERIES_START)).toEqual([])
  })

  it('temel serinin tamamen dışındaki bir aralık için boş dizi döner', () => {
    const result = getSeries(SERIES_START - 1000 * DAY, SERIES_START - 999 * DAY)
    expect(result).toEqual([])
  })

  it('~1 günlük aralıkta saatlik mum boyutunu kullanır (gruplama yapılmaz)', () => {
    const result = getSeries(SERIES_END - 1 * DAY, SERIES_END)
    expect(result.length).toBeGreaterThan(0)
    expect(result.length).toBeLessThanOrEqual(25)
  })

  it('~10 günlük aralıkta 4 saatlik gruplama uygular', () => {
    const result = getSeries(SERIES_END - 10 * DAY, SERIES_END)
    expect(result.length).toBeGreaterThan(0)
    // 10 gün * 24 saat = 240 saatlik mum, 4 saatlik kovaya girince çok daha az mum kalmalı
    expect(result.length).toBeLessThan(240)
  })

  it('~100 günlük aralıkta günlük gruplama uygular', () => {
    const result = getSeries(SERIES_END - 100 * DAY, SERIES_END)
    expect(result.length).toBeGreaterThan(0)
    expect(result.length).toBeLessThanOrEqual(101)
  })

  it('500 günlük aralıkta haftalık gruplama uygular', () => {
    const result = getSeries(SERIES_START, SERIES_START + 500 * DAY)
    expect(result.length).toBeGreaterThan(0)
    // 500 gün / 7 ~ 71-72 mum civarı, günlük mum sayısından (500) çok daha az olmalı
    expect(result.length).toBeLessThan(100)
  })

  it('döndürülen mumlar zaman sırasına göredir ve OHLC tutarlıdır', () => {
    const result = getSeries(SERIES_END - 30 * DAY, SERIES_END)
    for (let i = 1; i < result.length; i++) {
      expect(result[i].time).toBeGreaterThan(result[i - 1].time)
    }
    for (const candle of result) {
      expect(candle.high).toBeGreaterThanOrEqual(candle.low)
    }
  })
})

describe('presetRange', () => {
  it('her hazır aralık için doğru gün sayısı kadar geriye gider ve bugüne (SERIES_END) kadar uzanır', () => {
    for (const preset of RANGE_PRESETS) {
      const { from, to } = presetRange(preset)
      expect(to).toBe(SERIES_END)
      expect(from).toBe(SERIES_END - PRESET_DAYS[preset] * DAY)
    }
  })
})

describe('dateInputToSeconds', () => {
  it('boş string verilirse NaN döner', () => {
    expect(Number.isNaN(dateInputToSeconds(''))).toBe(true)
  })

  it('geçersiz bir tarih string\'i verilirse NaN döner', () => {
    expect(Number.isNaN(dateInputToSeconds('gecersiz-tarih'))).toBe(true)
  })

  it('günün başlangıcını (00:00:00) saniyeye çevirir', () => {
    const expected = Math.floor(Date.parse('2026-01-15T00:00:00') / 1000)
    expect(dateInputToSeconds('2026-01-15')).toBe(expected)
  })

  it('endOfDay=true ise günün sonunu (23:59:59) saniyeye çevirir', () => {
    const expected = Math.floor(Date.parse('2026-01-15T23:59:59') / 1000)
    expect(dateInputToSeconds('2026-01-15', true)).toBe(expected)
  })
})

describe('secondsToDateInput', () => {
  it('Unix saniyeyi YYYY-MM-DD formatına çevirir', () => {
    const seconds = 1_700_000_000
    const d = new Date(seconds * 1000)
    const expected = `${d.getFullYear()}-${`${d.getMonth() + 1}`.padStart(2, '0')}-${`${d.getDate()}`.padStart(2, '0')}`
    expect(secondsToDateInput(seconds)).toBe(expected)
  })

  it('dateInputToSeconds ile round-trip tutarlıdır', () => {
    const input = '2026-03-05'
    const seconds = dateInputToSeconds(input)
    expect(secondsToDateInput(seconds)).toBe(input)
  })
})
