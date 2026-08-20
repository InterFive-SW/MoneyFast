import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import MarketTickerWidget from './MarketTickerWidget'
import type { MarketTicker } from '../../data/mockData'

const tickers: MarketTicker[] = [
  { symbol: 'USD/TRY', name: 'Amerikan Doları', value: 38.54, unit: '₺', changePercent: 0.32, sparkline: [] },
  { symbol: 'EUR/TRY', name: 'Euro', value: 41.28, unit: '₺', changePercent: -0.15, sparkline: [] },
]

describe('MarketTickerWidget', () => {
  it('tüm ticker\'ları render eder, pozitif ve negatif işaretleri doğru gösterir', () => {
    render(<MarketTickerWidget tickers={tickers} />)
    expect(screen.getByText('USD/TRY')).toBeInTheDocument()
    expect(screen.getByText('EUR/TRY')).toBeInTheDocument()
    expect(screen.getByText('+0.32%')).toBeInTheDocument()
    expect(screen.getByText('-0.15%')).toBeInTheDocument()
  })
})
