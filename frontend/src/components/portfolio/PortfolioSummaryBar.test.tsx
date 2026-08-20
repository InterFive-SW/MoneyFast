import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import PortfolioSummaryBar from './PortfolioSummaryBar'
import type { Position } from '../../api/client'

function makePosition(overrides: Partial<Position> = {}): Position {
  return {
    symbol: 'THYAO', price: 295.5, quantity: 120, avgCost: 280, totalValue: 35_460,
    dailyReturn: 420, dailyReturnPercent: 1.2, totalReturn: 1_860, totalReturnPercent: 5.53,
    ...overrides,
  }
}

describe('PortfolioSummaryBar', () => {
  it('yüklenirken dönen animasyonu gösterir', () => {
    render(<PortfolioSummaryBar positions={[]} loading />)
    expect(document.querySelector('.animate-spin')).not.toBeNull()
  })

  it('pozisyon yokken tüm tabanlar sıfır olur, düşmeden %0 gösterir', () => {
    render(<PortfolioSummaryBar positions={[]} loading={false} />)
    expect(screen.getByText('Toplam Portföy Değeri')).toBeInTheDocument()
    expect(screen.getAllByText(/0,00%/).length).toBeGreaterThan(0)
  })

  it('günlük zarar ve toplam kâr birlikteyken renkleri doğru ayırır', () => {
    const positions = [
      makePosition({ totalValue: 35_460, dailyReturn: -420, totalReturn: 1_860 }),
    ]
    render(<PortfolioSummaryBar positions={positions} loading={false} />)
    const dailyValue = screen.getByText(/-.*420,00/)
    expect(dailyValue.className).toContain('text-rose-500')
  })

  it('günlük kâr ve toplam zarar birlikteyken renkleri doğru ayırır', () => {
    const positions = [
      makePosition({ totalValue: 35_460, dailyReturn: 420, totalReturn: -1_860 }),
    ]
    render(<PortfolioSummaryBar positions={positions} loading={false} />)
    const totalValue = screen.getByText(/-.*1\.860,00/)
    expect(totalValue.className).toContain('text-rose-500')
  })
})
