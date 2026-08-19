import type { MarketInstrument } from './mockData'

export type ColumnSetKey = 'getiri' | 'degerleme' | 'karlilik' | 'borcluluk' | 'buyume' | 'bilanco' | 'gelirTablosu' | 'nakitAkim'

export interface MetricColumn {
  key:      keyof MarketInstrument
  label:    string
  suffix?:  string  // '%', 'x' vb.
  compact?: boolean // büyük para birimleri için Mn/Mr/Tn kısaltması
}

export interface ColumnSetDef {
  key:     ColumnSetKey
  label:   string
  metrics: MetricColumn[] // 'getiri' seti özel render edilir (Hacim + Piyasa Değeri + 52 Hafta), burada boş
}

/** Hisseler tablosundaki hazır kolon setleri — her biri tek tıkla ilgili metrik grubunu getirir */
export const COLUMN_SETS: ColumnSetDef[] = [
  { key: 'getiri', label: 'Getiri', metrics: [] },
  { key: 'degerleme', label: 'Değerleme', metrics: [
    { key: 'pe', label: 'F/K', suffix: 'x' },
    { key: 'pb', label: 'PD/DD', suffix: 'x' },
    { key: 'evEbitda', label: 'FD/FAVÖK', suffix: 'x' },
  ] },
  { key: 'karlilik', label: 'Kârlılık', metrics: [
    { key: 'netMargin', label: 'Net Kâr Marjı', suffix: '%' },
    { key: 'roe', label: 'ROE', suffix: '%' },
  ] },
  { key: 'borcluluk', label: 'Borçluluk', metrics: [
    { key: 'debtToEquity', label: 'Borç/Özkaynak', suffix: 'x' },
  ] },
  { key: 'buyume', label: 'Büyüme', metrics: [
    { key: 'revenueGrowth', label: 'Gelir Büyümesi (Yıllık)', suffix: '%' },
  ] },
  { key: 'bilanco', label: 'Bilanço', metrics: [
    { key: 'totalAssets', label: 'Toplam Varlıklar', compact: true },
  ] },
  { key: 'gelirTablosu', label: 'Gelir Tablosu', metrics: [
    { key: 'revenueGrowth', label: 'Gelir Büyümesi', suffix: '%' },
    { key: 'netMargin', label: 'Net Kâr Marjı', suffix: '%' },
  ] },
  { key: 'nakitAkim', label: 'Nakit Akım', metrics: [
    { key: 'operatingCashFlow', label: 'Faaliyet Nakit Akışı', compact: true },
  ] },
]

export function formatMetricValue(item: MarketInstrument, metric: MetricColumn): string {
  const raw = item[metric.key]
  if (typeof raw !== 'number') return '—'
  if (metric.compact) {
    return new Intl.NumberFormat('tr-TR', { notation: 'compact', maximumFractionDigits: 1 }).format(raw) + ' ' + item.unit
  }
  const formatted = raw.toLocaleString('tr-TR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
  return metric.suffix ? `${formatted}${metric.suffix}` : formatted
}
