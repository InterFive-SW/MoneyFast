import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ProfitLossHeatmapWidget from './ProfitLossHeatmapWidget'
import { apiClient } from '../../api/client'
import type { HeatmapItem } from '../../api/client'

const items: HeatmapItem[] = [
  { symbol: 'A', weight: 10, changePercent: 3, sector: 'Bankacılık' },
  { symbol: 'B', weight: 8, changePercent: 1, sector: 'Sanayi' },
  { symbol: 'C', weight: 6, changePercent: -3, sector: 'Enerji' },
  { symbol: 'D', weight: 4, changePercent: -1, sector: 'Perakende' },
  { symbol: 'E', weight: 2, changePercent: 0, sector: 'Teknoloji' },
]

beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ProfitLossHeatmapWidget', () => {
  it('yüklenirken dönen animasyonu gösterir', () => {
    vi.spyOn(apiClient, 'getHeatmap').mockReturnValue(new Promise(() => {}))
    render(<ProfitLossHeatmapWidget />)
    expect(document.querySelector('.animate-spin')).not.toBeNull()
  })

  it('küçük boyutta (w<=2) özet görünümde pozitif ortalamayı gösterir', async () => {
    vi.spyOn(apiClient, 'getHeatmap').mockResolvedValue(items)
    render(<ProfitLossHeatmapWidget w={2} />)
    await waitFor(() => expect(screen.getByText('Piyasa Isısı (Özet)')).toBeInTheDocument())
    expect(screen.getByText('+0.00%')).toBeInTheDocument()
  })

  it('küçük boyutta (h<=2) veri boşsa çökmeden ortalama 0 gösterir', async () => {
    vi.spyOn(apiClient, 'getHeatmap').mockResolvedValue([])
    render(<ProfitLossHeatmapWidget h={1} />)
    await waitFor(() => expect(screen.getByText('Piyasa Isısı (Özet)')).toBeInTheDocument())
    expect(screen.getByText('+0.00%')).toBeInTheDocument()
  })

  it('küçük boyutta negatif ortalamada işaretsiz, kırmızı yüzde gösterir', async () => {
    vi.spyOn(apiClient, 'getHeatmap').mockResolvedValue([
      { symbol: 'C', weight: 6, changePercent: -3, sector: 'Enerji' },
      { symbol: 'D', weight: 4, changePercent: -1, sector: 'Perakende' },
    ])
    render(<ProfitLossHeatmapWidget w={2} />)
    await waitFor(() => expect(screen.getByText('Piyasa Isısı (Özet)')).toBeInTheDocument())
    const changeEl = screen.getByText('-2.00%')
    expect(changeEl.className).toContain('text-rose-500')
  })

  it('tam boyutta tüm hücreleri render eder ve hover ile tooltip gösterir', async () => {
    vi.spyOn(apiClient, 'getHeatmap').mockResolvedValue(items)
    render(<ProfitLossHeatmapWidget />)
    await waitFor(() => expect(screen.getByText('A')).toBeInTheDocument())
    expect(screen.getByText('B')).toBeInTheDocument()
    expect(screen.getByText('C')).toBeInTheDocument()
    expect(screen.getByText('D')).toBeInTheDocument()
    expect(screen.getByText('E')).toBeInTheDocument()

    expect(screen.queryByText('Sektör:')).not.toBeInTheDocument()
    const cellA = screen.getByText('A').parentElement!
    fireEvent.mouseEnter(cellA)
    expect(screen.getByText('Sektör:')).toBeInTheDocument()
    expect(screen.getByText('Bankacılık')).toBeInTheDocument()

    fireEvent.mouseLeave(cellA)
    expect(screen.queryByText('Sektör:')).not.toBeInTheDocument()

    // Negatif değişimli bir hücrede tooltip yüzdesi kırmızı (rose) renkte olmalı.
    const cellC = screen.getByText('C').parentElement!
    fireEvent.mouseEnter(cellC)
    const tooltip = document.querySelector('.z-20')!
    const tooltipPercent = within(tooltip as HTMLElement).getByText('-3%')
    expect(tooltipPercent.className).toContain('text-rose-400')
  })

  it('istek başarısız olursa hatayı loglar', async () => {
    vi.spyOn(apiClient, 'getHeatmap').mockRejectedValue(new Error('network'))
    render(<ProfitLossHeatmapWidget />)
    await waitFor(() => expect(console.error).toHaveBeenCalled())
  })
})
