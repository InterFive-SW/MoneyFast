/**
 * MoneyFast Dashboard — Yapay (Mock) Veri Katmanı
 *
 * Gerçek backend API entegrasyonu tamamlanana kadar widget bileşenlerinin
 * eksiksiz ve bağımsız çalışmasını sağlayan simüle edilmiş veri yapıları.
 *
 * UYARI: Tüm veriler açıkça sentetiktir; gerçek müşteri, hesap veya
 * kimlik bilgisi içermemektedir. TC kimlik numaraları ve hesap numaraları
 * geçersiz/test formatındadır.
 */

// ─── Piyasa Takip (Mini Tickers) ─────────────────────────────────────────────
export interface MarketTicker {
  symbol:        string
  name:          string
  value:         number
  unit:          string
  changePercent: number
  sparkline:     number[]
}

export const MOCK_MARKET_TICKERS: MarketTicker[] = [
  { symbol: 'USD/TRY', name: 'Amerikan Doları',  value: 38.54,       unit: '₺',     changePercent: +0.32, sparkline: [0.5,0.52,0.49,0.55,0.53,0.58,0.56,0.61] },
  { symbol: 'EUR/TRY', name: 'Euro',              value: 41.28,       unit: '₺',     changePercent: -0.15, sparkline: [0.6,0.58,0.62,0.59,0.61,0.57,0.60,0.58] },
  { symbol: 'ALTIN',   name: 'Gram Altın',        value: 3_648.70,    unit: '₺',     changePercent: +1.14, sparkline: [0.4,0.45,0.42,0.50,0.55,0.52,0.60,0.65] },
  { symbol: 'BIST100', name: 'Borsa İstanbul',    value: 10_482.3,    unit: 'puan',  changePercent: +0.87, sparkline: [0.55,0.58,0.60,0.57,0.62,0.65,0.63,0.68] },
]

// ─── Yatırım Hesabım (Investment Balance) ───────────────────────────────────
export interface InvestmentBalance {
  totalTRY: number
  totalUSD: number
  breakdown: {
    cashTRY: number
    stocksBIST: number
    stocksUS: number
  }
}

export const MOCK_INVESTMENT_BALANCE: InvestmentBalance = {
  totalTRY: 125_750.40,
  totalUSD: 3_262.85,
  breakdown: {
    cashTRY: 15_420.00,
    stocksBIST: 85_120.40,
    stocksUS: 25_210.00, // ₺ karşılığı
  }
}

// ─── Pozisyonlar (Positions) ────────────────────────────────────────────────
export interface Position {
  symbol: string
  price: number
  quantity: number
  avgCost: number
  totalValue: number
  dailyReturn: number
  dailyReturnPercent: number
  totalReturn: number
  totalReturnPercent: number
}

export const MOCK_POSITIONS: Position[] = [
  { symbol: 'THYAO', price: 295.50, quantity: 120, avgCost: 280.00, totalValue: 35_460.00, dailyReturn: 420.00, dailyReturnPercent: 1.20, totalReturn: 1_860.00, totalReturnPercent: 5.53 },
  { symbol: 'SISE', price: 54.20, quantity: 500, avgCost: 56.10, totalValue: 27_100.00, dailyReturn: -250.00, dailyReturnPercent: -0.91, totalReturn: -950.00, totalReturnPercent: -3.38 },
  { symbol: 'AAPL', price: 215.30, quantity: 3, avgCost: 195.00, totalValue: 24_862.84, dailyReturn: 15.50, dailyReturnPercent: 0.25, totalReturn: 60.90, totalReturnPercent: 10.41 },
]

// ─── Emir Geçmişi (Order History) ───────────────────────────────────────────
export interface Order {
  id: string
  symbol: string
  status: 'Bekliyor' | 'Gerçekleşti' | 'İptal'
  type: 'Alış' | 'Satış'
  quantity: number
  price: number
  total: number
  date: string
}

export const MOCK_ORDERS: Order[] = [
  { id: 'ORD-001', symbol: 'TUPRS', status: 'Bekliyor', type: 'Alış', quantity: 50, price: 172.50, total: 8_625.00, date: '2026-08-14T10:15:00' },
  { id: 'ORD-002', symbol: 'THYAO', status: 'Gerçekleşti', type: 'Satış', quantity: 20, price: 298.00, total: 5_960.00, date: '2026-08-13T15:45:00' },
  { id: 'ORD-003', symbol: 'NVDA', status: 'Gerçekleşti', type: 'Alış', quantity: 2, price: 115.20, total: 230.40, date: '2026-08-12T16:30:00' },
  { id: 'ORD-004', symbol: 'KCHOL', status: 'İptal', type: 'Alış', quantity: 100, price: 210.00, total: 21_000.00, date: '2026-08-11T09:20:00' },
]

// ─── Portföy Grafiği (Candlestick & Volume) ─────────────────────────────────
export interface CandlestickDataPoint {
  time: number // Unix timestamp
  open: number
  high: number
  low: number
  close: number
  value?: number // for volume
  color?: string // for volume color
}

// Rastgele veri üreteci
const generateData = (days: number, startPrice: number, volatility: number): CandlestickDataPoint[] => {
  const data: CandlestickDataPoint[] = []
  let currentPrice = startPrice
  
  // Bugünden geriye doğru gitmek yerine, en eskiden bugüne doğru gel
  const nowMs = Date.now()
  const startMs = nowMs - (days * 24 * 60 * 60 * 1000)

  for (let i = 0; i < days; i++) {
    const time = Math.floor((startMs + i * 24 * 60 * 60 * 1000) / 1000) // saniye cinsinden timestamp
    
    const open = currentPrice + (Math.random() - 0.5) * volatility
    const high = open + Math.random() * volatility
    const low = open - Math.random() * volatility
    const close = low + Math.random() * (high - low)
    
    const isUp = close >= open
    const volume = Math.floor(Math.random() * 10000) + 5000

    data.push({
      time: time as any, // lightweight-charts expects UTCTimestamp which is a branded number
      open,
      high,
      low,
      close,
      value: volume,
      color: isUp ? 'rgba(38, 166, 154, 0.5)' : 'rgba(239, 83, 80, 0.5)'
    })
    
    currentPrice = close
  }
  return data
}

export const MOCK_CHART_DATA = {
  'Gün': generateData(1, 120000, 500), // Gün için genelde saatlik data lazım ama şimdilik 1 mum tutalım (veya intraday time gerek)
  'Hafta': generateData(7, 120000, 1000),
  'Ay': generateData(30, 115000, 1500),
  '3 Ay': generateData(90, 100000, 2000),
  'Yıl': generateData(365, 80000, 3000),
}

// ─── Haberler (News) ────────────────────────────────────────────────────────
export interface NewsItem {
  id: string
  title: string
  source: string
  category: 'BIST' | 'ABD' | 'Genel'
  time: string
}

export const MOCK_NEWS: NewsItem[] = [
  { id: 'N-1', title: 'TCMB faiz kararını açıkladı, piyasalar nasıl tepki verdi?', source: 'Bloomberg HT', category: 'Genel', time: '10:30' },
  { id: 'N-2', title: 'THYAO 2. çeyrek bilançosunda beklentileri aştı', source: 'KAP', category: 'BIST', time: '09:15' },
  { id: 'N-3', title: 'Fed yetkilisinden faiz indirimi sinyali', source: 'Reuters', category: 'ABD', time: 'Dün' },
  { id: 'N-4', title: 'BIST100 endeksi günü rekor seviyeden kapattı', source: 'AA Finans', category: 'BIST', time: 'Dün' },
  { id: 'N-5', title: 'Teknoloji hisselerinde ralli devam ediyor', source: 'CNBC', category: 'ABD', time: '2 gün önce' },
]

// ─── Varlık Dağılımı (Asset Allocation - Donut Chart için) ──────────────────
export interface AssetAllocationItem {
  assetClass: string
  percentage: number
  amount: number
  color: string
}

export const MOCK_ASSET_ALLOCATION: AssetAllocationItem[] = [
  { assetClass: 'Hisse Senedi',   percentage: 42, amount: 52_815.17, color: '#10b981' },
  { assetClass: 'Döviz (USD/EUR)', percentage: 28, amount: 35_210.11, color: '#3b82f6' },
  { assetClass: 'Altın',          percentage: 18, amount: 22_635.07, color: '#f59e0b' },
  { assetClass: 'Yatırım Fonu',   percentage:  8, amount: 10_060.03, color: '#8b5cf6' },
  { assetClass: 'Nakit',          percentage:  4, amount:  5_030.02, color: '#94a3b8' },
]

// ─── Retail / Bütçe Verileri (Geri Yüklenenler) ──────────────────────────────

export interface TransactionData {
  id: string
  description: string
  category: string
  amount: number
  date: string
}

export interface SavingsGoal {
  id: string
  name: string
  target: number
  current: number
  icon: string
  deadline: string
  color: string
}

export interface SpendingOverviewData {
  month: string
  totalExpense: number
  changePercent: number
  categories: {
    label: string
    icon: string
    amount: number
    color: string
  }[]
}

export interface BalanceData {
  period: string
  total: number
  changePercent: number
  changeAmount: number
  sparklinePoints: number[]
}

