import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ResizeObserverMock } from '../../test/setup'
import { SERIES_START, SERIES_END, secondsToDateInput, getSeries } from '../../data/portfolioSeries'

// lightweight-charts jsdom'da canvas olmadan çalışmaz — bkz. PortfolioChartWidget.test.tsx'teki
// aynı desen. data/portfolioSeries.ts gerçek (seed'li, deterministik) haliyle kullanılıyor.
const mockSeries = { setData: vi.fn(), applyOptions: vi.fn() }
const mockChart = {
  addSeries: vi.fn(() => mockSeries),
  priceScale: vi.fn(() => ({ applyOptions: vi.fn() })),
  applyOptions: vi.fn(),
  timeScale: vi.fn(() => ({ fitContent: vi.fn() })),
  remove: vi.fn(),
}
const createChart = vi.fn(() => mockChart)

vi.mock('lightweight-charts', () => ({
  createChart: (...args: unknown[]) => createChart(...args),
  ColorType: { Solid: 'solid' },
  CandlestickSeries: {},
  HistogramSeries: {},
}))

// getSeries'i gerçek davranışını koruyan bir spy'a sarmalıyoruz — böylece "veri yok"
// ve "hacimsiz nokta" gibi gerçek üretim verisinde asla oluşmayan uç durumları,
// tüm bileşeni sahtelemeden, tek bir çağrı için tetikleyebiliyoruz.
vi.mock('../../data/portfolioSeries', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../data/portfolioSeries')>()
  return { ...actual, getSeries: vi.fn(actual.getSeries) }
})

import PortfolioPerformanceChart from './PortfolioPerformanceChart'

// Başlangıç/Bitiş <label>'ları <input>'lara htmlFor/id ile bağlı değil —
// sıradaki iki date input'u doğrudan alıyoruz: [0]=Başlangıç, [1]=Bitiş.
function getDateInputs() {
  return Array.from(document.querySelectorAll('input[type="date"]')) as HTMLInputElement[]
}

beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
  mockSeries.setData.mockClear()
  createChart.mockClear()
  vi.mocked(getSeries).mockClear()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('PortfolioPerformanceChart', () => {
  it('varsayılan olarak başlığı ve hazır aralık butonlarını render eder', () => {
    render(<PortfolioPerformanceChart />)
    expect(screen.getByText('Portföy Performansı')).toBeInTheDocument()
    for (const label of ['Gün', 'Hafta', 'Ay', '3 Ay', 'Yıl']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })

  it('farklı bir hazır aralığa tıklanınca seriye yeni veri set eder', () => {
    render(<PortfolioPerformanceChart />)
    mockSeries.setData.mockClear()
    fireEvent.click(screen.getByText('Ay'))
    expect(mockSeries.setData).toHaveBeenCalled()
  })

  it('setData hata fırlatırsa yakalanır ve loglanır', () => {
    mockSeries.setData.mockImplementationOnce(() => {
      throw new Error('chart data error')
    })
    render(<PortfolioPerformanceChart />)
    expect(console.error).toHaveBeenCalledWith('Chart data error:', expect.any(Error))
  })

  it('konteyner clientWidth/clientHeight > 0 ise chart bu boyutlarla başlatılır', () => {
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, value: 640 })
    Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, value: 480 })
    try {
      render(<PortfolioPerformanceChart />)
      expect(createChart).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ width: 640, height: 480 }))
    } finally {
      Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, value: 0 })
      Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, value: 0 })
    }
  })

  it('ResizeObserver alakasız/boş entries ile tetiklenirse boyutu güncellemez', () => {
    render(<PortfolioPerformanceChart />)
    mockChart.applyOptions.mockClear()
    ResizeObserverMock.lastInstance!.callback([], ResizeObserverMock.lastInstance as unknown as ResizeObserver)
    expect(mockChart.applyOptions).not.toHaveBeenCalled()
  })

  it('ResizeObserver geçerli hedefte ama sıfır boyutla tetiklenirse boyutu güncellemez', () => {
    render(<PortfolioPerformanceChart />)
    const container = document.querySelector('.absolute.inset-0')!
    mockChart.applyOptions.mockClear()
    ResizeObserverMock.lastInstance!.callback(
      [{ target: container, contentRect: { width: 0, height: 0 } } as ResizeObserverEntry],
      ResizeObserverMock.lastInstance as unknown as ResizeObserver
    )
    expect(mockChart.applyOptions).not.toHaveBeenCalled()
  })

  it('unmount edildiğinde grafik temizlenir', () => {
    const { unmount } = render(<PortfolioPerformanceChart />)
    expect(() => unmount()).not.toThrow()
    expect(mockChart.remove).toHaveBeenCalled()
  })

  it('getSeries boş dizi dönerse "veri bulunmuyor" mesajı gösterir ve seriye veri set etmez', () => {
    vi.mocked(getSeries).mockReturnValueOnce([])
    render(<PortfolioPerformanceChart />)
    expect(screen.getByText('Seçilen aralıkta veri bulunmuyor.')).toBeInTheDocument()
    expect(mockSeries.setData).not.toHaveBeenCalled()
  })

  it('bir mumda value alanı yoksa hacim verisinde 0 olarak yedeklenir', () => {
    vi.mocked(getSeries).mockReturnValueOnce([
      { time: 1000, open: 10, high: 12, low: 9, close: 11 }, // value yok
    ])
    render(<PortfolioPerformanceChart />)
    expect(mockSeries.setData).toHaveBeenCalledWith([
      expect.objectContaining({ value: 0 }),
    ])
  })

  it('özel aralık: başlangıç/bitiş tarihleri boşsa uyarı gösterir', () => {
    render(<PortfolioPerformanceChart />)
    fireEvent.click(screen.getByText('Özel Aralık'))
    fireEvent.click(screen.getByText('Uygula'))
    expect(screen.getByText('Lütfen başlangıç ve bitiş tarihlerini seçin.')).toBeInTheDocument()
  })

  it('özel aralık: yalnızca bitiş tarihi boşsa da aynı uyarı gösterir', () => {
    render(<PortfolioPerformanceChart />)
    fireEvent.click(screen.getByText('Özel Aralık'))
    const [fromInput] = getDateInputs()
    fireEvent.change(fromInput, { target: { value: secondsToDateInput(SERIES_START) } })
    fireEvent.click(screen.getByText('Uygula'))
    expect(screen.getByText('Lütfen başlangıç ve bitiş tarihlerini seçin.')).toBeInTheDocument()
  })

  it('özel aralık: bitiş başlangıçtan önceyse uyarı gösterir', () => {
    render(<PortfolioPerformanceChart />)
    fireEvent.click(screen.getByText('Özel Aralık'))
    const [fromInput, toInput] = getDateInputs()
    fireEvent.change(fromInput, { target: { value: secondsToDateInput(SERIES_END) } })
    fireEvent.change(toInput, { target: { value: secondsToDateInput(SERIES_START) } })
    fireEvent.click(screen.getByText('Uygula'))
    expect(screen.getByText('Bitiş tarihi başlangıç tarihinden sonra olmalıdır.')).toBeInTheDocument()
  })

  it('özel aralık: gelecekteki bir tarih veri kapsamı dışı uyarısı verir', () => {
    render(<PortfolioPerformanceChart />)
    fireEvent.click(screen.getByText('Özel Aralık'))
    const [fromInput, toInput] = getDateInputs()
    fireEvent.change(fromInput, { target: { value: '2099-01-01' } })
    fireEvent.change(toInput, { target: { value: '2099-01-02' } })
    fireEvent.click(screen.getByText('Uygula'))
    expect(screen.getByText('Seçilen aralık veri kapsamının dışında.')).toBeInTheDocument()
  })

  it('özel aralık: seri başlangıcından önceki bir tarih aralığı da veri kapsamı dışı uyarısı verir', () => {
    render(<PortfolioPerformanceChart />)
    fireEvent.click(screen.getByText('Özel Aralık'))
    const [fromInput, toInput] = getDateInputs()
    fireEvent.change(fromInput, { target: { value: '2015-01-01' } })
    fireEvent.change(toInput, { target: { value: '2015-01-02' } })
    fireEvent.click(screen.getByText('Uygula'))
    expect(screen.getByText('Seçilen aralık veri kapsamının dışında.')).toBeInTheDocument()
  })

  it('özel aralık: geçerli tarihlerle uygulanınca etikette gösterilir ve picker kapanır', () => {
    render(<PortfolioPerformanceChart />)
    fireEvent.click(screen.getByText('Özel Aralık'))
    const [fromInput, toInput] = getDateInputs()
    fireEvent.change(fromInput, { target: { value: secondsToDateInput(SERIES_START) } })
    fireEvent.change(toInput, { target: { value: secondsToDateInput(SERIES_END) } })
    fireEvent.click(screen.getByText('Uygula'))

    expect(screen.queryByText('Uygula')).not.toBeInTheDocument() // picker kapandı
    expect(screen.getByText(new RegExp(secondsToDateInput(SERIES_START)))).toBeInTheDocument()
  })

  it('özel aralık uygulandıktan sonra Temizle ile Yıl moduna döner', () => {
    render(<PortfolioPerformanceChart />)
    fireEvent.click(screen.getByText('Özel Aralık'))
    const [fromInput, toInput] = getDateInputs()
    fireEvent.change(fromInput, { target: { value: secondsToDateInput(SERIES_START) } })
    fireEvent.change(toInput, { target: { value: secondsToDateInput(SERIES_END) } })
    fireEvent.click(screen.getByText('Uygula'))

    fireEvent.click(screen.getByText('Özel Aralık'))
    fireEvent.click(screen.getByText('Temizle'))
    expect(screen.queryByText(new RegExp(secondsToDateInput(SERIES_START)))).not.toBeInTheDocument()
  })

  it('bir hazır aralık butonuna tıklamak açık hata mesajını temizler', () => {
    render(<PortfolioPerformanceChart />)
    fireEvent.click(screen.getByText('Özel Aralık'))
    fireEvent.click(screen.getByText('Uygula')) // hata üretir
    expect(screen.getByText('Lütfen başlangıç ve bitiş tarihlerini seçin.')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Gün'))
    fireEvent.click(screen.getByText('Özel Aralık'))
    expect(screen.queryByText('Lütfen başlangıç ve bitiş tarihlerini seçin.')).not.toBeInTheDocument()
  })
})
