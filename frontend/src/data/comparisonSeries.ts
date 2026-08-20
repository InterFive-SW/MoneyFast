/**
 * Karşılaştırma grafikleri için paylaşılan, deterministik (seed'li) mock zaman serisi üreteci.
 * Hisseler, Fonlar ve Endeksler karşılaştırma bileşenleri aynı üreteci kullanır —
 * aynı sembol/kod her zaman aynı seriyi üretir, apiClient'a bağımlılık yok.
 */

/** Basit, deterministik string -> sayı seed */
function hashSeed(text: string): number {
  let hash = 0
  for (let i = 0; i < text.length; i++) {
    hash = (hash << 5) - hash + text.charCodeAt(i)
    hash |= 0
  }
  return Math.abs(hash) || 1
}

/** mulberry32 — küçük, bağımlılıksız, seed'lenebilir PRNG */
function mulberry32(seed: number) {
  let a = seed
  return function () {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** Anahtara özel, deterministik, gün bazlı kümülatif % değişim serisi (mock) */
export function generateComparisonSeries(seedKey: string, days: number): number[] {
  const rand = mulberry32(hashSeed(seedKey))
  const values: number[] = [0]
  let cumulative = 0
  for (let i = 1; i < days; i++) {
    const dailyMove = (rand() - 0.48) * 2.2 // hafif pozitif eğilim, ~±2.2% günlük oynaklık
    cumulative += dailyMove
    values.push(cumulative)
  }
  return values
}

/** Seçilen anahtarlar için ortak tarih eksenli, recharts'a hazır karşılaştırma verisi üretir */
export function buildComparisonChartData(keys: string[], days: number): Record<string, number | string>[] {
  const seriesByKey = keys.map((key) => ({ key, values: generateComparisonSeries(key, days) }))
  const today = new Date()

  return Array.from({ length: days }, (_, dayIndex) => {
    const date = new Date(today)
    date.setDate(date.getDate() - (days - 1 - dayIndex))
    const point: Record<string, number | string> = {
      date: date.toLocaleDateString('tr-TR', { day: '2-digit', month: '2-digit' }),
    }
    seriesByKey.forEach(({ key, values }) => {
      point[key] = Number(values[dayIndex].toFixed(2))
    })
    return point
  })
}
