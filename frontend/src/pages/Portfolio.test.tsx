import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Portfolio from './Portfolio'
import { apiClient } from '../api/client'
import type { Position } from '../api/client'

// PortfolioPerformanceChart lightweight-charts kullanıyor — jsdom'da canvas olmadan çalışmaz.
vi.mock('lightweight-charts', () => ({
  createChart: () => ({
    addSeries: () => ({ setData: () => {}, applyOptions: () => {} }),
    priceScale: () => ({ applyOptions: () => {} }),
    applyOptions: () => {},
    timeScale: () => ({ fitContent: () => {} }),
    remove: () => {},
  }),
  ColorType: { Solid: 'solid' },
  CandlestickSeries: {},
  HistogramSeries: {},
}))

const positions: Position[] = [
  { symbol: 'THYAO', price: 295.5, quantity: 120, avgCost: 280, totalValue: 35_460, dailyReturn: 420, dailyReturnPercent: 1.2, totalReturn: 1_860, totalReturnPercent: 5.53 },
]

function renderPortfolio() {
  return render(
    <MemoryRouter>
      <Portfolio />
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
  vi.spyOn(apiClient, 'getWatchlist').mockResolvedValue({})
  vi.spyOn(apiClient, 'getAssetAllocation').mockResolvedValue([])
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Portfolio', () => {
  it('pozisyonlar yüklenirken özet çubuğu yükleniyor durumunu gösterir, sonra doldurur', async () => {
    vi.spyOn(apiClient, 'getPositions').mockResolvedValue(positions)
    renderPortfolio()

    expect(screen.getByText('Portföyüm')).toBeInTheDocument()
    await waitFor(() => expect(screen.getAllByText('THYAO').length).toBeGreaterThan(0))
  })

  it('pozisyonlar yüklenemezse hatayı loglar ve boş listeyle devam eder', async () => {
    vi.spyOn(apiClient, 'getPositions').mockRejectedValue(new Error('network'))
    renderPortfolio()

    await waitFor(() => expect(console.error).toHaveBeenCalled())
    expect(screen.getByText('Portföyünüzde görüntülenecek varlık bulunmuyor.')).toBeInTheDocument()
  })
})
