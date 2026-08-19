/**
 * Portföy Performans Serisi (mock)
 *
 * Tek ve tutarlı bir temel seri üretir; hem hazır zaman aralıkları (Gün/Hafta/Ay/...)
 * hem de kullanıcının seçtiği serbest tarih aralığı bu serinin bir dilimidir.
 * Böylece aralıklar arası geçişte grafik tutarlı kalır (Ay, Yıl'ın son 30 günüdür).
 *
 * Veritabanı/gerçek fiyat verisi bağlandığında bu modülün yerini bir API çağrısı alacak;
 * `getSeries(from, to)` imzası bu geçişe uygun tasarlandı.
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

const PRESET_DAYS: Record<RangePreset, number> = {
  'Gün': 1,
  'Hafta': 7,
  'Ay': 30,
  '3 Ay': 90,
  'Yıl': 365,
}

const HOUR = 60 * 60
const DAY = 24 * HOUR
const BASE_DAYS = 730 // temel seri: son 2 yıl
const START_PRICE = 80000
const HOURLY_VOLATILITY = 260

const UP_COLOR = 'rgba(38, 166, 154, 0.5)'
const DOWN_COLOR = 'rgba(239, 83, 80, 0.5)'

/**
 * Tohumlu (seeded) rastgele sayı üreteci — mulberry32.
 * Math.random() yerine bunu kullanıyoruz ki grafik her sayfa yenilemesinde
 * değişmesin; aynı tohum her zaman aynı seriyi üretir.
 */
function mulberry32(seed: number): () => number {
  let a = seed
  return function () {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/**
 * Temel seriyi üretir: son BASE_DAYS gün boyunca saatlik mumlar.
 * Random walk — her mumun open'ı bir öncekinin close'undan türer.
 */
function generateBaseSeries(): Candle[] {
  const rand = mulberry32(20260818)
  const data: Candle[] = []

  const nowSec = Math.floor(Date.now() / 1000)
  // Saat başına hizala, böylece bucket sınırları düzgün otursun
  const endSec = nowSec - (nowSec % HOUR)
  const startSec = endSec - BASE_DAYS * DAY
  const totalHours = BASE_DAYS * 24

  let currentPrice = START_PRICE
  // Hafif yukarı eğilim: 2 yılda ~%50 büyüme hissi versin
  const drift = (START_PRICE * 0.5) / totalHours

  for (let i = 0; i < totalHours; i++) {
    const time = startSec + i * HOUR

    const open = currentPrice + (rand() - 0.5) * HOURLY_VOLATILITY
    const high = open + rand() * HOURLY_VOLATILITY
    const low = open - rand() * HOURLY_VOLATILITY
    const close = low + rand() * (high - low)

    data.push({
      time,
      open,
      high,
      low,
      close,
      value: Math.floor(rand() * 10000) + 5000,
      color: close >= open ? UP_COLOR : DOWN_COLOR,
    })

    currentPrice = close + drift
  }

  return data
}

/** Modül yüklenirken bir kez üretilir. */
const BASE: Candle[] = generateBaseSeries()

export const SERIES_START = BASE[0].time
export const SERIES_END = BASE[BASE.length - 1].time

/**
 * Mumları verilen kova (bucket) boyutuna göre gruplar.
 * open = ilk mumun open'ı, high = max, low = min, close = son mumun close'u,
 * hacim = toplam.
 */
function aggregate(candles: Candle[], bucketSeconds: number): Candle[] {
  if (bucketSeconds <= HOUR) return candles

  const out: Candle[] = []
  let bucket: Candle | null = null
  let bucketStart = 0

  for (const c of candles) {
    const start = c.time - (c.time % bucketSeconds)

    if (!bucket || start !== bucketStart) {
      if (bucket) out.push(bucket)
      bucketStart = start
      bucket = { ...c, time: start }
      continue
    }

    bucket.high = Math.max(bucket.high, c.high)
    bucket.low = Math.min(bucket.low, c.low)
    bucket.close = c.close
    bucket.value = (bucket.value ?? 0) + (c.value ?? 0)
  }

  if (bucket) out.push(bucket)

  // Renkleri gruplanmış mumun kendi yönüne göre yeniden hesapla
  for (const c of out) {
    c.color = c.close >= c.open ? UP_COLOR : DOWN_COLOR
  }

  return out
}

/**
 * Aralığın uzunluğuna göre mum boyutunu seçer.
 * Amaç: mum sayısını okunabilir bir bantta (~24-400) tutmak.
 */
function bucketSizeFor(spanSeconds: number): number {
  if (spanSeconds <= 2 * DAY) return HOUR
  if (spanSeconds <= 14 * DAY) return 4 * HOUR
  if (spanSeconds <= 400 * DAY) return DAY
  return 7 * DAY
}

/**
 * Temel seriyi [from, to] aralığına göre keser ve uygun mum boyutunda gruplar.
 * from/to saniye cinsinden Unix timestamp.
 */
export function getSeries(from: number, to: number): Candle[] {
  if (!Number.isFinite(from) || !Number.isFinite(to) || to <= from) return []

  const slice = BASE.filter((c) => c.time >= from && c.time <= to)
  if (slice.length === 0) return []

  return aggregate(slice, bucketSizeFor(to - from))
}

/** Hazır aralık için {from, to} döndürür — serbest aralıkla aynı kod yolunu kullanır. */
export function presetRange(preset: RangePreset): { from: number; to: number } {
  const to = SERIES_END
  return { from: to - PRESET_DAYS[preset] * DAY, to }
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
