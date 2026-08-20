import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import MarketMoversWidget from './MarketMoversWidget'
import type { MarketInstrument } from '../../data/mockData'

function makeInstrument(overrides: Partial<MarketInstrument> = {}): MarketInstrument {
  return {
    symbol: 'THYAO', name: 'Türk Hava Yolları', market: 'BIST', price: 295.5, unit: '₺',
    changePercent: 1.2, volume: 1000, marketCap: 1000, sector: 'Ulaştırma', week52Low: 200, week52High: 300,
    ...overrides,
  }
}

const instruments = [
  makeInstrument({ symbol: 'SASA', changePercent: 3.4 }),
  makeInstrument({ symbol: 'EREGL', changePercent: -0.92 }),
]

describe('MarketMoversWidget', () => {
  it('varsayılan Yükselenler sekmesinde en çok kazandıranı üstte gösterir', () => {
    render(<MarketMoversWidget instruments={instruments} />)
    expect(screen.getByText('SASA')).toBeInTheDocument()
    expect(screen.getByText('+3.40%')).toBeInTheDocument()
  })

  it('Düşenler sekmesine geçince en çok kaybettireni üstte gösterir, Yükselenler\'e dönünce eski hale gelir', () => {
    render(<MarketMoversWidget instruments={instruments} />)
    fireEvent.click(screen.getByText('Düşenler'))
    expect(screen.getByText('-0.92%')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Yükselenler'))
    expect(screen.getByText('+3.40%')).toBeInTheDocument()
  })
})
