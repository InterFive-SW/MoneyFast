/**
 * Sample data for the four screens that have no provider.
 *
 * Fonlar (TEFAS), Endeksler (BIST sub-index levels and constituents) and the
 * unbacked Analizler reports cannot be sourced from yfinance, so they render
 * these rows behind a visible "Örnek veri" badge. Everything else in the app
 * now reads the database through the API — the exports that duplicated a real
 * endpoint have been removed rather than left available to reach for.
 *
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
// ─── Haberler (News) ────────────────────────────────────────────────────────
export interface NewsItem {
  id: string
  title: string
  source: string
  category: 'BIST' | 'ABD' | 'Genel'
  time: string
}

// ─── Piyasalar Ekranı — Enstrüman Listesi (Fintables tarzı ana tablo) ───────
export interface MarketInstrument {
  symbol:            string
  name:              string
  market:            'BIST' | 'ABD' | 'Kripto' | 'Döviz' | 'Altın' | 'Diğer'
  price:             number
  unit:              string
  changePercent:     number
  volume:            number
  marketCap:         number
  sector:            string
  week52Low:         number
  week52High:        number
  // Hazır kolon setleri için ek finansal metrikler — kripto varlıklarda uygulanmaz (undefined)
  pe?:                number  // F/K
  pb?:                number  // PD/DD
  evEbitda?:          number  // FD/FAVÖK
  netMargin?:         number  // Net kâr marjı %
  roe?:               number  // Özkaynak kârlılığı %
  debtToEquity?:      number  // Borç/Özkaynak
  revenueGrowth?:     number  // Yıllık gelir büyümesi %
  totalAssets?:       number  // Toplam varlıklar
  operatingCashFlow?: number  // Faaliyet nakit akışı
  indexWeight?:       number  // BIST100 içindeki ağırlık % (sadece BIST hisseleri)
}

export const MOCK_MARKET_INSTRUMENTS: MarketInstrument[] = [
  // ─ BIST ─
  { symbol: 'THYAO', name: 'Türk Hava Yolları',  market: 'BIST', price: 295.50, unit: '₺', changePercent: 1.20,  volume: 48_250_000,  marketCap: 407_800_000_000, sector: 'Ulaştırma',    week52Low: 210.00, week52High: 340.00,
    pe: 8.2,  pb: 1.4, evEbitda: 5.1,  netMargin: 9.8,  roe: 18.5, debtToEquity: 1.35, revenueGrowth: 22.4, totalAssets: 850_000_000_000,   operatingCashFlow: 62_000_000_000, indexWeight: 9.8 },
  { symbol: 'GARAN', name: 'Garanti BBVA',       market: 'BIST', price: 128.90, unit: '₺', changePercent: 0.65,  volume: 62_140_000,  marketCap: 451_200_000_000, sector: 'Bankacılık',   week52Low: 92.00,  week52High: 145.00,
    pe: 5.4,  pb: 1.1, evEbitda: 6.2,  netMargin: 38.2, roe: 24.6, debtToEquity: 8.9,  revenueGrowth: 45.1, totalAssets: 2_450_000_000_000, operatingCashFlow: 180_000_000_000, indexWeight: 8.5 },
  { symbol: 'ASELS', name: 'Aselsan',             market: 'BIST', price: 82.35,  unit: '₺', changePercent: -0.85, volume: 35_670_000,  marketCap: 288_900_000_000, sector: 'Savunma',      week52Low: 58.00,  week52High: 98.00,
    pe: 14.6, pb: 3.2, evEbitda: 9.8,  netMargin: 15.4, roe: 21.3, debtToEquity: 0.62, revenueGrowth: 38.7, totalAssets: 210_000_000_000,   operatingCashFlow: 18_000_000_000, indexWeight: 4.2 },
  { symbol: 'SISE',  name: 'Şişecam',             market: 'BIST', price: 54.20,  unit: '₺', changePercent: -0.91, volume: 21_980_000,  marketCap: 94_600_000_000,  sector: 'Sanayi',       week52Low: 44.00,  week52High: 68.00,
    pe: 11.3, pb: 1.0, evEbitda: 6.7,  netMargin: 6.8,  roe: 8.9,  debtToEquity: 0.95, revenueGrowth: 12.1, totalAssets: 320_000_000_000,   operatingCashFlow: 14_000_000_000, indexWeight: 2.1 },
  { symbol: 'TUPRS', name: 'Tüpraş',              market: 'BIST', price: 174.50, unit: '₺', changePercent: 1.21,  volume: 18_340_000,  marketCap: 340_100_000_000, sector: 'Enerji',       week52Low: 135.00, week52High: 210.00,
    pe: 6.9,  pb: 1.9, evEbitda: 4.3,  netMargin: 4.2,  roe: 27.8, debtToEquity: 1.12, revenueGrowth: 8.5,  totalAssets: 410_000_000_000,   operatingCashFlow: 32_000_000_000, indexWeight: 5.6 },
  { symbol: 'EREGL', name: 'Ereğli Demir Çelik',  market: 'BIST', price: 42.80,  unit: '₺', changePercent: -0.92, volume: 44_710_000,  marketCap: 149_800_000_000, sector: 'Sanayi',       week52Low: 34.00,  week52High: 52.00,
    pe: 15.8, pb: 0.9, evEbitda: 8.1,  netMargin: 3.1,  roe: 5.6,  debtToEquity: 0.48, revenueGrowth: -4.2, totalAssets: 280_000_000_000,   operatingCashFlow: 9_000_000_000, indexWeight: 1.8 },
  { symbol: 'KCHOL', name: 'Koç Holding',         market: 'BIST', price: 212.00, unit: '₺', changePercent: 0.65,  volume: 15_620_000,  marketCap: 478_300_000_000, sector: 'Holding',      week52Low: 165.00, week52High: 245.00,
    pe: 9.1,  pb: 1.3, evEbitda: 6.9,  netMargin: 11.2, roe: 14.8, debtToEquity: 1.05, revenueGrowth: 19.6, totalAssets: 1_100_000_000_000, operatingCashFlow: 55_000_000_000, indexWeight: 7.9 },
  { symbol: 'BIMAS', name: 'BİM Mağazalar',       market: 'BIST', price: 412.50, unit: '₺', changePercent: 0.52,  volume: 9_840_000,   marketCap: 250_600_000_000, sector: 'Perakende',    week52Low: 340.00, week52High: 460.00,
    pe: 21.4, pb: 8.6, evEbitda: 12.3, netMargin: 3.5,  roe: 42.1, debtToEquity: 0.35, revenueGrowth: 28.3, totalAssets: 95_000_000_000,    operatingCashFlow: 21_000_000_000, indexWeight: 3.4 },
  { symbol: 'AKBNK', name: 'Akbank',              market: 'BIST', price: 68.20,  unit: '₺', changePercent: -2.23, volume: 71_450_000,  marketCap: 358_400_000_000, sector: 'Bankacılık',   week52Low: 52.00,  week52High: 82.00,
    pe: 4.8,  pb: 0.95, evEbitda: 5.9, netMargin: 35.6, roe: 22.1, debtToEquity: 9.4,  revenueGrowth: 41.2, totalAssets: 2_100_000_000_000, operatingCashFlow: 145_000_000_000, indexWeight: 6.7 },
  { symbol: 'SASA',  name: 'Sasa Polyester',      market: 'BIST', price: 4.86,   unit: '₺', changePercent: 3.40,  volume: 128_900_000, marketCap: 121_500_000_000, sector: 'Kimya',        week52Low: 3.10,   week52High: 6.20,
    pe: 32.5, pb: 4.1, evEbitda: 18.9, netMargin: 2.1,  roe: 12.6, debtToEquity: 1.8,  revenueGrowth: 65.4, totalAssets: 78_000_000_000,    operatingCashFlow: 3_200_000_000, indexWeight: 2.9 },
  // ─ ABD ─
  { symbol: 'AAPL',  name: 'Apple Inc.',          market: 'ABD',  price: 215.30, unit: '$', changePercent: 0.25,  volume: 52_300_000,   marketCap: 3_310_000_000_000, sector: 'Teknoloji',    week52Low: 164.00, week52High: 237.00,
    pe: 33.2, pb: 48.5, evEbitda: 24.1, netMargin: 25.3, roe: 147.2, debtToEquity: 1.45, revenueGrowth: 6.1 },
  { symbol: 'MSFT',  name: 'Microsoft Corp.',     market: 'ABD',  price: 435.20, unit: '$', changePercent: 0.50,  volume: 19_800_000,   marketCap: 3_230_000_000_000, sector: 'Teknoloji',    week52Low: 340.00, week52High: 468.00,
    pe: 35.8, pb: 12.1, evEbitda: 22.6, netMargin: 35.9, roe: 33.4, debtToEquity: 0.42, revenueGrowth: 14.2 },
  { symbol: 'NVDA',  name: 'NVIDIA Corp.',        market: 'ABD',  price: 128.50, unit: '$', changePercent: 1.70,  volume: 210_400_000,  marketCap: 3_150_000_000_000, sector: 'Yarı İletken', week52Low: 60.00,  week52High: 152.00,
    pe: 45.2, pb: 38.7, evEbitda: 32.5, netMargin: 48.9, roe: 91.5, debtToEquity: 0.18, revenueGrowth: 78.3 },
  { symbol: 'TSLA',  name: 'Tesla Inc.',          market: 'ABD',  price: 248.90, unit: '$', changePercent: -1.85, volume: 88_650_000,   marketCap: 792_000_000_000,   sector: 'Otomotiv',     week52Low: 138.00, week52High: 300.00,
    pe: 68.4, pb: 12.8, evEbitda: 41.2, netMargin: 7.2,  roe: 18.9, debtToEquity: 0.16, revenueGrowth: 3.5 },
  { symbol: 'GOOGL', name: 'Alphabet Inc.',       market: 'ABD',  price: 178.40, unit: '$', changePercent: 0.95,  volume: 24_100_000,   marketCap: 2_180_000_000_000, sector: 'Teknoloji',    week52Low: 130.00, week52High: 202.00,
    pe: 24.6, pb: 6.9, evEbitda: 15.8, netMargin: 26.1, roe: 28.7, debtToEquity: 0.08, revenueGrowth: 11.4 },
  { symbol: 'AMZN',  name: 'Amazon.com Inc.',     market: 'ABD',  price: 195.60, unit: '$', changePercent: 0.40,  volume: 31_700_000,   marketCap: 2_040_000_000_000, sector: 'Perakende',    week52Low: 145.00, week52High: 218.00,
    pe: 38.9, pb: 7.4, evEbitda: 18.3, netMargin: 8.1,  roe: 19.6, debtToEquity: 0.55, revenueGrowth: 10.2 },
  { symbol: 'META',  name: 'Meta Platforms Inc.', market: 'ABD',  price: 612.80, unit: '$', changePercent: -0.55, volume: 14_200_000,   marketCap: 1_560_000_000_000, sector: 'Teknoloji',    week52Low: 410.00, week52High: 660.00,
    pe: 26.3, pb: 8.2, evEbitda: 16.9, netMargin: 34.5, roe: 31.2, debtToEquity: 0.35, revenueGrowth: 16.8 },
  // ─ Kripto (finansal rasyolar uygulanmaz) ─
  { symbol: 'BTC', name: 'Bitcoin',  market: 'Kripto', price: 96_450.00, unit: '$', changePercent: 2.15,  volume: 38_900_000_000, marketCap: 1_910_000_000_000, sector: 'Kripto Para', week52Low: 52_000.00, week52High: 108_000.00 },
  { symbol: 'ETH', name: 'Ethereum', market: 'Kripto', price: 3_680.20,  unit: '$', changePercent: -1.40, volume: 18_200_000_000, marketCap: 442_500_000_000,   sector: 'Kripto Para', week52Low: 2_100.00,  week52High: 4_100.00 },
  { symbol: 'SOL', name: 'Solana',   market: 'Kripto', price: 198.75,    unit: '$', changePercent: 4.60,  volume: 5_400_000_000,  marketCap: 94_300_000_000,    sector: 'Kripto Para', week52Low: 95.00,     week52High: 260.00 },
]

/** Sembolden enstrümanı bulur — detay sayfaları ve çapraz-referans (Fon Pozisyonları vb.) için ortak yardımcı */
export function findInstrument(symbol: string): MarketInstrument | undefined {
  return MOCK_MARKET_INSTRUMENTS.find((i) => i.symbol === symbol)
}

// ─── Piyasalar Ekranı — Fonlar ────────────────────────────────────────────────
export interface FundReturns {
  daily:      number
  monthly:    number
  threeMonth: number
  yearly:     number | null // null = henüz 1 yıllık geçmişi yok ("NA")
  threeYear:  number | null // null = henüz 3 yıllık geçmişi yok ("NA")
  fiveYear:   number | null
}

export interface Fund {
  code:           string
  name:           string
  founder:        string
  umbrella:       string
  managementFee:  number // yıllık %
  withholdingTax: number // stopaj %
  riskValue:      number // 1 (düşük) - 7 (yüksek)
  investorCount:  number
  size:           number // ₺
  netCashFlow:    number // son 1 ay, ₺ (+ giriş, - çıkış)
  returns:        FundReturns
  holdings:       { symbol: string; weight: number }[] // portföy dağılımı — borçlanma/para piyasası fonlarında boş
}

export const MOCK_FUNDS: Fund[] = [
  { code: 'AFT', name: 'İş Portföy Hisse Senedi Fonu',        founder: 'İş Portföy',       umbrella: 'Hisse Senedi Şemsiye Fonu',      managementFee: 2.5, withholdingTax: 0,  riskValue: 6, investorCount: 45_000, size: 3_200_000_000, netCashFlow: 85_000_000,
    returns: { daily: 0.40, monthly: 3.2, threeMonth: 9.8,  yearly: 38.5, threeYear: 145.2, fiveYear: 310.6 },
    holdings: [{ symbol: 'THYAO', weight: 18 }, { symbol: 'GARAN', weight: 12 }, { symbol: 'KCHOL', weight: 10 }, { symbol: 'TUPRS', weight: 8 }, { symbol: 'AKBNK', weight: 7 }] },
  { code: 'APT', name: 'Ak Portföy BIST Endeks Fonu',         founder: 'Ak Portföy',       umbrella: 'Hisse Senedi Şemsiye Fonu',      managementFee: 1.1, withholdingTax: 0,  riskValue: 5, investorCount: 62_000, size: 5_800_000_000, netCashFlow: 210_000_000,
    returns: { daily: 0.35, monthly: 2.9, threeMonth: 8.1,  yearly: 34.2, threeYear: 128.4, fiveYear: 265.9 },
    holdings: [{ symbol: 'GARAN', weight: 9 }, { symbol: 'THYAO', weight: 8.5 }, { symbol: 'AKBNK', weight: 7 }, { symbol: 'KCHOL', weight: 6.5 }, { symbol: 'BIMAS', weight: 5 }] },
  { code: 'GPB', name: 'Garanti Portföy Borçlanma Araçları Fonu', founder: 'Garanti Portföy', umbrella: 'Borçlanma Araçları Şemsiye Fonu', managementFee: 1.5, withholdingTax: 10, riskValue: 2, investorCount: 28_000, size: 1_900_000_000, netCashFlow: -45_000_000,
    returns: { daily: 0.12, monthly: 1.8, threeMonth: 5.4,  yearly: 24.6, threeYear: 82.1,  fiveYear: 165.3 },
    holdings: [] },
  { code: 'YKT', name: 'Yapı Kredi Portföy Değişken Fon',     founder: 'Yapı Kredi Portföy', umbrella: 'Değişken Şemsiye Fonu',         managementFee: 2.2, withholdingTax: 0,  riskValue: 5, investorCount: 19_500, size: 980_000_000,   netCashFlow: 32_000_000,
    returns: { daily: 0.28, monthly: 2.4, threeMonth: 7.2,  yearly: 29.8, threeYear: null,  fiveYear: null },
    holdings: [{ symbol: 'ASELS', weight: 15 }, { symbol: 'THYAO', weight: 12 }, { symbol: 'SISE', weight: 9 }, { symbol: 'TUPRS', weight: 8 }] },
  { code: 'QPP', name: 'QNB Portföy Para Piyasası Fonu',      founder: 'QNB Portföy',      umbrella: 'Para Piyasası Şemsiye Fonu',     managementFee: 0.8, withholdingTax: 10, riskValue: 1, investorCount: 51_000, size: 4_100_000_000, netCashFlow: 560_000_000,
    returns: { daily: 0.13, monthly: 1.6, threeMonth: 4.9,  yearly: 21.3, threeYear: 71.5,  fiveYear: 148.2 },
    holdings: [] },
  { code: 'FPK', name: 'Fiba Portföy Katılım Hisse Fonu',     founder: 'Fiba Portföy',     umbrella: 'Katılım Şemsiye Fonu',           managementFee: 2.0, withholdingTax: 0,  riskValue: 6, investorCount: 8_600,  size: 410_000_000,   netCashFlow: 18_000_000,
    returns: { daily: 0.42, monthly: 3.6, threeMonth: 10.5, yearly: 41.2, threeYear: null,  fiveYear: null },
    holdings: [{ symbol: 'ASELS', weight: 20 }, { symbol: 'TUPRS', weight: 14 }, { symbol: 'KCHOL', weight: 11 }] },
  { code: 'APG', name: 'Ak Portföy Global Teknoloji Fonu',    founder: 'Ak Portföy',       umbrella: 'Değişken Şemsiye Fonu',          managementFee: 2.8, withholdingTax: 0,  riskValue: 7, investorCount: 15_200, size: 720_000_000,   netCashFlow: 95_000_000,
    returns: { daily: 0.55, monthly: 4.8, threeMonth: 14.2, yearly: 52.6, threeYear: 198.4, fiveYear: null },
    holdings: [{ symbol: 'AAPL', weight: 15 }, { symbol: 'MSFT', weight: 14 }, { symbol: 'NVDA', weight: 13 }, { symbol: 'GOOGL', weight: 10 }] },
  { code: 'IPB', name: 'İş Portföy Borçlanma Araçları Fonu',  founder: 'İş Portföy',       umbrella: 'Borçlanma Araçları Şemsiye Fonu', managementFee: 1.3, withholdingTax: 10, riskValue: 2, investorCount: 33_400, size: 2_600_000_000, netCashFlow: -12_000_000,
    returns: { daily: 0.11, monthly: 1.7, threeMonth: 5.1,  yearly: 23.8, threeYear: 79.6,  fiveYear: 159.7 },
    holdings: [] },
  { code: 'GPH', name: 'Garanti Portföy Hisse Senedi Fonu',   founder: 'Garanti Portföy',  umbrella: 'Hisse Senedi Şemsiye Fonu',      managementFee: 2.4, withholdingTax: 0,  riskValue: 6, investorCount: 38_700, size: 2_950_000_000, netCashFlow: 67_000_000,
    returns: { daily: 0.38, monthly: 3.1, threeMonth: 9.4,  yearly: 36.9, threeYear: 139.8, fiveYear: 298.1 },
    holdings: [{ symbol: 'KCHOL', weight: 13 }, { symbol: 'THYAO', weight: 11 }, { symbol: 'GARAN', weight: 10 }, { symbol: 'AKBNK', weight: 8 }, { symbol: 'SISE', weight: 6 }] },
  { code: 'YKD', name: 'Yapı Kredi Portföy Dengeli Fon',      founder: 'Yapı Kredi Portföy', umbrella: 'Değişken Şemsiye Fonu',        managementFee: 1.9, withholdingTax: 0,  riskValue: 4, investorCount: 22_100, size: 1_450_000_000, netCashFlow: 9_000_000,
    returns: { daily: 0.21, monthly: 2.1, threeMonth: 6.5,  yearly: 27.4, threeYear: 94.6,  fiveYear: 187.3 },
    holdings: [{ symbol: 'GARAN', weight: 8 }, { symbol: 'THYAO', weight: 7 }, { symbol: 'TUPRS', weight: 6 }] },
  { code: 'QPK', name: 'QNB Portföy Kripto Varlık Fonu',      founder: 'QNB Portföy',      umbrella: 'Değişken Şemsiye Fonu',          managementFee: 3.2, withholdingTax: 0,  riskValue: 7, investorCount: 6_100,  size: 195_000_000,   netCashFlow: 42_000_000,
    returns: { daily: 1.20, monthly: 8.9, threeMonth: 22.4, yearly: null, threeYear: null,  fiveYear: null },
    holdings: [{ symbol: 'BTC', weight: 45 }, { symbol: 'ETH', weight: 30 }, { symbol: 'SOL', weight: 15 }] },
  { code: 'FPD', name: 'Fiba Portföy Döviz Fonu',             founder: 'Fiba Portföy',     umbrella: 'Para Piyasası Şemsiye Fonu',     managementFee: 1.0, withholdingTax: 0,  riskValue: 3, investorCount: 12_300, size: 680_000_000,   netCashFlow: 21_000_000,
    returns: { daily: 0.18, monthly: 1.9, threeMonth: 5.8,  yearly: 26.1, threeYear: 88.4,  fiveYear: null },
    holdings: [] },
  { code: 'APB', name: 'Ak Portföy BIST 30 Endeks Fonu',      founder: 'Ak Portföy',       umbrella: 'Hisse Senedi Şemsiye Fonu',      managementFee: 1.0, withholdingTax: 0,  riskValue: 5, investorCount: 41_200, size: 3_650_000_000, netCashFlow: 156_000_000,
    returns: { daily: 0.36, monthly: 3.0, threeMonth: 8.4,  yearly: 35.1, threeYear: 132.7, fiveYear: 271.4 },
    holdings: [{ symbol: 'GARAN', weight: 10 }, { symbol: 'AKBNK', weight: 9 }, { symbol: 'THYAO', weight: 8.5 }, { symbol: 'KCHOL', weight: 7 }] },
]

export function findFund(code: string): Fund | undefined {
  return MOCK_FUNDS.find((f) => f.code === code)
}

// ─── Piyasalar Ekranı — Endeksler ─────────────────────────────────────────────
export interface MarketIndex {
  code:            string // 'XU100'
  name:            string // 'BIST 100'
  value:           number
  changePercent:   number
  constituents:    string[] // MarketInstrument.symbol referansları
  returns: {
    sixMonth: number
    oneYear:  number
    threeYear: number
    fiveYear:  number
  }
}

export const MOCK_INDICES: MarketIndex[] = [
  { code: 'XU100', name: 'BIST 100',        value: 10_482.30, changePercent: 0.87,
    constituents: ['THYAO', 'GARAN', 'ASELS', 'SISE', 'TUPRS', 'EREGL', 'KCHOL', 'BIMAS', 'AKBNK', 'SASA'],
    returns: { sixMonth: 18.4, oneYear: 42.6, threeYear: 156.2, fiveYear: 410.8 } },
  { code: 'XU030', name: 'BIST 30',         value: 12_850.40, changePercent: 0.72,
    constituents: ['THYAO', 'GARAN', 'KCHOL', 'AKBNK', 'TUPRS', 'ASELS', 'BIMAS', 'SISE'],
    returns: { sixMonth: 16.9, oneYear: 39.8, threeYear: 148.5, fiveYear: 392.1 } },
  { code: 'XBANK', name: 'BIST Bankacılık', value: 18_420.60, changePercent: -0.45,
    constituents: ['GARAN', 'AKBNK'],
    returns: { sixMonth: 22.1, oneYear: 51.3, threeYear: 178.9, fiveYear: 468.4 } },
  { code: 'XUSIN', name: 'BIST Sınai',      value: 15_230.80, changePercent: 0.55,
    constituents: ['SISE', 'EREGL', 'TUPRS', 'ASELS', 'SASA'],
    returns: { sixMonth: 14.2, oneYear: 33.7, threeYear: 121.4, fiveYear: 305.6 } },
  { code: 'XUHIZ', name: 'BIST Hizmetler',  value: 9_640.15,  changePercent: 1.05,
    constituents: ['THYAO', 'BIMAS', 'KCHOL'],
    returns: { sixMonth: 19.8, oneYear: 45.2, threeYear: 163.7, fiveYear: 421.3 } },
]

// ─── Piyasalar Ekranı — Sektörler (özel segmentasyon) ─────────────────────────

// ─── Piyasalar Ekranı — Analizler (piyasa geneli rapor sayfaları) ─────────────
export interface EarningsReport {
  symbol:       string
  period:       string
  revenue:      number
  netIncome:    number
  epsActual:    number
  epsExpected:  number
  surprise:     number // % beat(+)/miss(-)
  reportDate:   string
}

export const MOCK_EARNINGS_REPORTS: EarningsReport[] = [
  { symbol: 'THYAO', period: '2026 Ç2', revenue: 128_400_000_000, netIncome: 12_600_000_000, epsActual: 5.82, epsExpected: 5.40, surprise: 7.8,  reportDate: '2026-08-14' },
  { symbol: 'GARAN', period: '2026 Ç2', revenue: 94_200_000_000,  netIncome: 36_000_000_000, epsActual: 8.15, epsExpected: 7.90, surprise: 3.2,  reportDate: '2026-08-12' },
  { symbol: 'TUPRS', period: '2026 Ç2', revenue: 210_500_000_000, netIncome: 8_900_000_000,  epsActual: 3.10, epsExpected: 3.45, surprise: -10.1, reportDate: '2026-08-11' },
  { symbol: 'AKBNK', period: '2026 Ç2', revenue: 88_600_000_000,  netIncome: 31_500_000_000, epsActual: 7.42, epsExpected: 7.20, surprise: 3.1,  reportDate: '2026-08-13' },
  { symbol: 'ASELS', period: '2026 Ç2', revenue: 32_100_000_000,  netIncome: 4_950_000_000,  epsActual: 1.28, epsExpected: 1.15, surprise: 11.3, reportDate: '2026-08-10' },
  { symbol: 'BIMAS', period: '2026 Ç2', revenue: 165_800_000_000, netIncome: 5_800_000_000,  epsActual: 12.40, epsExpected: 12.60, surprise: -1.6, reportDate: '2026-08-15' },
  { symbol: 'SISE',  period: '2026 Ç2', revenue: 48_900_000_000,  netIncome: 3_320_000_000,  epsActual: 1.94, epsExpected: 2.05, surprise: -5.4, reportDate: '2026-08-08' },
  { symbol: 'KCHOL', period: '2026 Ç2', revenue: 312_600_000_000, netIncome: 35_000_000_000, epsActual: 15.60, epsExpected: 14.90, surprise: 4.7,  reportDate: '2026-08-09' },
]

export interface DividendAnnouncement {
  symbol:         string
  amountPerShare: number
  yieldPercent:   number
  exDate:         string
  paymentDate:    string
}

export const MOCK_DIVIDEND_ANNOUNCEMENTS: DividendAnnouncement[] = [
  { symbol: 'TUPRS', amountPerShare: 8.40,  yieldPercent: 4.8, exDate: '2026-09-10', paymentDate: '2026-09-17' },
  { symbol: 'DOAS',  amountPerShare: 12.50, yieldPercent: 4.5, exDate: '2026-08-25', paymentDate: '2026-09-01' },
  { symbol: 'ENJSA', amountPerShare: 2.80,  yieldPercent: 5.2, exDate: '2026-09-15', paymentDate: '2026-09-22' },
  { symbol: 'FROTO', amountPerShare: 25.00, yieldPercent: 2.1, exDate: '2026-10-05', paymentDate: '2026-10-12' },
  { symbol: 'AKBNK', amountPerShare: 3.15,  yieldPercent: 4.6, exDate: '2026-09-05', paymentDate: '2026-09-12' },
  { symbol: 'SASA',  amountPerShare: 0.18,  yieldPercent: 3.7, exDate: '2026-09-20', paymentDate: '2026-09-27' },
]

export interface IpoAnnouncement {
  companyName:        string
  sector:             string
  priceRangeLow:      number
  priceRangeHigh:     number
  subscriptionStart:  string
  subscriptionEnd:    string
  status:             'Yaklaşan' | 'Devam Ediyor' | 'Tamamlandı'
}

export const MOCK_IPO_ANNOUNCEMENTS: IpoAnnouncement[] = [
  { companyName: 'Anadolu Teknoloji A.Ş.',   sector: 'Teknoloji',   priceRangeLow: 18.00, priceRangeHigh: 22.00, subscriptionStart: '2026-08-24', subscriptionEnd: '2026-08-26', status: 'Yaklaşan' },
  { companyName: 'Mavi Enerji Holding',      sector: 'Enerji',      priceRangeLow: 42.50, priceRangeHigh: 48.00, subscriptionStart: '2026-08-19', subscriptionEnd: '2026-08-21', status: 'Devam Ediyor' },
  { companyName: 'Kuzey Lojistik A.Ş.',      sector: 'Ulaştırma',   priceRangeLow: 9.20,  priceRangeHigh: 11.50, subscriptionStart: '2026-08-05', subscriptionEnd: '2026-08-07', status: 'Tamamlandı' },
  { companyName: 'Yeşil Tarım Ürünleri A.Ş.', sector: 'Gıda',        priceRangeLow: 6.80,  priceRangeHigh: 8.10,  subscriptionStart: '2026-09-02', subscriptionEnd: '2026-09-04', status: 'Yaklaşan' },
]

export interface AnalystRecommendation {
  symbol:               string
  brokerage:            string
  recommendation:       'Al' | 'Tut' | 'Sat'
  targetPrice:          number
  previousTargetPrice:  number | null
  date:                 string
}

export const MOCK_ANALYST_RECOMMENDATIONS: AnalystRecommendation[] = [
  { symbol: 'THYAO', brokerage: 'İş Yatırım',    recommendation: 'Al',  targetPrice: 365.00, previousTargetPrice: 340.00, date: '2026-08-15' },
  { symbol: 'GARAN', brokerage: 'Ak Yatırım',    recommendation: 'Al',  targetPrice: 152.00, previousTargetPrice: 145.00, date: '2026-08-14' },
  { symbol: 'TUPRS', brokerage: 'Yapı Kredi Yatırım', recommendation: 'Tut', targetPrice: 180.00, previousTargetPrice: 195.00, date: '2026-08-12' },
  { symbol: 'AKBNK', brokerage: 'QNB Finans Yatırım', recommendation: 'Al',  targetPrice: 82.00,  previousTargetPrice: 78.00,  date: '2026-08-13' },
  { symbol: 'EREGL', brokerage: 'Garanti BBVA Yatırım', recommendation: 'Sat', targetPrice: 38.00, previousTargetPrice: 44.00, date: '2026-08-10' },
  { symbol: 'BIMAS', brokerage: 'Ak Yatırım',    recommendation: 'Tut', targetPrice: 420.00, previousTargetPrice: null, date: '2026-08-16' },
]

export interface CapitalIncrease {
  symbol:      string
  type:        'Bedelli' | 'Bedelsiz' | 'Karma'
  ratio:       number // %
  recordDate:  string
  status:      'Onaylandı' | 'Beklemede' | 'Tamamlandı'
}

export const MOCK_CAPITAL_INCREASES: CapitalIncrease[] = [
  { symbol: 'SASA',  type: 'Bedelsiz', ratio: 50,  recordDate: '2026-09-01', status: 'Onaylandı' },
  { symbol: 'KCHOL', type: 'Bedelli',  ratio: 15,  recordDate: '2026-09-18', status: 'Beklemede' },
  { symbol: 'ASELS', type: 'Bedelsiz', ratio: 25,  recordDate: '2026-08-20', status: 'Tamamlandı' },
  { symbol: 'SISE',  type: 'Karma',    ratio: 30,  recordDate: '2026-09-25', status: 'Beklemede' },
]

// ─── Varlık Dağılımı (Asset Allocation - Donut Chart için) ──────────────────
export interface AssetAllocationItem {
  assetClass: string
  percentage: number
  amount: number
  color: string
}

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

