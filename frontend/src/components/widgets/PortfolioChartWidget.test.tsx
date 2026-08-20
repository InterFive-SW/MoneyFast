import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ResizeObserverMock } from '../../test/setup'

// lightweight-charts jsdom'da canvas olmadan çalışmaz — grafik kütüphanesini sahte
// bir implementasyonla değiştirip widget'ın kendi mantığını (filtre değişimi,
// veri güncelleme, hata yakalama, unmount temizliği) izole test ediyoruz.
const mockSeries = { setData: vi.fn(), applyOptions: vi.fn() }
const mockChart = {
  addSeries: vi.fn(() => mockSeries),
  priceScale: vi.fn(() => ({ applyOptions: vi.fn() })),
  applyOptions: vi.fn(),
  timeScale: vi.fn(() => ({ fitContent: vi.fn() })),
  remove: vi.fn(),
}
const createChart = vi.fn(() => mockChart)

// Diğer dönemler için ortak, artan trendli veri (doMock senaryolarında kullanılıyor).
const mockOtherData = [
  { time: 1000, open: 40, high: 45, low: 38, close: 42, value: 10, color: 'x' },
  { time: 2000, open: 42, high: 48, low: 40, close: 46, value: 20, color: 'x' },
]

vi.mock('lightweight-charts', () => ({
  createChart: (...args: unknown[]) => createChart(...args),
  ColorType: { Solid: 'solid' },
  CandlestickSeries: {},
  HistogramSeries: {},
}))

// NOT: vi.mock() dosya başına hoist edilir, bu yüzden factory içinde dışarıdaki
// const'lara (mockYilData/mockOtherData) referans veremiyoruz (TDZ hatası) —
// veri burada birebir kopyalanarak inline tanımlanıyor.
vi.mock('../../data/mockData', () => {
  const yil = [
    { time: 1000, open: 100, high: 130, low: 90, close: 120 },
    { time: 2000, open: 120, high: 125, low: 95, close: 100, value: 500, color: 'x' },
  ]
  const other = [
    { time: 1000, open: 40, high: 45, low: 38, close: 42, value: 10, color: 'x' },
    { time: 2000, open: 42, high: 48, low: 40, close: 46, value: 20, color: 'x' },
  ]
  return {
    MOCK_CHART_DATA: { 'Gün': other, 'Hafta': other, 'Ay': other, '3 Ay': other, 'Yıl': yil },
  }
})

import PortfolioChartWidget from './PortfolioChartWidget'

beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
  mockSeries.setData.mockClear()
  createChart.mockClear()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('PortfolioChartWidget', () => {
  it('varsayılan (büyük) boyutta grafik başlığını ve dönem butonlarını render eder', () => {
    render(<PortfolioChartWidget />)
    expect(screen.getByText('Portföy Performansı')).toBeInTheDocument()
    for (const label of ['Gün', 'Hafta', 'Ay', '3 Ay', 'Yıl']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })

  it('dönem butonuna tıklanınca seriye yeni veri set eder', () => {
    render(<PortfolioChartWidget />)
    mockSeries.setData.mockClear()
    fireEvent.click(screen.getByText('Ay'))
    expect(mockSeries.setData).toHaveBeenCalled()
  })

  it('setData hata fırlatırsa yakalanır ve loglanır', () => {
    mockSeries.setData.mockImplementationOnce(() => {
      throw new Error('chart data error')
    })
    render(<PortfolioChartWidget />)
    expect(console.error).toHaveBeenCalledWith('Chart data error:', expect.any(Error))
  })

  it('konteyner clientWidth/clientHeight > 0 ise chart bu boyutlarla başlatılır', () => {
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, value: 640 })
    Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, value: 480 })
    try {
      render(<PortfolioChartWidget />)
      expect(createChart).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ width: 640, height: 480 }))
    } finally {
      Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, value: 0 })
      Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, value: 0 })
    }
  })

  it('ResizeObserver alakasız/boş entries ile tetiklenirse boyutu güncellemez', () => {
    render(<PortfolioChartWidget />)
    mockChart.applyOptions.mockClear()
    ResizeObserverMock.lastInstance!.callback([], ResizeObserverMock.lastInstance as unknown as ResizeObserver)
    expect(mockChart.applyOptions).not.toHaveBeenCalled()
  })

  it('ResizeObserver geçerli hedefte ama sıfır boyutla tetiklenirse boyutu güncellemez', () => {
    render(<PortfolioChartWidget />)
    const container = document.querySelector('.absolute.inset-0')!
    mockChart.applyOptions.mockClear()
    ResizeObserverMock.lastInstance!.callback(
      [{ target: container, contentRect: { width: 0, height: 0 } } as ResizeObserverEntry],
      ResizeObserverMock.lastInstance as unknown as ResizeObserver
    )
    expect(mockChart.applyOptions).not.toHaveBeenCalled()
  })

  it('küçük boyutta (w<=2) azalan veriyle negatif (rose) özet gösterir', () => {
    render(<PortfolioChartWidget w={2} />)
    expect(screen.getByText('Portföy Performansı (Özet)')).toBeInTheDocument()
    const priceEl = screen.getByText('Son Kapanış').previousElementSibling!
    expect(priceEl.className).toContain('text-rose-500')
  })

  it('küçük boyutta (h<=1) özet görünümünü render eder', () => {
    render(<PortfolioChartWidget h={1} />)
    expect(screen.getByText('Portföy Performansı (Özet)')).toBeInTheDocument()
  })

  it('unmount edildiğinde grafik temizlenir', () => {
    const { unmount } = render(<PortfolioChartWidget />)
    expect(() => unmount()).not.toThrow()
    expect(mockChart.remove).toHaveBeenCalled()
  })
})

describe('PortfolioChartWidget — küçük görünümde farklı veri senaryoları', () => {
  afterEach(() => {
    vi.doUnmock('../../data/mockData')
    vi.resetModules()
  })

  it('artan veriyle pozitif (accent) özet gösterir', async () => {
    vi.resetModules()
    vi.doMock('../../data/mockData', () => ({
      MOCK_CHART_DATA: {
        'Gün': mockOtherData, 'Hafta': mockOtherData, 'Ay': mockOtherData, '3 Ay': mockOtherData,
        'Yıl': [
          { time: 1000, open: 90, high: 100, low: 85, close: 90, value: 5, color: 'x' },
          { time: 2000, open: 90, high: 130, low: 90, close: 120, value: 10, color: 'x' },
        ],
      },
    }))
    const { default: Widget } = await import('./PortfolioChartWidget')
    render(<Widget w={2} />)
    const priceEl = screen.getByText('Son Kapanış').previousElementSibling!
    expect(priceEl.className).toContain('text-accent-500')
  })

  it('dönem verisi boşsa çökmeden "-" gösterir', async () => {
    vi.resetModules()
    vi.doMock('../../data/mockData', () => ({
      MOCK_CHART_DATA: { 'Gün': [], 'Hafta': [], 'Ay': [], '3 Ay': [], 'Yıl': [] },
    }))
    const { default: Widget } = await import('./PortfolioChartWidget')
    render(<Widget w={2} />)
    expect(screen.getByText('-')).toBeInTheDocument()
  })
})
