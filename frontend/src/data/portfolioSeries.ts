/**
 * Portfolio performance series — range helpers over REAL candles.
 *
 * This module used to generate its own prices: a seeded mulberry32 random walk
 * from `START_PRICE = 80000` with a hardcoded +50% drift, 730 days of it. Its
 * own header said an API call would replace it, and `/api/market/candles` now
 * serves genuine bars, so the generator is gone and only the slicing and date
 * helpers remain.
 */

export interface Candle {
  time: number // Unix timestamp (saniye)
  open: number
  high: number
  low: number
  close: number
  value?: number // hacim
  color?: string // hacim çubuğunun rengi
}

export type RangePreset = 'Gün' | 'Hafta' | 'Ay' | '3 Ay' | 'Yıl'

export const RANGE_PRESETS: RangePreset[] = ['Gün', 'Hafta', 'Ay', '3 Ay', 'Yıl']

const DAY = 86_400

/** Seconds per preset, used to slice back from the newest bar. */
const PRESET_DAYS: Record<RangePreset, number> = {
  'Gün': 1,
  'Hafta': 7,
  'Ay': 30,
  '3 Ay': 90,
  'Yıl': 365,
}

/** The window a preset covers, relative to the series actually loaded. */
export function presetRangeFor(series: Candle[], preset: RangePreset): { from: number; to: number } {
  if (!series.length) return { from: 0, to: 0 }
  const to = series[series.length - 1].time
  return { from: to - PRESET_DAYS[preset] * DAY, to }
}

/** The bars falling inside a window. */
export function sliceSeries(series: Candle[], from: number, to: number): Candle[] {
  return series.filter((candle) => candle.time >= from && candle.time <= to)
}

/** `YYYY-MM-DD` (native date input değeri) → Unix saniye. */
export function dateInputToSeconds(value: string, endOfDay = false): number {
  if (!value) return NaN
  const ms = endOfDay ? Date.parse(`${value}T23:59:59`) : Date.parse(`${value}T00:00:00`)
  return Number.isNaN(ms) ? NaN : Math.floor(ms / 1000)
}

/** Unix saniye → `YYYY-MM-DD` (native date input min/max değeri için). */
export function secondsToDateInput(seconds: number): string {
  const d = new Date(seconds * 1000)
  const month = `${d.getMonth() + 1}`.padStart(2, '0')
  const day = `${d.getDate()}`.padStart(2, '0')
  return `${d.getFullYear()}-${month}-${day}`
}
