/**
 * The performance chart must draw the data it fetched.
 *
 * Both memos here derive from `series`, which starts empty and is filled by an
 * async fetch — but `series` was missing from their dependency arrays. The
 * bars arrived, nothing recomputed, and the chart sat on "Seçilen aralıkta
 * veri bulunmuyor" until the user clicked a different range, which changed
 * `mode` and recomputed them by accident.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import PortfolioPerformanceChart from '../PortfolioPerformanceChart'

// lightweight-charts draws to a canvas jsdom does not provide, and its
// failures surface as unhandled "Value is null" errors. The behaviour under
// test is which data reaches the chart, not what it paints.
vi.mock('lightweight-charts', () => {
  const series = { setData: vi.fn(), priceScale: () => ({ applyOptions: vi.fn() }) }
  return {
    createChart: () => ({
      // v5 API: one addSeries() taking a series-type token.
      addSeries: () => series,
      priceScale: () => ({ applyOptions: vi.fn() }),
      timeScale: () => ({ fitContent: vi.fn(), applyOptions: vi.fn() }),
      applyOptions: vi.fn(),
      resize: vi.fn(),
      remove: vi.fn(),
    }),
    CandlestickSeries: 'candlestick',
    HistogramSeries: 'histogram',
    ColorType: { Solid: 'solid' },
    CrosshairMode: { Normal: 0 },
  }
})

/**
 * Pencere pencere mum serisi -- `/api/investment/portfolio/chart`'ın biçimi.
 *
 * Bu uç nokta `XU100`'ü döndürüyordu: BIST 100 endeksini, "Portföy
 * Performansı" başlığının altında. Artık portföyün kendi değer serisi geliyor
 * ve her aralık kendi çözünürlüğünde.
 */
function ranges(count = 300) {
  const day = 86_400
  const start = Math.floor(Date.now() / 1000) - count * day
  const bars = Array.from({ length: count }, (_, i) => ({
    time: start + i * day,
    open: 100 + i * 0.1,
    high: 101 + i * 0.1,
    low: 99 + i * 0.1,
    close: 100.5 + i * 0.1,
    value: 0,
    color: '#22c55e',
  }))
  return { gun: bars, hafta: bars, ay: bars, yil: bars, iki_yil: bars }
}

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class {
    observe() {} unobserve() {} disconnect() {}
  } as never)
  vi.stubGlobal('fetch', vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(ranges()) }),
  ))
  localStorage.setItem('access_token', 'test-token')
})
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('PortfolioPerformanceChart', () => {
  it('draws the fetched bars without the user touching the range', async () => {
    const { container } = render(<PortfolioPerformanceChart />)

    // Empty before the fetch settles is correct and expected.
    expect(container.textContent).toContain('Seçilen aralıkta veri bulunmuyor')

    await waitFor(
      () => expect(container.textContent).not.toContain('Seçilen aralıkta veri bulunmuyor'),
      { timeout: 3000 },
    )
  })

  it('says so honestly when the series really is empty', async () => {
    vi.stubGlobal('fetch', vi.fn(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ gun: [], hafta: [], ay: [], yil: [], iki_yil: [] }),
      }),
    ))
    const { container } = render(<PortfolioPerformanceChart />)
    await new Promise((r) => setTimeout(r, 120))
    expect(container.textContent).toContain('Seçilen aralıkta veri bulunmuyor')
  })
})
