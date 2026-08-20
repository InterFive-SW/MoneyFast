import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import PortfolioHighlights from './PortfolioHighlights'
import type { Position } from '../../api/client'

function makePosition(overrides: Partial<Position> = {}): Position {
  return {
    symbol: 'THYAO', price: 295.5, quantity: 120, avgCost: 280, totalValue: 35_460,
    dailyReturn: 420, dailyReturnPercent: 1.2, totalReturn: 1_860, totalReturnPercent: 5.53,
    ...overrides,
  }
}

describe('PortfolioHighlights', () => {
  it('yüklenirken dönen animasyonu gösterir', () => {
    render(<PortfolioHighlights positions={[]} loading />)
    expect(document.querySelector('.animate-spin')).not.toBeNull()
  })

  it('pozisyon yokken bilgi mesajı gösterir', () => {
    render(<PortfolioHighlights positions={[]} loading={false} />)
    expect(screen.getByText('Portföyünüzde görüntülenecek varlık bulunmuyor.')).toBeInTheDocument()
  })

  it('tek pozisyonda yalnızca en çok kazandıranı gösterir, kaybettiren bölümü göstermez', () => {
    render(<PortfolioHighlights positions={[makePosition({ symbol: 'THYAO', totalReturnPercent: 5.53 })]} loading={false} />)
    expect(screen.getByText('En Çok Kazandıran')).toBeInTheDocument()
    expect(screen.queryByText('En Çok Kaybettiren')).not.toBeInTheDocument()
  })

  it('birden fazla pozisyonda en çok kazandıran ve kaybettireni ayrı ayrı gösterir', () => {
    const positions = [
      makePosition({ symbol: 'THYAO', totalReturnPercent: 5.53 }),
      makePosition({ symbol: 'SISE', totalReturnPercent: -3.38 }),
    ]
    render(<PortfolioHighlights positions={positions} loading={false} />)
    expect(screen.getByText('THYAO')).toBeInTheDocument()
    expect(screen.getByText('SISE')).toBeInTheDocument()
    expect(screen.getByText('+5,53%')).toBeInTheDocument()
    expect(screen.getByText('-3,38%')).toBeInTheDocument()
  })
})
