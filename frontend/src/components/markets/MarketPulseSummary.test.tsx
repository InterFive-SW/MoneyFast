import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import MarketPulseSummary from './MarketPulseSummary'
import type { MarketInstrument, MarketTicker } from '../../data/mockData'

function makeInstrument(overrides: Partial<MarketInstrument> = {}): MarketInstrument {
  return {
    symbol: 'THYAO', name: 'Türk Hava Yolları', market: 'BIST', price: 295.5, unit: '₺',
    changePercent: 1.2, volume: 1000, marketCap: 1000, sector: 'Ulaştırma', week52Low: 200, week52High: 300,
    ...overrides,
  }
}

describe('MarketPulseSummary', () => {
  it('enstrüman listesi boşsa hiçbir şey render etmez', () => {
    const { container } = render(<MarketPulseSummary instruments={[]} tickers={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('BIST100 pozitif değişimdeyken "yükseliyor" ve pozitif işaretli yüzdeleri gösterir', () => {
    const instruments = [
      makeInstrument({ symbol: 'THYAO', changePercent: 5 }),
      makeInstrument({ symbol: 'SISE', changePercent: -3 }),
      makeInstrument({ symbol: 'GARAN', changePercent: 0 }),
    ]
    const tickers: MarketTicker[] = [
      { symbol: 'BIST100', name: 'Borsa İstanbul', value: 10_000, unit: 'puan', changePercent: 0.5, sparkline: [] },
    ]
    render(<MarketPulseSummary instruments={instruments} tickers={tickers} />)
    expect(screen.getByText(/yükseliyor/)).toBeInTheDocument()
    expect(screen.getByText('THYAO')).toBeInTheDocument()
    expect(screen.getByText('SISE')).toBeInTheDocument()
    expect(screen.getByText(/\+5\.00%/)).toBeInTheDocument()
    expect(screen.getByText(/-3\.00%/)).toBeInTheDocument()
  })

  it('BIST100 negatif değişimdeyken "geriliyor" gösterir', () => {
    const instruments = [makeInstrument({ symbol: 'A', changePercent: 2 }), makeInstrument({ symbol: 'B', changePercent: -1 })]
    const tickers: MarketTicker[] = [
      { symbol: 'BIST100', name: 'Borsa İstanbul', value: 10_000, unit: 'puan', changePercent: -0.5, sparkline: [] },
    ]
    render(<MarketPulseSummary instruments={instruments} tickers={tickers} />)
    expect(screen.getByText(/geriliyor/)).toBeInTheDocument()
  })

  it('BIST100 ticker\'ı bulunamazsa BIST100 cümlesini atlar', () => {
    const instruments = [makeInstrument({ symbol: 'A', changePercent: 2 }), makeInstrument({ symbol: 'B', changePercent: -1 })]
    render(<MarketPulseSummary instruments={instruments} tickers={[]} />)
    expect(screen.queryByText(/BIST100/)).not.toBeInTheDocument()
    expect(screen.getByText(/En çok kazandıran/)).toBeInTheDocument()
  })
})
