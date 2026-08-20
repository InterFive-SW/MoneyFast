import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import PortfolioWidget from './PortfolioWidget'
import type { PortfolioWidgetPayload } from '../../../types/chat'

describe('PortfolioWidget', () => {
  it('kâr durumunda pozitif işaretle ve yeşille gösterir', () => {
    const payload: PortfolioWidgetPayload = {
      total_value: 100_000,
      total_profit_loss: 5_000,
      positions: [
        { symbol: 'THYAO', quantity: 10, avg_cost: 280, last_price: 295.5, market_value: 2955, unrealized_pnl: 155, unrealized_pnl_pct: 0.055 },
      ],
    }
    render(<PortfolioWidget payload={payload} />)
    expect(screen.getByText('THYAO')).toBeInTheDocument()
    expect(screen.getByText(/\+.*5\.000,00/)).toBeInTheDocument()
  })

  it('zarar durumunda işaretsiz ve kırmızı gösterir', () => {
    const payload: PortfolioWidgetPayload = {
      total_value: 90_000,
      total_profit_loss: -3_000,
      positions: [
        { symbol: 'SISE', quantity: 100, avg_cost: 56, last_price: 54.2, market_value: 5420, unrealized_pnl: -180, unrealized_pnl_pct: -0.032 },
      ],
    }
    render(<PortfolioWidget payload={payload} />)
    expect(screen.getByText('SISE')).toBeInTheDocument()
    const total = screen.getByText(/-.*3\.000,00/)
    expect(total.parentElement?.className).toContain('text-rose-600')
  })

  it('pozisyon yokken bilgi mesajı gösterir', () => {
    const payload: PortfolioWidgetPayload = { total_value: 0, total_profit_loss: 0, positions: [] }
    render(<PortfolioWidget payload={payload} />)
    expect(screen.getByText('Aktif pozisyon bulunmuyor.')).toBeInTheDocument()
  })
})
